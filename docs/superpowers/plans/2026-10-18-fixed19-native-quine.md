# Fixed-3^19 Native Quine Research Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Search for a guest-native fixed-`3^19` quine and produce reproducible evidence for a valid candidate or a precise `NOT_DEMONSTRATED` result.

**Architecture:** A bounded research harness proposes candidates through the synthesis backend, runs them in `bolge19`, and compares raw guest stdout with the candidate source bytes. Every search records its seed, bounds, candidate digests, VM result, and failure reason; host-side source copying is forbidden.

**Tech Stack:** Python 3.12 standard library, synthesis-backend API, Zig 0.16.0 `bolge19`, `unittest`.

**Spec:** [SYSTEM_SPEC.md](../../SYSTEM_SPEC.md)

## Global Constraints

- Search only the fixed-`3^19` profile implemented by `bolge19`.
- Do not transfer Classic `3^10` quine claims or raw artifacts to this target.
- A valid quine must satisfy guest `stdout == source_bytes` byte-for-byte, emit no extra bytes, and reach `HALT`.
- Never use the host to open/copy the candidate source into stdout.
- Preserve every candidate and failed-search report in a unique evidence directory; do not overwrite.
- A bounded search failure means `NOT_DEMONSTRATED`, not “no quine exists.”
- Do not publish, push, create a release, or edit upstream BolgeForge as part of this plan.

## Review Focus

- Final newline and whitespace differences between source bytes and canonical loading: pin with `test_quine_compares_exact_source_bytes`.
- Candidate copied by host rather than emitted by the guest: pin with `test_quine_verifier_runs_guest_candidate`.
- Non-HALT termination or extra output accepted as success: pin with `test_quine_requires_halt_and_no_extra_output`.
- Candidate source changed after evidence capture: pin with `test_quine_manifest_detects_candidate_mutation`.
- Search budget exhaustion misreported as unsatisfiable: pin with `test_quine_budget_exhaustion_is_not_unsat`.

---

### Task 1: Define the quine contract and evidence schema

**Files:**
- Create: `quine/contract.json`
- Create: `quine/__init__.py`
- Create: `quine/evidence.py`
- Create: `tests/test_quine_contract.py`

**Interfaces:**
- `QuineContract(profile: str, loader: str, newline_policy: str)`; `newline_policy` is one of `final-newline` or `no-final-newline`.
- `quine/contract.json` fixes `profile="fixed-3^19"`, `loader="canonical"`, and `newline_policy="no-final-newline"`; it also requires byte-exact stdout and a guest `HALT`.
- `QuineReport(status: str, candidate_path: str | None, source_sha256: str | None, stdout_sha256: str | None, steps: int | None, bounds: dict, reason: str)`.
- Statuses are `DEMONSTRATED`, `NOT_DEMONSTRATED`, and `BUDGET_EXHAUSTED`; never emit a global `NO_QUINE` status.
- The contract fixes whether the source file has a final newline and which whitespace the canonical loader discards. The emitted bytes still include exactly the declared source bytes.

- [x] Write tests for fixed-3^19 profile validation, newline policy, report serialization, and required search-bound fields.
- [x] Run: `python3 -m unittest tests.test_quine_contract -v`.
  Expected: FAIL because the quine contract and report types are absent.
- [x] Implement the JSON contract loader and versioned evidence schema; reject unknown profiles and missing search bounds.
- [x] Run: `python3 -m unittest tests.test_quine_contract -v`.
  Expected: PASS; `contract.json` names `fixed-3^19`, canonical loading, and byte-exact output comparison.
- [x] Commit with `docs: define fixed19 quine contract` (`9507d8e`).

### Task 2: Implement a bounded candidate search driver

**Files:**
- Create: `quine/search.py`
- Create: `tools/search_fixed19_quine.py`
- Create: `tests/test_quine_search.py`

**Interfaces:**
- Consume the fixed-3^19 profile and guest runner from the synthesis-backend plan. Define a separate `QuineSearchBudget` so it cannot be confused with the synthesizer's `SearchBudget`.
- Produce `search(contract: QuineContract, budget: QuineSearchBudget, output_dir: Path) -> QuineReport`. Task 3 owns `verify_candidate(...)` in `quine/verify.py` so there is one canonical verifier.
- `QuineSearchBudget` contains `max_nodes`, `wall_seconds`, `candidate_steps`, `candidate_timeout_seconds`, `candidate_memory_bytes`, and `max_candidate_bytes`.
- Implement `iter_candidates(contract: QuineContract, budget: QuineSearchBudget)`, a deterministic bounded enumerator that derives printable candidate images from search state and profile constraints; it must not load a candidate corpus or embed instruction strings. If this candidate space proves too large, retain the search harness and report its bounds as `NOT_DEMONSTRATED`.
- Search is deterministic for a declared seed and method. Each candidate is generated from search state; candidate bytes are not pasted into source code or copied from a file.
- The harness records the exact algorithm, seed, node/time/address/step budgets, candidates attempted, and a digest for every retained candidate.

