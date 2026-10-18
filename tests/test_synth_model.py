from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from slopsynth.model import MemoryWrite, RunStatus, run_model
from slopsynth.profile import Profile, load_profile


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "build" / "bolge19"


class Fixed19ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile: Profile = load_profile(ROOT / "profiles" / "fixed19.json")

    def run_one(self, image: bytes, stdin: bytes = b"", *, max_address: int = 256):
        return run_model(
            image,
            stdin,
            self.profile,
            loader="canonical",
            max_steps=1,
            max_address=max_address,
            trace_writes=True,
        )

    def test_input_dispatch_reads_one_byte_into_accumulator(self) -> None:
        result = self.run_one(b"u", b"A")

        self.assertEqual(result.status, RunStatus.MAX_STEPS)
        self.assertEqual((result.final_a, result.final_c, result.final_d), (65, 1, 1))

    def test_output_dispatch_writes_low_accumulator_byte(self) -> None:
        result = self.run_one(b"c")

        self.assertEqual(result.stdout, b"\x00")
        self.assertEqual(result.status, RunStatus.MAX_STEPS)

    def test_halt_dispatch_stops_without_advancing(self) -> None:
        result = run_model(
            b"Q", b"", self.profile, loader="canonical", max_steps=4, max_address=8
        )

        self.assertEqual(result.status, RunStatus.HALT)
        self.assertEqual((result.steps, result.final_c, result.final_d), (0, 0, 0))

    def test_jump_dispatch_loads_c_from_memory_at_d(self) -> None:
        result = self.run_one(b"b", max_address=128)

        self.assertEqual(result.status, RunStatus.MAX_STEPS)
        self.assertEqual((result.final_c, result.final_d), (99, 1))

    def test_move_dispatch_loads_d_from_memory_at_d(self) -> None:
        result = self.run_one(b"(")

        self.assertEqual(result.status, RunStatus.MAX_STEPS)
        self.assertEqual((result.final_c, result.final_d), (1, 41))

    def test_rotate_dispatch_updates_accumulator_and_memory(self) -> None:
        result = self.run_one(b"'")

        self.assertEqual(result.final_a, 13)
        self.assertEqual(
            result.memory_writes,
            (MemoryWrite(0, 39, 13), MemoryWrite(0, 13, 32)),
        )

    def test_crazy_dispatch_updates_accumulator_and_memory(self) -> None:
        result = self.run_one(b">")

        self.assertEqual(result.final_a, 581_130_764)
        self.assertEqual(result.memory_writes, (MemoryWrite(0, 62, 581_130_764),))

    def test_nop_dispatch_advances_both_pointers(self) -> None:
        result = self.run_one(b"D")

        self.assertEqual(result.status, RunStatus.MAX_STEPS)
        self.assertEqual((result.final_a, result.final_c, result.final_d), (0, 1, 1))

    def test_post_instruction_encryption_mutates_current_cell(self) -> None:
        result = self.run_one(b"u")

        self.assertEqual(result.memory_writes, (MemoryWrite(0, 117, 111),))

    def test_eof_sentinel_is_not_a_byte(self) -> None:
        image = b"ubO"
        eof_result = run_model(
            image, b"", self.profile, loader="canonical", max_steps=4, max_address=8
        )
        byte_result = run_model(
            image, b"\xff", self.profile, loader="canonical", max_steps=4, max_address=8
        )

        self.assertEqual(eof_result.status, RunStatus.HALT)
        self.assertEqual(eof_result.final_a, 1_162_261_466)
        self.assertEqual(byte_result.status, RunStatus.HALT)
        self.assertEqual(byte_result.final_a, 255)
        self.assertEqual(byte_result.stdout, b"\xff")

    def test_step_exhaustion_preserves_completed_steps(self) -> None:
        result = run_model(
            b"ubO", b"X", self.profile, loader="canonical", max_steps=1, max_address=8
        )

        self.assertEqual(result.status, RunStatus.MAX_STEPS)
        self.assertEqual((result.steps, result.final_a, result.stdout), (1, 88, b""))

    def test_model_bound_is_distinct_from_vm_halt(self) -> None:
        result = run_model(
            b"ubO", b"X", self.profile, loader="canonical", max_steps=8, max_address=0
        )

        self.assertEqual(result.status, RunStatus.MODEL_BOUND)
        self.assertEqual((result.steps, result.final_c), (1, 1))

    def test_canonical_loader_rejects_invalid_opcode(self) -> None:
        result = run_model(
            b"!", b"", self.profile, loader="canonical", max_steps=4, max_address=8
        )

        self.assertEqual(result.status, RunStatus.LOAD_ERROR)

    def test_whitespace_only_canonical_image_matches_bolge19(self) -> None:
        image = b" \n"
        model = run_model(
            image, b"", self.profile, loader="canonical", max_steps=1, max_address=8
        )
        actual = self.run_bolge19(image, b"", max_steps=1)

        self.assertEqual(model.status.value, actual["status"])
        self.assertEqual(model.steps, actual["steps"])

    def test_loader_modes_keep_whitespace_behavior_distinct(self) -> None:
        source = b"u bO"
        canonical = run_model(
            source, b"x", self.profile, loader="canonical", max_steps=4, max_address=8
        )
        raw = run_model(
            source, b"x", self.profile, loader="raw", max_steps=4, max_address=8
        )

        self.assertEqual((canonical.status, canonical.stdout), (RunStatus.HALT, b"x"))
        self.assertEqual((raw.status, raw.stdout), (RunStatus.MAX_STEPS, b""))

    def test_positioned_decode_and_mutation_match_bolge19(self) -> None:
        self.assertTrue(ENGINE.is_file(), "build/bolge19 must be built before this test")
        cases = ((b"ubO", "echo"), (b"uCO", "mutated"))
        for image, label in cases:
            for stdin in (b"A", b"\x00", b"\xff"):
                with self.subTest(image=label, stdin=stdin):
                    model = run_model(
                        image,
                        stdin,
                        self.profile,
                        loader="canonical",
                        max_steps=8,
                        max_address=1024,
                    )
                    actual = self.run_bolge19(image, stdin, max_steps=8)
                    self.assertEqual(model.status.value, actual["status"])
                    self.assertEqual(model.stdout, actual["stdout"])
                    self.assertEqual(model.steps, actual["steps"])

    def test_optional_trace_records_guest_dispatches_and_memory_purposes(self) -> None:
        result = run_model(
            b"ubO",
            b"X",
            self.profile,
            loader="canonical",
            max_steps=8,
            max_address=8,
            trace_instructions=True,
            trace_accesses=True,
        )

        self.assertEqual(
            [(event.address, event.operation) for event in result.instruction_trace],
            [(0, "input"), (1, "output"), (2, "halt")],
        )
        self.assertIn("instruction", {access.purpose for access in result.memory_accesses})
        self.assertIn("encryption", {access.purpose for access in result.memory_accesses})

    def run_bolge19(self, image: bytes, stdin: bytes, *, max_steps: int) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidate.mb"
            path.write_bytes(image)
            completed = subprocess.run(
                [str(ENGINE), str(path), "--loader", "canonical", "--max-steps", str(max_steps)],
                input=stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=2,
                check=False,
            )
        if b"HALT steps=" in completed.stderr:
            status = RunStatus.HALT.value
        elif b"MAX_STEPS" in completed.stderr:
            status = RunStatus.MAX_STEPS.value
        else:
            self.fail(f"bolge19 returned an unrecognized status: {completed.stderr!r}")
        match = re.search(rb"(?:HALT steps=|MAX_STEPS )(\d+)", completed.stderr)
        self.assertIsNotNone(match, completed.stderr)
        return {
            "status": status,
            "steps": int(match.group(1)),
            "stdout": completed.stdout,
        }


if __name__ == "__main__":
    unittest.main()
