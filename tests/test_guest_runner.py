from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tools.guest_runner import GuestStatus, RunConfig, run_guest


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


if __name__ == "__main__":
    unittest.main()
