# Guest Lisp Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a complete, independently specified Lisp dialect whose parser, evaluator, built-ins, REPL, and state commands execute in a generated fixed-`3^19` guest.

**Architecture:** A host-only reference evaluator supplies expected results for the conformance suite. Readable guest IR modules describe the actual reader, value model, evaluator, primitives, and REPL; the fixed-19 synthesis compiler emits the Malbolge image. `guest_runner` executes that image and never calls the reference evaluator.

**Tech Stack:** Python 3.12 standard library for the reference model, guest IR builders, and harness; Zig 0.16.0 `bolge19` for guest execution; `unittest` for tests.

**Spec:** [SYSTEM_SPEC.md](../../SYSTEM_SPEC.md)

## Global Constraints

- Do not start guest-runtime implementation until the synthesis plan demonstrates input-dependent branching, arithmetic, load/store, bounded loops, and calls/returns.
- Product target is fixed-`3^19`; do not claim dynamic-width Unshackled or Malbolge Free compatibility.
- All target instruction bytes and reusable blocks come from the synthesis compiler; guest IR is readable host-side source, never a hand-written Malbolge image.
- A host Lisp model is an oracle for expected results only. `tools/guest_runner.py` must execute the generated guest and must not import or call the reference model.
- No MalbolgeLISP upstream code, image, or manual is copied. Define an original semantic contract using historical documentation only as a feature inventory.
- Keep the Python host toolchain on the standard library. Record raw stdout/stderr, status, image digest, step limit, loader, and resource limits for each evidence run.
- Mark each feature `SPECIFIED`, `IMPLEMENTED`, and `DEMONSTRATED` separately; no aggregate “complete” label while a promised feature lacks guest evidence.

## Review Focus

- Reader handling of EOF, non-ASCII bytes, and truncated forms: pin with `test_guest_reader_rejects_truncated_and_invalid_input`.
- Lexical scope and shadowing in nested closures: pin with `test_guest_closure_uses_lexical_environment`.
- Invalid arity, type, and bounds behavior: pin with `test_guest_errors_match_feature_matrix`.
- Corrupt or truncated imported state: pin with `test_guest_import_rejects_invalid_image`.
- Guest timeout or step exhaustion accidentally reported as HALT: pin with `test_conformance_keeps_terminal_statuses_distinct`.

---

### Task 1: Freeze the language contract and feature matrix

**Files:**
- Create: `spec/lisp-language-v1.md`
- Create: `spec/lisp-feature-matrix.json`
- Create: `tools/check_feature_matrix.py`
- Create: `tests/test_lisp_feature_matrix.py`

**Interfaces:**
- Each matrix entry has `id`, `surface`, `category`, `semantics`, `positive_cases`, `negative_cases`, and `guest_test_ids`. Each case records expected bytes/status and positive `max_steps`, `timeout_seconds`, `address_space_bytes`, and `output_bytes` limits.
- Include every documented syntax form, value type, built-in name and overload, REPL command, state command, and specified error class. Keep the inventory as data so omitted features are visible.
- For each behavior, write exact input bytes, expected output bytes, expected terminal status, and any state carried to the next expression. Label unresolved historical details `OPEN`; they cannot be claimed as implemented.

- [ ] Write `test_matrix_ids_are_unique`, `test_every_feature_has_semantics_and_cases`, and `test_every_matrix_case_names_a_guest_test`.
- [ ] Run: `python3 -m unittest tests.test_lisp_feature_matrix -v`.
  Expected: FAIL because the matrix and checker do not exist.
- [ ] Author the independent language contract and matrix. Pin numeric range/overflow, reader grammar, evaluation order, truth values, printer format, EOF/encoding, error behavior, and state import/export format.
- [ ] Run: `python3 -m unittest tests.test_lisp_feature_matrix -v`.
  Expected: PASS; the checker rejects duplicate IDs, missing semantics, missing positive/negative cases, and undocumented test IDs.
- [ ] Commit with `docs: specify complete LispSlop language surface`.

### Task 2: Build the host-only reference evaluator

**Files:**
- Create: `reference/__init__.py`
- Create: `reference/lisp_reference.py`
- Create: `tests/reference/__init__.py`
- Create: `tests/reference/test_reader.py`
- Create: `tests/reference/test_evaluator.py`
- Create: `tests/reference/test_builtins.py`

