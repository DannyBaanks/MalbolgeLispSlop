# SDD ledger — plan: docs/superpowers/plans/2026-10-18-complete-native-lisp.md

## Checklist

- [x] Task 1: contract, dependencies, persistent plan
- [x] Task 2: compatibility inventory and checker
- [ ] Task 3: semantic contract and original-profile probes
- [ ] Task 4: exact symbolic transition model
- [ ] Task 5: synthesized reusable blocks/bootstrap
- [ ] Task 6: general certified module compiler
- [ ] Task 7: guest heap/values/environments/stack
- [ ] Task 8: guest reader/printer/core evaluator
- [ ] Task 9: complete promised language surface
- [ ] Task 10: REPL/state commands
- [ ] Task 11: clean reproduction and complete guest matrix

## Pre-flight and rulings

- Tasks 2/3 produce the language matrix/contract consumed by 7–10. No guest
  feature may be labeled implemented from reference-only tests.
- Tasks 4/5 produce transitions/block contracts consumed by 6; task 6 is the
  execution dependency gate for 7–10. Current H2 is not that gate.
- Task 11 consumes every prior task's evidence and manifests; legacy evidence
  and legacy manifest verification must remain available.
- Ruling: user explicitly approved this plan including Z3 and separate quine
  scope; this approval supersedes contradictory old specification passages.
  Cost if wrong: contract amendment, not silently reduced implementation scope.
- Ruling: use a manual isolated worktree for the sibling repository because
  this chat's native create_worktree tool targets its attached ISyCo monorepo.
  Cost: worktree is not managed by the app; preserve it and report its path.
- Ruling: retain scratch/ledger/evidence; skill cleanup suggestions do not
  override the user's zero-deletion contract.
- Baseline attempt started before asynchronous worktree checkout completed:
  build script was absent and tests failed due to missing VM. No code changed;
  rerun build/tests after checkout completion before implementation.

## Execution

Task 1: complete. Clean checkout baseline: 136 tests, exit 0; Zig build exit 0.
Pinned Z3 imports as 4.16.0. Baseline ResourceWarnings match prior H2.
Ruling: task 4 depends on the frozen machine profile, not language tasks 2/3;
its implementation may progress while those contracts are being audited, but
no guest Lisp code starts until tasks 5/6 are demonstrated.

Task 2: compatibility inventory frozen; closure gate remains open. The manual
union contains 224 rows (80 builtins, 104 errors, 13 syntax forms, 13 types, 7
overloads, 7 commands). Nineteen additional mandatory cross-cutting semantic
rows cover scope/lifetime, evaluation, equality, macros/laziness, reader and
printer behavior, errors, REPL state, bounds, and recursion: 243 rows total.
The inventory includes the `.F` omissions `quote`, `gcd`, `lcm`, and `bind'`;
E033 is absent from the source error table. The validator also refuses a
refrozen inventory that omits any required semantic row, and retains the gates
for completeness, identities, digests, and guest evidence. All 243 rows remain
DECLARED because exact guest fixtures and implementations do not exist. Local
reference: `/home/danny/Development/ISyCo Git/malbolge-lisp/MalbolgeLisp.pdf`;
it is not copied. Independent review found this coverage gap before it was
closed; the reviewer confirmed the expanded inventory remains unimplemented.

Task 3: in progress. `tools/probe_language_contract.py` writes immutable bounded
sessions against `/tmp/opencode/specimen100-m1-lisp.mb` with the raw loader and
records input, output, status, budgets, image/VM/profile/recorder hashes. The
specimen digest in these records is
`092df5cdc240de33a355d3cf82bdf09e0859c5827ee57a65bf93dfc37e8f3256`.
Observed: `(+ 2 1)` -> `3`, `(* 3 3)` -> `9`, `(% 5 2)` -> `1`, `> 5 6` ->
`0`, `< 5 6` -> `1`, and `= 6 6` -> `1`. Both `(+ 67108863 1)` and
`(+' 67108863 1)` returned `0`. The 59-case probe stopped on `E095` at its
first form; two underflow probes reached the 240-second supervisor limit and
the broad safe-arithmetic probe reached 8,000,000,000 VM steps. These are
preserved observations, not inferred semantics. The bounded equality probe
then confirmed `=`, `/=`, and `~` on numeric operands with 0/1 results; it
halted at 6,934,983,070 VM steps. Structural equality, nonnumeric truth,
subtraction underflow, evaluation order, lazy values and macros remain
unresolved against the original. `spec/lisp-language-v1.md` records those
observations and the chosen 26-bit modular target behavior without upgrading
the unresolved matrix rows. `runs/20261018T1840Z-list-sort-replicate/` contains
only a prepared request and stdin, with no result or hashes; it is explicitly
not counted as a completed probe.

Task 4: bounded model conformance demonstrated, complete-compiler gate remains
open. The Z3 transition implementation checks all fixed19 native opcodes,
translation/region boundaries, loader modes, initialization pages, input/EOF,
halt and execution bounds against the concrete model and `bolge19`; normal
and `python -O` runs pass. T24's correct orientation has 0 mismatches and the
swapped control has 18,709 of 59,049 mismatches. Evidence:
`evidence/symbolic_model_v1/runs/20261018T185835Z-a94cc6fc/`.
This is bounded differential evidence; it is not a proof of the Zig VM or a
claim that every possible machine state has been exhaustively checked.

Task 5: reusable unary OPR/ROT primitives demonstrated, bootstrap and general
composition remain NOT_DEMONSTRATED. Search uses fixed-residue SAT checks so
replay does not depend on Z3's incidental model choice. Universal contracts
prove the A result, code restoration, three-step control exit, unchanged I/O
and full memory frame except the selected data word. The actual VM calls each
block twice under variable byte cases. Normal and `-O` tests pass. Evidence:
`evidence/unary_blocks_v1/runs/20261018T190458Z-dfbc981d/`; it contains 30 raw
native runs and two mutated-block negative controls. All 30 expected outputs
matched; both mutations changed or prevented the expected result.
No bootstrap, general branch/memory/call lowering, or Lisp guest is claimed.

Task 6: one second fixed19 branch template demonstrated; the general module
compiler remains NOT_DEMONSTRATED. The new source has useful, distinct work on
both arms: zero consumes and discards one byte before echoing the next, while
nonzero echoes the next byte. Its lowering is a fixed 259-cell layout, so it
does not establish arbitrary branch relocation, block composition, data
memory, arithmetic, loops, or calls. The original H2 image/proof remains a
separate regression. Evidence:
`evidence/both_arms_branch_v1/runs/20261018T191951Z-44715b9f/`; 1,792 selector
and payload VM cases, two spaced-image cases, full-address first-read EOF, and
two mutant negative controls (1,797 native runs total). All native results
halt and match the concrete model; both negative controls halt with the
model-predicted wrong output. Evidence checksums pass and the historical H2
image digest is unchanged. The gate passed with Python `-O`; all 173 unit tests
passed normally and with `-O`. Independent review approved this scoped claim.
General CFG composition and the MalbolgeLISP guest remain NOT_DEMONSTRATED.
