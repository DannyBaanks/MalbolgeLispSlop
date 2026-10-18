# Fixed-3^19 Synthesis Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic host toolchain that synthesizes guest instruction streams for the fixed-`3^19` machine from readable program contracts, with no hand-authored Malbolge bytes.

**Architecture:** Python defines the profile, guest IR, bounded semantic model, and search contracts. A deterministic synthesizer finds target streams, a layout pass emits printable bytes, and `bolge19` executes each accepted candidate. Search results always state their bounds; exhausting a budget is not proof of impossibility.

**Tech Stack:** Python 3.12 standard library, `unittest`, Zig 0.16.0 `bolge19` as the execution target.

**Spec:** [SYSTEM_SPEC.md](../../SYSTEM_SPEC.md)

## Global Constraints

- Target only the fixed-width 19-trit (`3^19`) machine implemented by `bolge19`.
- The profile end value is `1,162,261,467`; EOF input maps to `END - 1`.
- Keep raw and canonical loaders distinct; generated text uses canonical loading.
- Generate all target instruction bytes, including any reusable blocks. Do not copy `fixtures/echo.mb` into output or maintain opcode templates by hand.
- Use Python 3.12 standard library and Zig 0.16.0; do not add runtime dependencies.
- Put temporary generated images under ignored `build/`; write evidence to unique run directories and never overwrite.
- Do not describe this fixed profile as dynamically widening Unshackled or Malbolge Free.

## Review Focus

- Position-dependent decode and self-modification: pin with `test_positioned_decode_and_mutation_match_bolge19`.
- Canonical whitespace skipping versus raw cell counting: pin with `test_loader_contracts_diverge_on_whitespace`.
- EOF sentinel versus byte `0xff`: pin with `test_eof_sentinel_is_not_a_byte`.
- Search budget exhaustion versus a proven no-solution result: pin with `test_budget_exhaustion_is_not_unsat`.
- Post-generation byte edits versus declared provenance: pin with `test_manifest_rejects_changed_artifact`.

---

### Task 1: Pin the target profile and define guest IR

**Files:**
- Create: `profiles/fixed19.json`
- Create: `slopsynth/__init__.py`
- Create: `slopsynth/profile.py`
- Create: `slopsynth/ir.py`
- Create: `slopsynth/ir_json.py`
- Create: `examples/echo.json`
- Create: `tests/__init__.py`
- Test: `tests/test_synth_profile.py`
- Test: `tests/test_synth_ir.py`

**Interfaces:**
- Produces `Profile` and `load_profile(path: Path) -> Profile`.
- Produces immutable `Program(name: str, operations: tuple[Operation, ...])` and `load_program(path: Path) -> Program`.
- The initial `Operation` variants are `ReadA`, `WriteA`, and `Halt`. Later tasks add a variant only with its semantic tests.
- The profile records `name="fixed-3^19"`, `trits=19`, `end=1_162_261_467`, `eof_value=1_162_261_466`, the eight dispatch indices from `src/bolge19.zig`, and the raw/canonical loader rules including the canonical position cycle of 564.

- [ ] Write `test_profile_has_fixed_3_19_constants`, `test_loader_contracts_diverge_on_whitespace`, and `test_profile_rejects_unknown_dispatch_indices`.
- [ ] Run: `python3 -m unittest tests.test_synth_profile -v`
  Expected: the new tests fail because the profile loader does not exist.
- [ ] Implement `Profile` and `load_profile` in `slopsynth/profile.py`; load constants from `profiles/fixed19.json` rather than duplicating them in the synthesizer.
- [ ] Run: `python3 -m unittest tests.test_synth_profile -v`
  Expected: PASS, including exact `END`, EOF, opcode-index, and loader assertions.
- [ ] Write `test_ir_accepts_echo_and_rejects_unknown_ops` and `test_ir_requires_terminal_halt`.
- [ ] Run: `python3 -m unittest tests.test_synth_ir -v`
  Expected: FAIL because the IR loader does not exist.