**Interfaces:**
- Produces `parse_forms(source: bytes) -> tuple[Expr, ...]`.
- Produces `evaluate(expr: Expr, env: Environment) -> Value` and `format_value(value: Value) -> bytes`.
- The reference module is imported only by tests and `tools/run_lisp_conformance.py` when calculating expected results. It is not imported by `tools/guest_runner.py` or the generated guest.

- [ ] Write reader tests for numbers, symbols, null, quoted/lazy forms, nested parentheses, square forms, fork forms, indexed forms, comments, invalid bytes, and truncated lists.
- [ ] Run: `python3 -m unittest tests.reference.test_reader -v`.
  Expected: FAIL because the reference reader is absent.
- [ ] Implement the reader and formatter from `spec/lisp-language-v1.md` without copying upstream source or manual text.
- [ ] Run: `python3 -m unittest tests.reference.test_reader -v`.
  Expected: PASS; valid forms round-trip under the specified normalization and invalid input returns the matrix error.
- [ ] Add evaluator tests for the core forms and built-in tests in the same feature groups used by the matrix.
- [ ] Run: `python3 -m unittest tests.reference -v`.
  Expected: PASS for every reference-model case. These tests do not establish guest execution.
- [ ] Commit with `feat: add LispSlop reference oracle`.

### Task 3: Add the guest conformance runner

**Files:**
- Create: `tools/run_lisp_conformance.py`
- Create: `tests/guest/__init__.py`
- Create: `tests/test_lisp_conformance_runner.py`
- Modify: `Makefile`

**Interfaces:**
- Consume `RunConfig`, `GuestResult`, and `run_guest(image: Path, stdin: bytes, config: RunConfig)` from the synthesis-backend plan.
- Produce `run_matrix(matrix_path: Path, image: Path, evidence_root: Path) -> dict`; it builds each `RunConfig` from the limits recorded for that case and creates a unique run-ID directory.
- The runner stores exact source bytes, guest stdout/stderr, terminal status, return code, image/profile digests, loader, limits, and expected-versus-observed comparison. Evidence output refuses to overwrite an existing path.

- [ ] Write `test_runner_executes_echo_guest_without_reference_import`, `test_runner_records_raw_bytes_and_hashes`, and `test_conformance_keeps_terminal_statuses_distinct`.
- [ ] Run: `./tools/build.sh` and `python3 -m unittest tests.test_lisp_conformance_runner -v`.
  Expected: FAIL because the conformance runner is absent.
- [ ] Implement matrix loading and guest invocation through `tools/guest_runner.py`; assert the reference module is not loaded by that runner.
- [ ] Run: `python3 -m unittest tests.test_lisp_conformance_runner -v`.
  Expected: PASS on the existing `ubO` fixture; HALT, MAX_STEPS, loader error, and wall timeout remain distinct.
- [ ] Commit with `feat: add byte-oriented LispSlop conformance runner`.

### Task 4: Implement guest values, heap, and environments

**Files:**
- Create: `guest_ir/lisp/values.py`
- Create: `guest_ir/lisp/memory.py`
- Create: `guest_ir/lisp/environment.py`
- Create: `tests/guest/test_guest_values.py`
- Create: `tests/guest/test_guest_memory.py`

**Interfaces:**
- Each module exports a builder returning functions/blocks in `slopsynth.ir.Module`; none evaluates Lisp on the host.
- Define a tagged `Value` layout from the language spec for numbers, symbols, strings, lists, callable values, lazy values, and null.
- Define guest operations `alloc_words`, `alloc_cons`, `lookup_symbol`, `bind_symbol`, and `reset_heap` in the IR module.

- [ ] Write guest-kernel tests for value tags, list construction/access, allocator exhaustion, heap reset, lexical environment lookup, and shadowing.
- [ ] Run: `./tools/build.sh` and `python3 -m unittest tests.guest.test_guest_values tests.guest.test_guest_memory -v`.
  Expected: FAIL because the guest IR builders are absent.
- [ ] Implement the data structures as guest IR functions and compile them with `slopsynth.compile_module`; keep allocator pointers and object contents in guest memory.
- [ ] Run the tests through the generated image in `bolge19`.
  Expected: PASS with exact byte outputs and no host-side evaluation of values.
- [ ] Commit with `feat: add guest Lisp values and memory`.

### Task 5: Implement the guest reader and printer

**Files:**
- Create: `guest_ir/lisp/reader.py`
- Create: `guest_ir/lisp/printer.py`
- Create: `tests/guest/test_guest_reader.py`
- Create: `tests/guest/test_guest_printer.py`

