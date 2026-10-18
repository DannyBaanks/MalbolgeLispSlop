"""Resource-bounded subprocess runner for generated fixed-19 guests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import os
from pathlib import Path
import resource
import selectors
import signal
import subprocess
import time


class GuestStatus(str, Enum):
    HALT = "HALT"
    MAX_STEPS = "MAX_STEPS"
    LOAD_ERROR = "LOAD_ERROR"
    WALL_TIMEOUT = "WALL_TIMEOUT"
    OUTPUT_LIMIT = "OUTPUT_LIMIT"
    PROCESS_ERROR = "PROCESS_ERROR"


@dataclass(frozen=True, slots=True)
class RunConfig:
    loader: str
    max_steps: int
    timeout_seconds: float
    address_space_bytes: int
    output_bytes: int

    def __post_init__(self) -> None:
        if self.loader not in {"raw", "canonical"}:
            raise ValueError("loader must be raw or canonical")
        if type(self.max_steps) is not int or self.max_steps <= 0:
            raise ValueError("max_steps must be a positive integer")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be finite and positive")
        if type(self.address_space_bytes) is not int or self.address_space_bytes <= 0:
            raise ValueError("address_space_bytes must be a positive integer")
        if type(self.output_bytes) is not int or self.output_bytes < 0:
            raise ValueError("output_bytes must not be negative")


@dataclass(frozen=True, slots=True)
class GuestResult:
    stdout: bytes
    stderr: bytes
    returncode: int | None
    status: GuestStatus


_STDERR_LIMIT = 1_048_576
_CHUNK_SIZE = 65_536


def _set_address_space_limit(limit: int) -> None:
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.kill()
        except ProcessLookupError:
            pass


def _status_from_stderr(stderr: bytes, returncode: int) -> GuestStatus:
    if b"HALT steps=" in stderr and returncode == 0:
        return GuestStatus.HALT
    if b"MAX_STEPS " in stderr:
        return GuestStatus.MAX_STEPS
    if any(
        marker in stderr
        for marker in (
            b"caracter invalido",
            b"tamano invalido",
            b"no pude abrir",
            b"lectura corta",
        )
    ):
        return GuestStatus.LOAD_ERROR
    return GuestStatus.PROCESS_ERROR


def run_guest(
    image: Path,
    stdin: bytes,
    config: RunConfig,
    *,
    engine_path: Path | None = None,
) -> GuestResult:
    """Execute an image while bounding wall time, address space, and output.

    ``output_bytes`` caps captured stdout. Stderr is drained continuously and
    capped at one MiB to keep diagnostics bounded. Crossing either cap kills
    the guest and returns ``OUTPUT_LIMIT``. ``WALL_TIMEOUT`` is reported only
    when the deadline actually terminated the guest; a guest that exited on
    its own is classified from its exit code and telemetry even if the
    deadline check fires while draining.
    """
    if not isinstance(stdin, bytes):
        raise ValueError("stdin must be bytes")
    engine = engine_path or Path(__file__).resolve().parents[1] / "build" / "bolge19"
    if not image.is_file():
        return GuestResult(
            b"",
            f"guest image does not exist: {image}".encode(),
            None,
            GuestStatus.LOAD_ERROR,
        )
    if not engine.is_file():
        return GuestResult(
            b"",
            f"guest VM does not exist: {engine}".encode(),
            None,
            GuestStatus.PROCESS_ERROR,
        )

    command = [
        str(engine),
        str(image),
        "--loader",
        config.loader,
        "--max-steps",
        str(config.max_steps),
    ]
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            close_fds=True,
            start_new_session=True,
            preexec_fn=lambda: _set_address_space_limit(config.address_space_bytes),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return GuestResult(b"", str(exc).encode(), None, GuestStatus.PROCESS_ERROR)

    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    selector = selectors.DefaultSelector()
    stdout_fd = process.stdout.fileno()
    stderr_fd = process.stderr.fileno()
    stdin_fd = process.stdin.fileno()
    for fd in (stdout_fd, stderr_fd, stdin_fd):
        os.set_blocking(fd, False)

    stdout = bytearray()
    stderr = bytearray()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    written = 0
    if stdin:
        selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
    else:
        process.stdin.close()

    deadline = time.monotonic() + config.timeout_seconds
    wall_timeout = False
    output_limit = False
    while selector.get_map():
        now = time.monotonic()
        if now >= deadline:
            wall_timeout = True
            _kill_process_group(process)
            deadline = float("inf")

        events = selector.select(timeout=min(0.05, max(0.0, deadline - now)))
        for key, mask in events:
            if key.data == "stdin":
                try:
                    written += os.write(stdin_fd, stdin[written : written + _CHUNK_SIZE])
                except BrokenPipeError:
                    written = len(stdin)
                if written >= len(stdin):
                    selector.unregister(process.stdin)
                    process.stdin.close()
            elif mask & selectors.EVENT_READ:
                target = stdout if key.data == "stdout" else stderr
                limit = config.output_bytes if key.data == "stdout" else _STDERR_LIMIT
                try:
                    chunk = os.read(key.fd, _CHUNK_SIZE)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                remaining = max(0, limit - len(target))
                target.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    output_limit = True
                    _kill_process_group(process)
                    deadline = float("inf")

    selector.close()
    process.stdin.close() if not process.stdin.closed else None
    try:
        process.wait(timeout=0.2)
    except subprocess.TimeoutExpired:
        _kill_process_group(process)
        process.wait()

    if output_limit:
        status = GuestStatus.OUTPUT_LIMIT
        returncode: int | None = process.returncode
    elif wall_timeout and process.returncode == -signal.SIGKILL:
        status = GuestStatus.WALL_TIMEOUT
        returncode = None
    else:
        returncode = process.returncode
        assert returncode is not None
        status = _status_from_stderr(bytes(stderr), returncode)
    return GuestResult(bytes(stdout), bytes(stderr), returncode, status)