- [ ] Implement the three initial operation variants and JSON parser in `slopsynth/ir.py` and `slopsynth/ir_json.py`; make `examples/echo.json` describe read, write, halt.
- [ ] Run: `python3 -m unittest tests.test_synth_ir -v`
  Expected: PASS; unknown operations and missing final halt are rejected with a useful error.
- [ ] Commit these files with `docs: define fixed19 synthesis profile and IR`.

### Task 2: Add the bounded fixed-3^19 semantic model

**Files:**
- Create: `slopsynth/model.py`
- Create: `tests/test_synth_model.py`
- Modify: `profiles/fixed19.json` only if a test exposes a missing profile constant.

**Interfaces:**
- Produces `RunStatus` with `HALT`, `MAX_STEPS`, `LOAD_ERROR`, and `MODEL_BOUND`.
- Produces `RunResult(stdout: bytes, status: RunStatus, steps: int, final_a: int, final_c: int, final_d: int)`.
- Produces `run_model(image: bytes, stdin: bytes, profile: Profile, *, loader: str, max_steps: int, max_address: int) -> RunResult`.
- The model must reject reads above `max_address`; it must not silently treat the bound as the VM's full address space.

- [ ] Write tests for every dispatch operation, post-instruction encryption, memory mutation, `test_eof_sentinel_is_not_a_byte`, step exhaustion, and bounded memory access.
- [ ] Run: `python3 -m unittest tests.test_synth_model -v`
  Expected: FAIL because `run_model` is absent.
- [ ] Implement the fixed-profile transition model with sparse writes and explicit loader selection. Preserve the VM's distinction between `HALT`, `MAX_STEPS`, and a model bound.
- [ ] Run: `./tools/build.sh` and `python3 -m unittest tests.test_synth_model -v`.
  Expected: PASS; `ubO` echoes `A`, NUL, and `0xff`, and the test harness distinguishes EOF from `0xff`.
- [ ] Add `test_positioned_decode_and_mutation_match_bolge19` and compare model and Zig VM output/status on the existing `ubO` fixture plus one mutated fixture.
- [ ] Run: `python3 -m unittest tests.test_synth_model -v`.
  Expected: PASS for the declared model bounds. Label this comparison as cross-checking, not an independent backend certification.
- [ ] Commit with `feat: add bounded fixed19 synthesis model`.

### Task 3: Synthesize and emit the minimal variable-I/O guest

**Files:**
- Create: `slopsynth/encode.py`
- Create: `slopsynth/search.py`
- Create: `tests/test_synth_echo.py`

**Interfaces:**
- Produces `SearchBudget(max_cells: int, max_nodes: int, max_steps: int, max_address: int)`.
- Produces `SynthesisResult(status: str, image: bytes | None, explored_nodes: int, bounds: SearchBudget)`; statuses are `FOUND`, `NOT_FOUND_WITHIN_BOUNDS`, and `BUDGET_EXHAUSTED`.
- Produces `synthesize_program(program: Program, profile: Profile, budget: SearchBudget) -> SynthesisResult` and `encode_program(program: Program, profile: Profile) -> bytes`.

- [ ] Write tests that the `ReadA, WriteA, Halt` program synthesizes as `b"ubO"`, echoes four distinct byte inputs, and reports configured bounds when a candidate exceeds them.
- [ ] Run: `python3 -m unittest tests.test_synth_echo -v`.
  Expected: FAIL because synthesis and encoding are absent.
- [ ] Implement deterministic synthesis over canonical-valid source bytes. Generate each candidate byte from the requested guest operation and address; do not read or copy `fixtures/echo.mb`.
- [ ] Run: `./tools/build.sh` and `python3 -m unittest tests.test_synth_echo -v`.
  Expected: PASS; the synthesized image is `ubO` and echoes the corpus in the actual `bolge19` VM.