**Interfaces:**
- Export `read_form(input_state) -> Value` and `print_value(value, output_state) -> None` as guest IR functions.
- Implement the exact syntax and byte/encoding behavior fixed in Task 1, including null, comments, quote/lazy prefixes, square/fork forms, and indexed forms.

- [ ] Write `test_guest_reader_accepts_all_matrix_syntax`, `test_guest_reader_rejects_truncated_and_invalid_input`, and `test_guest_printer_round_trips_supported_values`.
- [ ] Run: `python3 -m unittest tests.guest.test_guest_reader tests.guest.test_guest_printer -v`.
  Expected: FAIL because the guest parser/printer are absent.
- [ ] Implement reader and printer as guest functions; the host reference may produce expected bytes but may not parse guest input on the runtime path.
- [ ] Run: `./tools/build.sh` and the two guest test modules.
  Expected: PASS for all listed syntax and errors in the fixed-3^19 guest.
- [ ] Commit with `feat: add guest Lisp reader and printer`.

### Task 6: Implement core evaluation and callable values

**Files:**
- Create: `guest_ir/lisp/evaluator.py`
- Create: `guest_ir/lisp/callables.py`
- Create: `tests/guest/test_guest_evaluator.py`
- Create: `tests/guest/test_guest_callables.py`

**Interfaces:**
- Export `eval_form(form: Value, env: Value) -> Value` and `apply(function: Value, args: Value, env: Value) -> Value` as guest IR functions.
- Implement symbol lookup, quote, conditionals, `cond`, `let`, `def`, `defun`, `lambda`, lexical closures, recursion, macros, and `eval` as fixed by the feature matrix.
- Add callable forms for macros, lazy values, `bind`, `bind'`, `atop`, `fork`, `lift`, `bruijn`, `monad`, `dyad`, `selfie`, and `commute` when their matrix rows require them.

- [ ] Write guest tests for quote/if/cond, variable mutation and scope, `test_guest_closure_uses_lexical_environment`, recursion, macro unevaluated arguments, lazy forcing, partial application, and invalid callable arity.
- [ ] Run: `python3 -m unittest tests.guest.test_guest_evaluator tests.guest.test_guest_callables -v`.
  Expected: FAIL because evaluator functions are absent.
- [ ] Implement the evaluator as guest IR; closures capture their lexical environment and every recursive call uses guest stack/memory.
- [ ] Run the tests through `tools/run_lisp_conformance.py` and compare bytes with the host oracle.
  Expected: PASS for the core evaluation rows; any mismatch is recorded against the feature ID.
- [ ] Commit with `feat: add guest Lisp evaluator and closures`.

### Task 7: Implement numeric, comparison, and primitive list built-ins

**Files:**
- Create: `guest_ir/lisp/builtins_numeric.py`
- Create: `guest_ir/lisp/builtins_lists.py`
- Create: `tests/guest/test_guest_numeric.py`
- Create: `tests/guest/test_guest_lists.py`

**Interfaces:**
- Export `apply_numeric(name: Symbol, args: Value) -> Value` and `apply_list(name: Symbol, args: Value) -> Value` as guest functions.
- Numeric rows include the arithmetic, comparison, boolean/bitwise, min/max, and overloaded operators in the feature matrix.
- List rows include `atom`, `cons`, `car`, `cdr`, `iota`, `size`, `nth`, `append`, `append'`, `tie`, `rev`, `zip`, and flattening operations from the matrix.

- [ ] Write one positive, one boundary, and one invalid-type/arity test for each matrix row in these groups.
- [ ] Run: `python3 -m unittest tests.guest.test_guest_numeric tests.guest.test_guest_lists -v`.
  Expected: FAIL because the guest built-in modules are absent.
- [ ] Implement each built-in in guest IR. Use the integer bounds and overflow rules from Task 1; do not rely on host arithmetic during guest execution.
- [ ] Run the tests through the guest and reference oracle.
  Expected: PASS for every matrix row in these groups; failures retain the exact feature ID and raw output.
- [ ] Commit with `feat: add guest numeric and list builtins`.

### Task 8: Implement higher-order operations and function combinators

**Files:**
- Create: `guest_ir/lisp/builtins_higher_order.py`
- Create: `guest_ir/lisp/builtins_combinators.py`
- Create: `tests/guest/test_guest_higher_order.py`
- Create: `tests/guest/test_guest_combinators.py`

