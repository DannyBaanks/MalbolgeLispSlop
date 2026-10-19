"""H0: the textual guest front-end must reach the IR the JSON contracts already reach."""

from __future__ import annotations

from pathlib import Path
import unittest

from slopsynth.encode import encode_program
from slopsynth.ir import Halt, Program, ReadA, WriteA
from slopsynth.ir_json import load_program
from slopsynth.lang import LangError, format_placed, format_program, parse, parse_placed
from slopsynth.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]


class H0EchoIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = load_profile(ROOT / "profiles" / "fixed19.json")

    def test_text_echo_parses_to_the_same_program_as_the_json_contract(self) -> None:
        from_text = parse((ROOT / "examples" / "echo.slop").read_text(encoding="utf-8"))
        from_json = load_program(ROOT / "examples" / "echo.json")

        self.assertIsInstance(from_text, Program)
        self.assertEqual(from_text, from_json)
        self.assertEqual(encode_program(from_text, self.profile), b"ubO")

    def test_encoder_output_is_reachable_from_the_text_alone(self) -> None:
        placed = parse_placed("name echo\nread\nwrite\nhalt\n")
        self.assertEqual(placed.labels, ())
        self.assertEqual(placed.anchors, ())
        self.assertEqual(encode_program(placed.program, self.profile), b"ubO")

    def test_format_round_trips_every_example(self) -> None:
        for path in sorted((ROOT / "examples").glob("*.slop")):
            with self.subTest(example=path.name):
                placed = parse_placed(path.read_text(encoding="utf-8"))
                self.assertEqual(parse_placed(format_placed(placed)), placed)

    def test_format_program_renders_the_default_register_implicitly(self) -> None:
        program = Program(name="echo", operations=(ReadA(), WriteA(), Halt()))
        self.assertEqual(format_program(program), "name echo\nread\nwrite\nhalt\n")
        self.assertEqual(parse(format_program(program)), program)


class GrammarTests(unittest.TestCase):
    def test_comments_blank_lines_and_case_are_ignored(self) -> None:
        placed = parse_placed(
            "; leading comment\n\nNAME Echo ; trailing\n  Read\nWrite\nHalt\n"
        )
        self.assertEqual(placed.name, "Echo")
        self.assertEqual(placed.program.operations, (ReadA(), WriteA(), Halt()))

    def test_named_registers_parse_into_the_ir_and_are_refused_by_the_backend(self) -> None:
        placed = parse_placed("name r\nread B\nwrite B\nhalt\n")
        self.assertEqual(placed.program.operations, (ReadA("B"), WriteA("B"), Halt()))

    def test_unknown_mnemonic_reports_its_line(self) -> None:
        with self.assertRaises(LangError) as caught:
            parse_placed("name g\nfrobnicate\nhalt\n")
        self.assertEqual(caught.exception.line, 2)
        self.assertIn("unknown mnemonic", caught.exception.message)

    def test_call_and_return_parse_into_ir(self) -> None:
        source = (
            "name g\ncase 00,00\nentry main\nmain:\n"
            "    read x\n    call y, identity, x\n    write y\n    halt\n"
            "identity:\n    ret x\n"
        )
        placed = parse_placed(source)
        self.assertIsNotNone(placed.module)
        self.assertEqual(len(placed.module.functions), 2)
        caller = placed.module.functions[0]
        callee = placed.module.functions[1]
        self.assertEqual(caller.name, "main")
        self.assertEqual(callee.name, "identity")

    def test_name_is_mandatory_and_unique(self) -> None:
        with self.assertRaises(LangError):
            parse_placed("read\nhalt\n")
        with self.assertRaises(LangError):
            parse_placed("name a\nname b\nhalt\n")

    def test_a_label_without_an_operation_after_it_is_rejected(self) -> None:
        with self.assertRaises(LangError) as caught:
            parse_placed("name a\nhalt\ntrailing:\n")
        self.assertIn("without an operation", caught.exception.message)

    def test_duplicate_labels_are_rejected(self) -> None:
        with self.assertRaises(LangError):
            parse_placed("name a\nx:\nread\nx:\nhalt\n")

    def test_at_requires_a_bounded_absolute_address(self) -> None:
        with self.assertRaises(LangError):
            parse_placed("name a\nat -1\nhalt\n")
        with self.assertRaises(LangError):
            parse_placed("name a\nat 1162261467\nhalt\n")
        with self.assertRaises(LangError):
            parse_placed("name a\nat 10\nat 20\nhalt\n")

    def test_line_length_is_bounded(self) -> None:
        with self.assertRaises(LangError):
            parse_placed("name a\n" + "read" + (";" + "x" * 5000) + "\n")

    def test_operands_must_be_comma_separated_and_non_empty(self) -> None:
        with self.assertRaises(LangError):
            parse_placed("name a\nadd A,B,\nhalt\n")


class ModuleShapeTests(unittest.TestCase):
    def test_control_flow_parses_into_a_module_with_cases(self) -> None:
        placed = parse_placed(
            "name counter\n"
            "case 30,30\n"
            "entry top\n"
            "top:\n"
            "    read\n"
            "    brz A, zero, done\n"
            "zero:\n"
            "    add A, 0, 1\n"
            "    jump top\n"
            "done:\n"
            "    halt\n"
        )
        self.assertIsNone(placed.program)
        module = placed.module
        self.assertEqual(len(module.cases), 1)
        self.assertEqual(module.cases[0].stdin, b"0")
        self.assertEqual(module.cases[0].stdout, b"0")
        self.assertEqual(
            [block.name for block in module.functions[0].blocks],
            ["top", "zero", "done"],
        )

    def test_a_module_needs_cases_and_an_entry(self) -> None:
        with self.assertRaises(LangError) as caught:
            parse_placed("name m\ntop:\n    jump top\n")
        self.assertIn("at least one case", caught.exception.message)
        with self.assertRaises(LangError) as caught:
            parse_placed("name m\ncase 00,00\ntop:\n    halt\n")
        self.assertIn("entry label", caught.exception.message)

    def test_irregular_control_flow_surfaces_as_a_line_diagnostic_not_a_bare_valueerror(self) -> None:
        for source in (
            "name m\ncase 00,00\nentry top\ntop:\n    jump nowhere\n",
            "name m\ncase 00,00\nentry ghost\ntop:\n    halt\n",
            "name m\nentry top\ntop:\n    halt\n",
        ):
            with self.subTest(source=source):
                with self.assertRaises(LangError):
                    parse_placed(source)

    def test_absolute_addresses_do_not_belong_to_a_module(self) -> None:
        with self.assertRaises(LangError) as caught:
            parse_placed(
                "name m\ncase 00,00\nentry top\nat 10\ntop:\n    halt\n"
            )
        self.assertIn("straight-line", caught.exception.message)

    def test_operations_before_the_first_label_are_rejected(self) -> None:
        with self.assertRaises(LangError) as caught:
            parse_placed("name m\ncase 00,00\nentry top\nread\ntop:\n    halt\n")
        self.assertIn("before the first label", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