- [x] Write `test_quine_budget_exhaustion_is_not_unsat`, `test_completed_empty_search_is_not_demonstrated`, and `test_seeded_search_order_and_manifest_are_reproducible`.
- [x] Run: `python3 -m unittest tests.test_quine_search -v`.
  Expected: FAIL because the search driver is absent.
- [x] Implement the deterministic search loop using only profile-derived candidates and the guest runner; candidates are dispatch-name products encoded by the synthesis API and retained in a new run directory.
- [x] Run: `python3 -m unittest tests.test_quine_search -v`.
  Expected: PASS; reports distinguish budget exhaustion from a fully explored bounded space.
- [x] Commit with `feat: add bounded fixed19 quine search driver` (`1c77832`).

### Task 3: Verify candidate execution byte-for-byte

**Files:**
- Create: `quine/verify.py`
- Create: `tools/verify_fixed19_quine.py`
- Create: `tests/test_quine_verifier.py`

**Interfaces:**
- Consume `run_guest(image: Path, stdin: bytes, config: RunConfig) -> GuestResult` from the synthesis-backend plan.
- Produce `verify_candidate(source: Path, contract: QuineContract, budget: QuineSearchBudget) -> QuineReport`.
- Invoke the guest with empty stdin and map `candidate_steps`, `candidate_timeout_seconds`, `candidate_memory_bytes`, and `max_candidate_bytes` to the runner's step, wall-time, address-space, and output-capture limits.
- Success requires canonical guest loading, `stdout == source.read_bytes()`, status `HALT`, and an image/source digest match in the report. Capture stderr separately; telemetry there does not count as quine output.
- A second backend is recorded only when it is genuinely independent and accepts the same fixed profile and loader. Otherwise the report says single-implementation verification.

- [x] Write `test_quine_compares_exact_source_bytes`, `test_quine_verifier_runs_guest_candidate`, `test_quine_requires_halt_and_no_extra_output`, `test_quine_manifest_detects_candidate_mutation`, and negative cases for final-newline mismatch, `MAX_STEPS`, and `WALL_TIMEOUT`.
- [x] Run: `./tools/build.sh` and `python3 -m unittest tests.test_quine_verifier -v`.
  Expected: FAIL because the candidate verifier is absent.
- [x] Implement verification by passing the candidate path directly to `bolge19` through `run_guest`; never read candidate bytes in a host output path.
- [x] Run: `python3 -m unittest tests.test_quine_verifier -v`.
  Expected: PASS on negative controls; no unverified candidate is marked `DEMONSTRATED`.
- [ ] Commit with `feat: verify fixed19 quine candidates in guest`.

### Task 4: Run the declared search and record its local evidence report

**Files:**
- Create: `quine/budget-smoke.json`
- Create: `docs/QUINE_RESEARCH.md`
- Modify: `Makefile`
- Modify: `README.md`

**Interfaces:**
- CLI: `python3 tools/search_fixed19_quine.py --contract quine/contract.json --budget quine/budget-smoke.json --output-root evidence/quine`.
- `budget-smoke.json` pins a first bounded campaign at 10,000 candidate nodes, 10 seconds wall time, 1,000,000 guest steps per candidate, 2 seconds/536,870,912 bytes per candidate process, and 100,000 bytes maximum per candidate image. Later campaigns use new immutable budget files.
- The CLI creates a unique run directory containing `report.json`, raw stdout/stderr for executed candidates, candidate files, and SHA-256 digests.
- `docs/QUINE_RESEARCH.md` reports the latest verified result without deleting or overwriting earlier runs.

- [ ] Write `test_search_cli_creates_unique_evidence_run` and `test_report_never_calls_budget_exhaustion_a_quine`.
- [ ] Run: `python3 -m unittest tests.test_quine_search tests.test_quine_verifier -v`.
  Expected: FAIL until the CLI and report writer are complete.
- [ ] Implement unique run IDs and an append-only report index. Preserve every rejected candidate and its reason.
- [ ] Run the smoke campaign with `python3 tools/search_fixed19_quine.py --contract quine/contract.json --budget quine/budget-smoke.json --output-root evidence/quine`, then run the verifier on each surviving candidate.
  Expected: either a fully demonstrated candidate or a `NOT_DEMONSTRATED` / `BUDGET_EXHAUSTED` report with the exact explored bounds and hashes.
- [ ] Commit with `docs: record fixed19 quine research run`.

## Completion gate

This track is complete only when a fixed-`3^19` candidate passes byte-exact guest verification and halts. If the bounded search does not find one, the research tooling and honest evidence report are complete, but the system specification’s quine gate remains open.
