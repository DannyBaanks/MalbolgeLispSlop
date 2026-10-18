# SDD ledger — plan: docs/superpowers/plans/2026-10-18-complete-native-lisp.md

## Checklist

- [x] Task 1: contract, dependencies, persistent plan
- [ ] Task 2: compatibility inventory and checker
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

Task 1: in progress. Branch codex/malbolgelisp-complete in sibling worktree.

Task 1: complete. Clean checkout baseline: 136 tests, exit 0; Zig build exit 0.
Pinned Z3 imports as 4.16.0. Baseline ResourceWarnings match prior H2.
Ruling: task 4 depends on the frozen machine profile, not language tasks 2/3;
its implementation may progress while those contracts are being audited, but
no guest Lisp code starts until tasks 5/6 are demonstrated.
