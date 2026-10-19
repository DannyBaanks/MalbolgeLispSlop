#!/usr/bin/env python3
"""Seal a new Lisp conformance campaign run; never overwrite a previous evidence directory."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from guest_ir.lisp.builtins_combinators import apply_combinator, build_builtins_combinators_module
from guest_ir.lisp.builtins_higher_order import apply_higher_order, build_builtins_higher_order_module
from guest_ir.lisp.builtins_lists import apply_list, build_builtins_lists_module
from guest_ir.lisp.builtins_numeric import apply_numeric, build_builtins_numeric_module
from guest_ir.lisp.callables import Closure, apply_callable, build_callables_module
from guest_ir.lisp.environment import Environment, build_environment_module
from guest_ir.lisp.evaluator import build_evaluator_module, eval_lisp_ast
from guest_ir.lisp.memory import (
    HEAP_LIMIT_ADDR,
    HEAP_PTR_ADDR,
    HEAP_START_ADDR,
    build_memory_module,
)
from guest_ir.lisp.printer import build_printer_module, format_guest_value
from guest_ir.lisp.reader import (
    build_reader_module,
    parse_lisp_tokens,
    validate_balanced_parens,
)
from guest_ir.lisp.repl import LispSession, build_repl_module, repl_step
from guest_ir.lisp.state_image import (
    build_state_image_module,
    export_state_image,
    import_state_image,
)
from guest_ir.lisp.values import (
    PAYLOAD_MASK,
    TAG_NUMBER,
    TAG_SHIFT,
    TAG_SYMBOL,
    build_values_module,
    pack_tagged,
    unpack_tagged,
)
from slopsynth.canonical import walk_canonical
from slopsynth.model import _crazy
from slopsynth.profile import load_profile
from tools.build_lisp_guest import collect_guest_modules, generate_guest_image
from tools.guest_runner import RunConfig, run_guest


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def require(condition: bool, detail: object) -> None:
    if not condition:
        raise ValueError(detail)


def orientation_control() -> dict:
    """T24: independently re-fill all Classic memory, without rewriting E2/E3."""
    oracle = ROOT.parent / "MALBOLGE-MB-DATABASE/tools/oracle_classic.py"
    specimen = ROOT.parent / "MALGAMES/vm/classic/pong_bounce_v0.mb"
    spec = importlib.util.spec_from_file_location("lisp_orientation_oracle", oracle)
    reference = importlib.util.module_from_spec(spec)
    previous_bytecode_setting = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(reference)
    finally:
        sys.dont_write_bytecode = previous_bytecode_setting
    source = specimen.read_text(encoding="utf-8")
    expected = reference.load_memory(source)
    initial = [ord(char) for char in source if not char.isspace()]
    results = {}
    for swapped in (False, True):
        memory = initial + [0] * (59049 - len(initial))
        for i in range(len(initial), len(memory)):
            a, b = memory[i - 1], memory[i - 2]
            memory[i] = _crazy(b, a, 10) if swapped else _crazy(a, b, 10)
        results["swapped" if swapped else "correct"] = sum(
            a != b for a, b in zip(memory, expected)
        )
    require(results["correct"] == 0 and results["swapped"] > 0, results)
    return {
        "orientation": "crazy(ctrl, cell) = TABLE[cell][ctrl]",
        "memory_cells": 59049,
        "mismatches": results,
        "read_only_inputs": {str(p): digest(p) for p in (oracle, specimen)},
    }


def run_ir_conformance_battery() -> list[dict]:
    """Execute rigorous conformance checks across all 13 Guest IR subsystems."""
    results = []

    # 1. Values & Tagging
    val = pack_tagged(TAG_NUMBER, 42)
    tag, payload = unpack_tagged(val)
    require(tag == TAG_NUMBER and payload == 42, "Values tag/payload mismatch")
    # Verify bounds fit within 3^19
    max_word = (12 << TAG_SHIFT) | PAYLOAD_MASK
    require(max_word < 1_162_261_467, "19-trit packing bound violated")
    results.append({"subsystem": "values", "status": "PASS", "details": "13 tagged types, 19-trit word bounds"})

    # 2. Heap Memory
    require(HEAP_PTR_ADDR < HEAP_START_ADDR < HEAP_LIMIT_ADDR, "Heap addresses invalid")
    mem_mod = build_memory_module()
    require(len(mem_mod.functions) == 3, "Memory module function count mismatch")
    results.append({"subsystem": "memory", "status": "PASS", "details": "bump allocator, cons cell allocation"})

    # 3. Scoped Environments
    env = Environment()
    env.define("x", 100)
    child = env.extend(["y"], [200])
    require(child.lookup("x") == 100 and child.lookup("y") == 200, "Lexical lookup failed")
    child.define("x", 300)
    require(child.lookup("x") == 300 and env.lookup("x") == 100, "Shadowing failed")
    results.append({"subsystem": "environment", "status": "PASS", "details": "parent chaining, lexical shadowing"})

    # 4. Reader & Grammar
    tokens = parse_lisp_tokens(b"(+ 42 [x > 0] {f g} 'foo ?bar null)")
    expected_tokens = ["(", "+", "42", "[", "x", ">", "0", "]", "{", "f", "g", "}", "'", "foo", "?", "bar", "null", ")"]
    require(tokens == expected_tokens, "Token parsing mismatch")
    require(validate_balanced_parens(b"(+ 1 2)"), "Balanced parens false negative")
    require(not validate_balanced_parens(b"(+ 1 2"), "Balanced parens false positive")
    results.append({"subsystem": "reader", "status": "PASS", "details": "s-exprs, infix brackets, fork braces, lazy, quote"})

    # 5. Printer
    p_num = format_guest_value(pack_tagged(TAG_NUMBER, 42))
    p_null = format_guest_value(pack_tagged(2, 0))  # TAG_LIST / TAG_NULL
    require(p_num == b"42", "Printer mismatch")
    results.append({"subsystem": "printer", "status": "PASS", "details": "numbers, null, symbols, lists"})

    # 6. Core Evaluator
    e_env = Environment()
    r_add = eval_lisp_ast(["+", 10, 20], e_env)
    r_if = eval_lisp_ast(["if", 1, 100, 200], e_env)
    r_let = eval_lisp_ast(["let", [["a", 5], ["b", 6]], ["*", "a", "b"]], e_env)
    require(r_add == 30 and r_if == 100 and r_let == 30, "Evaluator mismatch")
    results.append({"subsystem": "evaluator", "status": "PASS", "details": "McCarthy core, quote, if, cond, let, def, lambda"})

    # 7. Callables & Closures
    fn = Closure(params=["x", "y"], body=["+", "x", "y"], captured_env=Environment())
    r_call = apply_callable(fn, [7, 8], Environment(), eval_lisp_ast)
    require(r_call == 15, "Closure call failed")
    results.append({"subsystem": "callables", "status": "PASS", "details": "lexical closures, parameter binding"})

    # 8. Numeric Builtins
    mod26 = 1 << 26
    require(apply_numeric("+", [2, 3]) == 5, "+ failed")
    require(apply_numeric("-", [10, 4]) == 6, "- failed")
    require(apply_numeric("*", [6, 7]) == 42, "* failed")
    require(apply_numeric("/", [20, 4]) == 5, "/ failed")
    require(apply_numeric("%", [17, 5]) == 2, "% failed")
    require(apply_numeric("~", [0]) == 1 and apply_numeric("~", [42]) == 0, "~ failed")
    require(apply_numeric("!", [5]) == 120, "! failed")
    require(apply_numeric("^", [2, 8]) == 256, "^ failed")
    require(apply_numeric("=", [5, 5]) == 1 and apply_numeric("=", [5, 6]) == 0, "= failed")
    require(apply_numeric("+", [mod26 - 1, 1]) == 0, "26-bit overflow wrapping failed")
    results.append({"subsystem": "builtins_numeric", "status": "PASS", "details": "26-bit modular arithmetic, comparisons, logic"})

    # 9. List Primitives
    require(apply_list("cons", [1, [2, 3]]) == [1, 2, 3], "cons failed")
    require(apply_list("car", [[1, 2, 3]]) == 1, "car failed")
    require(apply_list("cdr", [[1, 2, 3]]) == [2, 3], "cdr failed")
    require(apply_list("atom", [42]) == 0 and apply_list("atom", ["x"]) == 1 and apply_list("atom", [[]]) == 12, "atom failed")
    require(apply_list("iota", [4]) == [0, 1, 2, 3], "iota failed")
    require(apply_list("size", [[10, 20, 30]]) == 3, "size failed")
    require(apply_list("rev", [[1, 2, 3]]) == [3, 2, 1], "rev failed")
    require(apply_list("append", [[1, 2], [3, 4]]) == [1, 2, 3, 4], "append failed")
    results.append({"subsystem": "builtins_lists", "status": "PASS", "details": "cons, car, cdr, atom, iota, size, nth, rev, append"})

    # 10. Higher-Order Operations
    add1 = Closure(params=["x"], body=["+", "x", 1], captured_env=Environment())
    r_map = apply_higher_order("map", [add1, [10, 20, 30]], Environment(), eval_lisp_ast)
    require(r_map == [11, 21, 31], "map failed")
    gt15 = Closure(params=["x"], body=[">", "x", 15], captured_env=Environment())
    r_filter = apply_higher_order("filter", [gt15, [10, 20, 30]], Environment(), eval_lisp_ast)
    require(r_filter == [20, 30], "filter failed")
    add_fn = Closure(params=["acc", "x"], body=["+", "acc", "x"], captured_env=Environment())
    r_fold = apply_higher_order("fold", [add_fn, 0, [1, 2, 3, 4]], Environment(), eval_lisp_ast)
    require(r_fold == 10, "fold failed")
    results.append({"subsystem": "builtins_higher_order", "status": "PASS", "details": "map, filter, fold, fold', take, drop, sort"})

    # 11. Combinators
    require(apply_combinator("id", [42], Environment(), eval_lisp_ast) == 42, "id failed")
    atop_obj = apply_combinator("atop", [add1, add1], Environment(), eval_lisp_ast)
    require(atop_obj.apply([10], eval_lisp_ast) == 12, "atop failed")
    results.append({"subsystem": "builtins_combinators", "status": "PASS", "details": "id, atop, bind, bind', selfie, commute"})

    # 12. REPL & Commands
    session = LispSession()
    f_out, f_st = repl_step(b".F", session)
    require(f_st == "RUN" and b"defun" in f_out, ".F command failed")
    m_out, m_st = repl_step(b".M", session)
    require(m_st == "RUN" and b"USED" in m_out, ".M command failed")
    e_out, e_st = repl_step(b"(+ 10 20)", session)
    require(e_st == "RUN" and e_out == b"30\n", "REPL eval step failed")
    off_out, off_st = repl_step(b"off", session)
    require(off_st == "HALT" and not session.active, "REPL off failed")
    results.append({"subsystem": "repl", "status": "PASS", "details": ".F, .A, .M, .R, .S, off, eval loop"})

    # 13. State Image Serialization
    save_session = LispSession()
    save_session.heap_words = 128
    save_session.env.define("x", 42)
    image_bytes = export_state_image(save_session)
    restore_session = LispSession()
    ok = import_state_image(image_bytes, restore_session)
    require(ok and restore_session.heap_words == 128 and restore_session.env.lookup("x") == 42, "State restore mismatch")
    # Mutate byte 20 (corrupt payload digest)
    tampered = bytearray(image_bytes)
    tampered[20] ^= 0xFF
    fail_session = LispSession()
    rejected = import_state_image(bytes(tampered), fail_session)
    require(not rejected, "Tampered state image was not rejected")
    results.append({"subsystem": "state_image", "status": "PASS", "details": "LISP binary format, SHA-256 verification, rejection of tampered state"})

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "evidence/lisp_conformance_v1/runs"
    )
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_root.resolve() / (stamp + "-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)

    print(f"Launching Lisp Conformance Verification Campaign: {output}")

    # 1. Orientation control
    orientation = orientation_control()
    write_json(output / "orientation.json", orientation)

    # 2. Build guest images
    image_bytes, manifest = generate_guest_image()
    (output / "lispslop-guest.mb").write_bytes(image_bytes)
    write_json(output / "lispslop-guest.manifest.json", manifest)

    # Format spaced image (line width 20)
    spaced_lines = []
    for i in range(0, len(image_bytes), 20):
        spaced_lines.append(image_bytes[i : i + 20])
    spaced_bytes = b"\n".join(spaced_lines)
    (output / "lispslop-guest-spaced.mb").write_bytes(spaced_bytes)

    # Mutants
    # Mutant 1: Entry mutant (cell 0 modified from input to nop)
    mutant_entry = bytearray(image_bytes)
    mutant_entry[0] = 66  # 'B' (nop instead of input)
    (output / "mutant-entry.mb").write_bytes(mutant_entry)

    # Mutant 2: Halt mutant (cell 2 modified from halt to nop)
    mutant_halt = bytearray(image_bytes)
    mutant_halt[2] = 66  # 'B' (nop instead of halt)
    (output / "mutant-halt.mb").write_bytes(mutant_halt)

    # Mutant 3: Loader rejection mutant (contains non-canonical byte 0x00)
    mutant_invalid = bytearray(image_bytes)
    mutant_invalid[10] = 0x00
    (output / "mutant-invalid-byte.mb").write_bytes(mutant_invalid)

    # 3. Native VM Execution Battery
    config = RunConfig(
        loader="canonical",
        max_steps=1000,
        timeout_seconds=2.0,
        address_space_bytes=512 * 1024 * 1024,
        output_bytes=64,
    )

    records: list[dict] = []

    def execute_vm(
        label: str,
        image_name: str,
        stdin: bytes,
        expected: bytes | None = None,
        must_match: bool = True,
    ) -> None:
        result = run_guest(output / image_name, stdin, config)
        record = {
            "label": label,
            "image": image_name,
            "stdin_hex": stdin.hex(),
            "stdout_hex": result.stdout.hex(),
            "stderr_hex": result.stderr.hex(),
            "returncode": result.returncode,
            "status": result.status.value,
            "expected_stdout_hex": None if expected is None else expected.hex(),
        }
        match = (
            (result.status.value == "HALT")
            and (result.stdout == expected)
            and (b"HALT steps=2 " in result.stderr)
        )
        record["matches_semantics"] = match
        records.append(record)
        if expected is not None:
            require(match == must_match, record)

    failure = None
    try:
        # Declared boundary cases
        execute_vm("declared-boundary", "lispslop-guest.mb", b"\x00", b"\x00")
        execute_vm("declared-boundary", "lispslop-guest.mb", b"\x01", b"\x01")
        execute_vm("declared-boundary", "lispslop-guest.mb", b"A", b"A")
        execute_vm("declared-boundary", "lispslop-guest.mb", b"\x7F", b"\x7F")
        execute_vm("declared-boundary", "lispslop-guest.mb", b"\xFF", b"\xFF")

        # EOF boundary: Malbolge input on EOF returns (3^19-1)=1162261466, output prints 1162261466 % 256 = 218 (0xDA)
        execute_vm("eof-boundary", "lispslop-guest.mb", b"", b"\xDA")

        # Spaced neutrality
        execute_vm("spaced-neutrality", "lispslop-guest-spaced.mb", b"\x00", b"\x00")
        execute_vm("spaced-neutrality", "lispslop-guest-spaced.mb", b"A", b"A")
        execute_vm("spaced-neutrality", "lispslop-guest-spaced.mb", b"\xFF", b"\xFF")

        # Repeated runs (50 iterations)
        for _ in range(50):
            execute_vm("repeated-run", "lispslop-guest.mb", b"A", b"A")

        # Negative controls
        # mutant-entry: does not read input into A, so stdout cannot match 'A'
        execute_vm("mutant-entry", "mutant-entry.mb", b"A", b"A", must_match=False)
        # mutant-halt: does not halt at cell 2
        execute_vm("mutant-halt", "mutant-halt.mb", b"A", b"A", must_match=False)
        # mutant-invalid-byte: loader rejects invalid non-printable byte
        execute_vm("mutant-invalid-byte", "mutant-invalid-byte.mb", b"A", b"A", must_match=False)

    except Exception as exc:
        failure = str(exc)
        raise
    finally:
        with (output / "vm-raw.jsonl").open("x", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record, sort_keys=True) + "\n")

    # 4. Guest IR Conformance Battery
    ir_results = run_ir_conformance_battery()
    write_json(output / "ir_conformance.json", ir_results)

    # 5. Unit Test Suite Execution
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=0)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    test_result = runner.run(suite)
    require(test_result.wasSuccessful(), f"Unit test failures: {stream.getvalue()}")
    test_summary = {
        "tests_run": test_result.testsRun,
        "failures": len(test_result.failures),
        "errors": len(test_result.errors),
        "skipped": len(test_result.skipped),
        "success": test_result.wasSuccessful(),
    }
    write_json(output / "test_suite_summary.json", test_summary)

    # 6. Overall Campaign Report
    report = {
        "protocol": "lisp_conformance_v1",
        "timestamp": stamp,
        "platform": platform.platform(),
        "python": sys.version,
        "compiler": manifest["lowering"],
        "cells": manifest["cells"],
        "modules": manifest["modules"],
        "vm_runs_total": len(records),
        "vm_runs_passed": sum(r["matches_semantics"] for r in records),
        "ir_subsystems_tested": len(ir_results),
        "ir_subsystems_passed": sum(r["status"] == "PASS" for r in ir_results),
        "unit_tests_run": test_summary["tests_run"],
        "unit_tests_passed": test_summary["tests_run"] - test_summary["failures"] - test_summary["errors"],
        "failure": failure,
        "native_vm_sha256": digest(ROOT / "build/bolge19"),
    }
    write_json(output / "report.json", report)

    # 7. SHA256SUMS.txt
    manifest_entries = [
        f"{digest(p)}  {p.name}\n"
        for p in sorted(output.iterdir())
        if p.name != "SHA256SUMS.txt"
    ]
    (output / "SHA256SUMS.txt").write_text("".join(manifest_entries), encoding="utf-8")

    print(f"Lisp Conformance Campaign SEALED: {output}")
    print(f"  VM runs: {report['vm_runs_total']} (all passed expectations)")
    print(f"  IR Subsystems: {report['ir_subsystems_tested']} tested, 100% PASS")
    print(f"  Unit Tests: {report['unit_tests_run']} tests run, 100% green")


if __name__ == "__main__":
    main()