- [ ] Add `test_budget_exhaustion_is_not_unsat` and verify that node exhaustion returns `BUDGET_EXHAUSTED` with the exact configured bounds.
- [ ] Run: `python3 -m unittest tests.test_synth_echo -v`.
  Expected: PASS; no bounded search failure is reported as proof that no program exists.
- [ ] Commit with `feat: synthesize fixed19 variable-io guest`.

### Task 4: Prove the backend can synthesize control flow and memory

**Files:**
- Modify: `slopsynth/ir.py`
- Modify: `slopsynth/search.py`
- Modify: `slopsynth/model.py`
- Create: `examples/branch_zero.json`
- Create: `examples/store_load.json`
- Create: `examples/countdown.json`
- Create: `tests/test_synth_capabilities.py`
- Create: `docs/SYNTHESIS_FEASIBILITY.md`

**Interfaces:**
- Add `Module`, `Function`, `BasicBlock`, `BranchZero`, `Jump`, `Load`, `Store`, `Add`, `Sub`, `Call`, and `Return` to the typed guest IR. Each operation has a semantic contract in the feasibility report.
- Extend `synthesize_program` without changing its result statuses or budget fields.
- Produce `compile_module(module: Module, profile: Profile, budget: SearchBudget) -> SynthesisResult`.
- Produce a feasibility report with each target, search method, bounds, explored nodes, generated-image digest, VM result, and `DEMONSTRATED` or `NOT_DEMONSTRATED` label.

- [ ] Write `test_synthesized_branch_distinguishes_zero_and_nonzero`, `test_synthesized_store_load_preserves_input`, `test_synthesized_add_and_sub_boundaries`, `test_synthesized_countdown_halts_at_zero`, and `test_synthesized_call_return_preserves_result` using multiple inputs and boundary values.
- [ ] Run: `python3 -m unittest tests.test_synth_capabilities -v`.
  Expected: FAIL because the operations and search results do not exist.
- [ ] Extend the typed IR and bounded search; explore deterministic enumeration and a BolgeForge-inspired shortest-path search over profile-derived states. Do not copy the Classic macro table or claim a transfer from `3^10`.
- [ ] Run: `./tools/build.sh` and `python3 -m unittest tests.test_synth_capabilities -v`.
  Expected: each demonstrated goal runs in `bolge19` and matches its contract on all listed cases.
- [ ] If any goal exhausts its budget, write the exact bounds and candidate/failure evidence to `docs/SYNTHESIS_FEASIBILITY.md`; label it `NOT_DEMONSTRATED` and stop before starting the full Lisp guest plan.
- [ ] Commit with `feat: synthesize fixed19 control-flow primitives` or, for an honest failed search, `docs: record fixed19 synthesis feasibility limit`.

### Task 5: Add guest runner, CLI, and reproducible artifact manifests

**Files:**
- Create: `slopsynth/manifest.py`
- Create: `tools/guest_runner.py`
- Create: `tools/synthesize_guest.py`
- Create: `tools/verify_generated_guest.py`
- Create: `tests/test_guest_runner.py`
- Create: `tests/test_synth_manifest.py`
- Modify: `Makefile`
- Create: `docs/SYNTHESIZER.md`

**Interfaces:**
- Produces `RunConfig(loader: str, max_steps: int, timeout_seconds: float, address_space_bytes: int, output_bytes: int)` and `GuestResult(stdout: bytes, stderr: bytes, returncode: int | None, status: GuestStatus)`.
- `GuestStatus` is one of `HALT`, `MAX_STEPS`, `LOAD_ERROR`, `WALL_TIMEOUT`, `OUTPUT_LIMIT`, or `PROCESS_ERROR`; return code alone never determines `HALT`. The runner caps captured stdout and terminates the child with `OUTPUT_LIMIT` when it crosses the configured bound.
- Produces `run_guest(image: Path, stdin: bytes, config: RunConfig) -> GuestResult`; keep it independent from the Lisp reference model.
- CLI: `python3 tools/synthesize_guest.py <goal.json> --profile profiles/fixed19.json --output <new-path> --manifest <new-path> --max-cells N --max-nodes N --max-steps N --max-address N`.
- The manifest records profile digest, program digest, generator revision, algorithm/configuration, explored nodes, artifact SHA-256, and validation result. Volatile timestamps belong in evidence, not in the reproducible manifest.