**Interfaces:**
- Export `apply_higher_order(name: Symbol, args: Value) -> Value` and `apply_combinator(name: Symbol, args: Value) -> Value` as guest IR functions.
- Cover `map`, `filter`, `flatmap`, `any`, `every`, `sort`, `fold`, `fold'`, `zipwith`, `iterate`, `iterateN`, `where`, `replicate`, `count`, take/drop variants, `intersperse`, `scan`, `scan'`, `uniq`, and the remaining higher-order matrix rows.

- [ ] Write tests for empty/singleton/larger lists, callback state, false results, invalid callbacks, invalid ordering inputs, and each overload listed in the feature matrix.
- [ ] Run: `python3 -m unittest tests.guest.test_guest_higher_order tests.guest.test_guest_combinators -v`.
  Expected: FAIL because the guest modules are absent.
- [ ] Implement the operations by calling guest `apply`; all iteration and callback evaluation happens inside the guest.
- [ ] Run the tests through the guest and compare against the reference model.
  Expected: PASS for every assigned feature ID.
- [ ] Commit with `feat: add guest higher-order Lisp operations`.

### Task 9: Add the persistent REPL, commands, and state import/export

**Files:**
- Create: `guest_ir/lisp/repl.py`
- Create: `guest_ir/lisp/state_image.py`
- Create: `tests/guest/test_guest_repl.py`
- Create: `tests/guest/test_guest_state_image.py`

**Interfaces:**
- Export `repl_step(input_state, session_state) -> (session_state, terminal_status)` and `reset_session(session_state) -> session_state` as guest IR functions.
- Implement documented commands `.F`, `.A`, `.R`, `.M`, `.S`, `.E`, `.I`, expression persistence, EOF handling, and the specified quit form.
- State serialization is a project-defined versioned binary format with explicit bounds and validation; do not reproduce an unchecked upstream memory dump.

- [ ] Write tests for definitions surviving across forms, reset clearing state, memory and symbol reporting, valid export/import round trip, `test_guest_import_rejects_invalid_image`, and EOF/quit status.
- [ ] Run: `python3 -m unittest tests.guest.test_guest_repl tests.guest.test_guest_state_image -v`.
  Expected: FAIL because the guest REPL and state-image functions are absent.
- [ ] Implement the REPL and versioned state format entirely in guest IR. Keep prompt and error bytes defined by the language spec.
- [ ] Run tests through the actual generated guest.
  Expected: PASS; persistent state changes only when the corresponding guest expression or command runs.
- [ ] Commit with `feat: add persistent guest REPL and state images`.

### Task 10: Close the complete feature matrix and reproducible guest build

**Files:**
- Create: `tools/build_lisp_guest.py`
- Create: `tests/test_complete_guest_matrix.py`
- Create: `docs/LISP_CONFORMANCE.md`
- Modify: `Makefile`
- Modify: `README.md`

**Interfaces:**
- `build_lisp_guest.py` assembles the guest IR modules, calls `slopsynth.compile_module`, and writes `build/lispslop-guest.mb` plus a deterministic manifest.
- `run_lisp_conformance.py` accepts the generated image, matrix, required resource bounds, and a new evidence path; it refuses to overwrite evidence.
- The project status report lists each feature ID and its `SPECIFIED`, `IMPLEMENTED`, and `DEMONSTRATED` states.

- [ ] Write `test_complete_guest_matrix_has_no_open_rows`, `test_all_promised_rows_have_guest_results`, `test_guest_errors_match_feature_matrix`, `test_guest_build_is_reproducible`, and `test_host_oracle_is_not_on_guest_execution_path`.
- [ ] Run: `./tools/build.sh` and `python3 -m unittest tests.test_complete_guest_matrix -v`.
  Expected: FAIL while any feature row lacks a guest implementation or evidence.
- [ ] Implement the image build and evidence report; never call the product complete when any promised row is open, host-evaluated, or missing a guest result.
- [ ] Run: `python3 -m unittest discover -s tests -v` and `python3 tools/run_lisp_conformance.py --image build/lispslop-guest.mb --matrix spec/lisp-feature-matrix.json --evidence-root evidence/lisp`.
  Expected: every matrix row has guest output matching the declared expectation; all HALT/limit/error statuses and resource bounds appear in the evidence.
- [ ] Commit with `feat: complete fixed19 LispSlop guest conformance`.
