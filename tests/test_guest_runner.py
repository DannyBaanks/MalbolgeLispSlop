from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.guest_runner import GuestStatus, RunConfig, run_guest


def _payload_pipe(payload: bytes):
    read_fd, write_fd = os.pipe()
    os.write(write_fd, payload)
    os.close(write_fd)
    return os.fdopen(read_fd, "rb")


def _stdin_pipe():
    read_fd, write_fd = os.pipe()
    return os.fdopen(read_fd, "rb"), os.fdopen(write_fd, "wb")


class _FakeProcess:
    """Deterministic stand-in used to place the deadline check precisely."""

    def __init__(self, *, stdout: bytes, stderr: bytes, exited: bool) -> None:
        self.stdout = _payload_pipe(stdout)
        self.stderr = _payload_pipe(stderr)
        self._stdin_read, self.stdin = _stdin_pipe()
        self.pid = 1 << 30
        self.returncode = 0 if exited else None

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            self.returncode = -9
        return self.returncode

    def kill(self) -> None:
        raise ProcessLookupError


class GuestRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.image = self.root / "guest.mb"
        self.image.write_bytes(b"generated")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_engine(self, body: str) -> Path:
        engine = self.root / "fake_bolge19"
        engine.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
        engine.chmod(engine.stat().st_mode | 0o111)
        return engine

    def config(self, *, timeout: float = 2.0, output_bytes: int = 16) -> RunConfig:
        return RunConfig(
            loader="canonical",
            max_steps=100,
            timeout_seconds=timeout,
            address_space_bytes=512 * 1024 * 1024,
            output_bytes=output_bytes,
        )

    def run_fake(self, body: str, *, timeout: float = 2.0, output_bytes: int = 16):
        engine = self.make_engine(body)
        return run_guest(
            self.image,
            b"input",
            self.config(timeout=timeout, output_bytes=output_bytes),
            engine_path=engine,
        )

    def test_stdout_capture_is_capped_and_reports_output_limit(self) -> None:
        result = self.run_fake("import os\nos.write(1, b'x' * 1000000)\n", output_bytes=32)

        self.assertEqual(result.status, GuestStatus.OUTPUT_LIMIT)
        self.assertEqual(len(result.stdout), 32)
        self.assertLessEqual(len(result.stdout), 32)

    def test_halt_and_step_exhaustion_are_distinct(self) -> None:
        halted = self.run_fake(
            "import os\nos.write(2, b'bolge19: HALT steps=3\\n')\n"
        )
        exhausted = self.run_fake(
            "import os\nos.write(2, b'bolge19: MAX_STEPS 100\\n')\n"
        )

        self.assertEqual(halted.status, GuestStatus.HALT)
        self.assertEqual(exhausted.status, GuestStatus.MAX_STEPS)

    def test_wall_timeout_is_not_a_halt(self) -> None:
        result = self.run_fake("import time\ntime.sleep(2)\n", timeout=0.05)

        self.assertEqual(result.status, GuestStatus.WALL_TIMEOUT)
        self.assertIsNone(result.returncode)

    def test_loader_error_is_distinct_from_process_error(self) -> None:
        result = self.run_fake(
            "import os\n"
            "os.write(2, b'bolge19: caracter invalido\\n')\n"
            "raise SystemExit(2)\n"
        )

        self.assertEqual(result.status, GuestStatus.LOAD_ERROR)

    def test_unrecognized_exit_is_process_error(self) -> None:
        result = self.run_fake("raise SystemExit(7)\n")

        self.assertEqual(result.status, GuestStatus.PROCESS_ERROR)

    def test_guest_that_exited_when_the_deadline_fires_classifies_by_telemetry(
        self,
    ) -> None:
        process = _FakeProcess(
            stdout=b"",
            stderr=b"bolge19: HALT steps=3 c=1 d=1 a=1 elapsed=0s\n",
            exited=True,
        )
        engine = self.root / "fake_bolge19"
        engine.write_bytes(b"x")
        ticks = iter([100.0, 103.0])
        fake_time = mock.Mock()
        fake_time.monotonic.side_effect = lambda: next(ticks, 2000.0)

        with (
            mock.patch("tools.guest_runner.subprocess.Popen", return_value=process),
            mock.patch("tools.guest_runner.time", fake_time),
        ):
            result = run_guest(
                self.image,
                b"input",
                self.config(timeout=2.0),
                engine_path=engine,
            )

        self.assertEqual(result.status, GuestStatus.HALT)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"HALT steps=", result.stderr)

    def test_guest_still_running_when_the_deadline_fires_is_wall_timeout(self) -> None:
        process = _FakeProcess(stdout=b"", stderr=b"", exited=False)
        engine = self.root / "fake_bolge19"
        engine.write_bytes(b"x")
        ticks = iter([100.0, 103.0])
        fake_time = mock.Mock()
        fake_time.monotonic.side_effect = lambda: next(ticks, 2000.0)

        with (
            mock.patch("tools.guest_runner.subprocess.Popen", return_value=process),
            mock.patch("tools.guest_runner.time", fake_time),
        ):
            result = run_guest(
                self.image,
                b"input",
                self.config(timeout=2.0),
                engine_path=engine,
            )

        self.assertEqual(result.status, GuestStatus.WALL_TIMEOUT)
        self.assertIsNone(result.returncode)


if __name__ == "__main__":
    unittest.main()