- [ ] Write tests for capped byte capture and distinct `OUTPUT_LIMIT`, `HALT` versus `MAX_STEPS` and wall timeout, no-overwrite evidence paths, deterministic repeated synthesis, and `test_manifest_rejects_changed_artifact`.
- [ ] Run: `python3 -m unittest tests.test_guest_runner tests.test_synth_manifest -v`.
  Expected: FAIL because the runner, CLI, and manifest writer are absent.
- [ ] Implement the bounded subprocess runner and manifest writer; keep stdout/stderr as bytes and do not infer HALT from timeout or exit code alone.
- [ ] Run: `./tools/build.sh` and `python3 -m unittest tests.test_guest_runner tests.test_synth_manifest -v`.
  Expected: PASS; repeated runs produce the same image and manifest digests, while a one-byte edit fails verification.
- [ ] Add the CLI and a `synth-echo` Make target. The command refuses to overwrite output paths and writes generated bytes only under the requested new path.
- [ ] Run: `python3 tools/synthesize_guest.py examples/echo.json --profile profiles/fixed19.json --output build/synth/echo.mb --manifest build/synth/echo.manifest.json --max-cells 3 --max-nodes 10000 --max-steps 8 --max-address 8`.
  Expected: exit 0, generated image `ubO`, manifest status `FOUND`, guest status `HALT`, and byte-exact output for the echo corpus.
- [ ] Commit with `feat: add reproducible fixed19 synthesis CLI`.

### Task 6: Add the deliberately silly manual-review estimate

**Files:**
- Create: `tools/estimate_review_time.py`
- Create: `tests/test_review_estimate.py`
- Modify: `Makefile`
- Modify: `docs/SYNTHESIZER.md`

**Interfaces:**
- `estimate_review_time(artifact_bytes: int, bytes_per_second: float, hours_per_day: float) -> ReviewEstimate` reports uninterrupted years as `bytes / rate / 31,536,000` and workday years as `bytes / (rate * hours_per_day * 3,600) / 365`.
- CLI: `python3 tools/estimate_review_time.py build/lispslop-guest.mb --bytes-per-second 1 --hours-per-day 8` measures the current generated image size and prints both estimates plus the input assumptions.
- Historical “350 MB” figures may appear only as cited historical context. The command always measures the actual file and must not imply that byte-by-byte reading is semantic verification.

- [ ] Write `test_estimate_uses_actual_artifact_size`, `test_estimate_scales_with_reading_rate`, and `test_invalid_estimate_inputs_are_rejected`.
- [ ] Run: `python3 -m unittest tests.test_review_estimate -v`.
  Expected: FAIL because the estimator is absent.
- [ ] Implement the pure calculation and CLI; keep input rates explicit and label the result as a satire estimate.
- [ ] Run: `python3 -m unittest tests.test_review_estimate -v` and invoke the CLI on a generated guest image.
  Expected: both time estimates use that file's measured byte count; no historical size is substituted.
- [ ] Commit with `docs: add measured manual-review satire estimate`.

## Dependency gate

The guest Lisp plan may start after Tasks 1–5 pass **and** Task 4 demonstrates branch, bounded loop, and guest memory load/store. If one of those remains `NOT_DEMONSTRATED`, keep the runtime unimplemented and revise the synthesis design first. This gate prevents a readable host evaluator from being mistaken for a Lisp guest.
