"""H1: relocation, and the loader-side walk that gates every emitted image."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from slopsynth.assemble import AssemblyError, assemble, layout_of
from slopsynth.canonical import canonical_accept_set, opcode_names, walk_canonical
from slopsynth.encode import encode_dispatch_sequence
from slopsynth.lang import parse_placed
from slopsynth.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "build" / "bolge19"


class CanonicalWalkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = load_profile(ROOT / "profiles" / "fixed19.json")

    def test_accept_set_is_the_profile_dispatch_itself(self) -> None:
        self.assertEqual(
            canonical_accept_set(self.profile),
            frozenset({4, 5, 23, 39, 40, 62, 68, 81}),
        )

    def test_the_certified_echo_image_walks_to_input_output_halt(self) -> None:
        walk = walk_canonical(b"ubO", self.profile)
        self.assertTrue(walk.accepted)
        self.assertEqual(walk.accepted_cells, 3)
        self.assertEqual(walk.opcodes, (23, 5, 81))
        self.assertEqual(opcode_names(walk.opcodes, self.profile), ("input", "output", "halt"))

    def test_spacing_is_skipped_without_advancing_the_position(self) -> None:
        for spaced in (b"u\nb O", b"u\r\nb\tO", b"   ubO\n\n"):
            with self.subTest(spaced=spaced):
                self.assertEqual(walk_canonical(spaced, self.profile).opcodes, (23, 5, 81))

    def test_a_non_dispatchable_byte_is_rejected_where_it_sits(self) -> None:
        walk = walk_canonical(b"u!", self.profile)
        self.assertFalse(walk.accepted)
        self.assertEqual(walk.rejected_offset, 1)
        self.assertEqual(walk.accepted_cells, 1)
        self.assertIn("not dispatchable", walk.reason)

    def test_a_byte_outside_the_printable_range_is_rejected(self) -> None:
        walk = walk_canonical(b"u\x00O", self.profile)
        self.assertFalse(walk.accepted)
        self.assertEqual(walk.rejected_offset, 1)
        self.assertIn("printable range", walk.reason)

    def test_the_position_cycle_wraps_at_564_cells(self) -> None:
        names = ["nop"] * 564 + ["input", "output", "halt"]
        image = encode_dispatch_sequence(names, self.profile)
        walk = walk_canonical(image, self.profile)
        self.assertTrue(walk.accepted)
        self.assertEqual(walk.opcodes[-3:], (23, 5, 81))
        self.assertEqual(image[564:567], b"ubO")

    def test_encoder_and_walk_agree_on_every_dispatchable_sequence(self) -> None:
        names = sorted(self.profile.dispatch)
        for length in (1, 7, 564, 565, 1200):
            for shift in (0, 3, 11):
                with self.subTest(length=length, shift=shift):
                    sequence = [names[(index + shift) % len(names)] for index in range(length)]
                    image = encode_dispatch_sequence(sequence, self.profile)
                    walk = walk_canonical(image, self.profile)
                    self.assertTrue(walk.accepted, walk.reason)
                    self.assertEqual(
                        walk.opcodes, tuple(self.profile.dispatch[name] for name in sequence)
                    )


class RelocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = load_profile(ROOT / "profiles" / "fixed19.json")

    def test_labels_resolve_to_the_cell_address_of_their_operation(self) -> None:
        placed = parse_placed("name off\nloop:\nat 564\nread\nwrite\nhalt\n")
        built = assemble(placed, self.profile)
        self.assertEqual(built.layout.addresses, (564, 565, 566))
        self.assertEqual(built.layout.labels, ((564, "loop"),))
        self.assertEqual(built.label_address("loop"), 564)
        self.assertEqual(built.layout.padded_cells, 564)
        self.assertEqual(built.cells, 567)
        self.assertEqual(built.walk.accepted_cells, 567)

    def test_spacing_only_changes_the_file_not_the_program(self) -> None:
        placed = parse_placed((ROOT / "examples" / "offset.slop").read_text(encoding="utf-8"))
        plain = assemble(placed, self.profile)
        formatted = assemble(placed, self.profile, line_width=20)
        self.assertEqual(formatted.image.replace(b"\n", b""), plain.image)
        self.assertEqual(formatted.walk.opcodes, plain.walk.opcodes)
        self.assertGreater(len(formatted.image), len(plain.image))

    def test_an_anchor_that_moves_backwards_is_refused(self) -> None:
        placed = parse_placed("name back\nread\nat 0\nwrite\nhalt\n")
        with self.assertRaises(AssemblyError) as caught:
            layout_of(placed)
        self.assertIn("moves backwards", str(caught.exception))

    def test_an_over_large_image_is_refused_instead_of_allocated(self) -> None:
        placed = parse_placed("name huge\nat 2000000\nhalt\n")
        with self.assertRaises(AssemblyError) as caught:
            layout_of(placed)
        self.assertIn("cell limit", str(caught.exception))

    def test_control_flow_is_refused_rather_than_invented(self) -> None:
        placed = parse_placed(
            "name m\ncase 30,30\nentry top\ntop:\n    read\n    jump top\n"
        )
        self.assertIsNone(placed.program)
        with self.assertRaises(AssemblyError) as caught:
            assemble(placed, self.profile)
        self.assertIn("no lowering", str(caught.exception))

    def test_a_register_other_than_a_is_refused_before_any_byte_is_emitted(self) -> None:
        placed = parse_placed("name b\nread B\nhalt\n")
        with self.assertRaises(AssemblyError):
            assemble(placed, self.profile)

    def test_assembled_images_contain_no_whitespace_unless_asked(self) -> None:
        placed = parse_placed("name w\nat 100\nread\nhalt\n")
        built = assemble(placed, self.profile)
        self.assertFalse(set(built.image) & set(self.profile.loaders["raw"].whitespace_bytes))


@unittest.skipUnless(ENGINE.is_file(), "build/bolge19 must be built before this test")
class EngineAgreementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = load_profile(ROOT / "profiles" / "fixed19.json")

    def run_image(self, image: bytes, stdin: bytes, loader: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "guest.mb"
            path.write_bytes(image)
            return subprocess.run(
                [str(ENGINE), str(path), "--loader", loader, "--max-steps", "100000"],
                input=stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
                check=False,
            )

    def test_the_relocated_guest_echoes_under_the_canonical_loader(self) -> None:
        placed = parse_placed((ROOT / "examples" / "offset.slop").read_text(encoding="utf-8"))
        for line_width in (None, 20):
            image = assemble(placed, self.profile, line_width=line_width).image
            for value in (b"3", b"A", b"\xff"):
                with self.subTest(line_width=line_width, value=value):
                    actual = self.run_image(image, value, "canonical")
                    self.assertEqual(actual.returncode, 0)
                    self.assertEqual(actual.stdout, value)
                    self.assertIn(b"HALT steps=566", actual.stderr)

    def test_spacing_that_the_canonical_loader_ignores_corrupts_the_raw_load(self) -> None:
        placed = parse_placed((ROOT / "examples" / "offset.slop").read_text(encoding="utf-8"))
        plain = assemble(placed, self.profile).image
        formatted = assemble(placed, self.profile, line_width=20).image

        for image in (plain, formatted):
            with self.subTest(len=len(image)):
                under_raw = self.run_image(image, b"3", "raw")
                under_canonical = self.run_image(image, b"3", "canonical")
                if image is plain:
                    self.assertEqual(under_raw.stdout, under_canonical.stdout)
                    self.assertNotIn(b"AVISO", under_raw.stderr)
                else:
                    self.assertEqual(under_canonical.stdout, b"3")
                    self.assertNotEqual(under_raw.stdout, under_canonical.stdout)
                    self.assertIn(b"AVISO", under_raw.stderr)
                    self.assertIn(b"imagen=596", under_raw.stderr)

    def test_the_engine_refuses_an_image_the_walk_refuses(self) -> None:
        for bad in (b"u!", b"ub\x00O", b"!bO"):
            with self.subTest(image=bad):
                walk = walk_canonical(bad, self.profile)
                self.assertFalse(walk.accepted)
                actual = self.run_image(bad, b"3", "canonical")
                self.assertEqual(actual.returncode, 2)
                self.assertIn(b"caracter invalido", actual.stderr)


if __name__ == "__main__":
    unittest.main()
