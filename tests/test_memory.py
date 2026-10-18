"""Tests for Gate H4 scoped native memory store/load lowering."""

from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

from slopsynth.assemble import AssemblyError
from slopsynth.lang import parse_placed
from slopsynth.memory import lower_memory
from slopsynth.model import RunStatus, run_model
from slopsynth.profile import Profile, load_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "profiles" / "fixed19.json"
SLOP_PATH = ROOT / "examples" / "store_load.slop"
VM_PATH = ROOT / "build" / "bolge19"


class MemoryLoweringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = load_profile(PROFILE_PATH)
        cls.placed = parse_placed(SLOP_PATH.read_text(encoding="utf-8"))
        assert cls.placed.module is not None
        cls.module = cls.placed.module

    def test_lower_memory_produces_canonical_accepted_image(self) -> None:
        built = lower_memory(self.module, self.profile)
        self.assertEqual(built.cells, 259)
        self.assertTrue(built.walk.accepted)
        self.assertEqual(built.lowering, "fixed19-scoped-memory-v1")
        self.assertEqual(built.labels, (("main", (103, 104)),))

    def test_model_execution_byte_exact(self) -> None:
        built = lower_memory(self.module, self.profile)
        test_bytes = [0x00, 0x01, 0x41, 0x7F, 0xAA, 0xFE, 0xFF]
        for b in test_bytes:
            res = run_model(
                built.image,
                bytes((b,)),
                self.profile,
                loader="canonical",
                max_steps=256,
                max_address=built.cells,
            )
            self.assertEqual(res.status, RunStatus.HALT)
            self.assertEqual(res.stdout, bytes((b,)))

    def test_native_bolge19_execution(self) -> None:
        import tempfile
        from tools.guest_runner import RunConfig, run_guest
        if not VM_PATH.is_file():
            self.skipTest("build/bolge19 not built")
        built = lower_memory(self.module, self.profile)
        config = RunConfig("canonical", 512, 5, 512 * 1024 * 1024, 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "store_load.mb"
            path.write_bytes(built.image)
            test_bytes = [0x00, 0x01, 0x41, 0x7F, 0xAA, 0xFF]
            for b in test_bytes:
                inp = bytes((b,))
                res = run_guest(path, inp, config)
                self.assertEqual(res.status.value, "HALT")
                self.assertEqual(res.stdout, inp)
                self.assertIn(b"HALT steps=8 ", res.stderr)

    def test_refuses_address_mismatch(self) -> None:
        bad_slop = """name bad_addr
entry main
case 00,00
main:
    read A
    st 32, A
    ld A, 33
    write A
    halt
"""
        placed = parse_placed(bad_slop)
        assert placed.module is not None
        with self.assertRaisesRegex(AssemblyError, "does not match load address"):
            lower_memory(placed.module, self.profile)

    def test_refuses_case_contradiction(self) -> None:
        bad_slop = """name bad_case
entry main
case 00,ff
main:
    read A
    st 32, A
    ld A, 32
    write A
    halt
"""
        placed = parse_placed(bad_slop)
        assert placed.module is not None
        with self.assertRaisesRegex(AssemblyError, "contradicts"):
            lower_memory(placed.module, self.profile)

    def test_refuses_profile_mismatch(self) -> None:
        custom_profile = Profile(
            name="other",
            trits=19,
            end=1162261467,
            eof_value=1162261466,
            dispatch=self.profile.dispatch,
            loaders=self.profile.loaders,
        )
        with self.assertRaisesRegex(AssemblyError, "exact bundled fixed19 profile"):
            lower_memory(self.module, custom_profile)


if __name__ == "__main__":
    unittest.main()
