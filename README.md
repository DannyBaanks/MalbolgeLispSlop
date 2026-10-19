# MalbolgeLispSlop

**100% Slop. 0% Excuses.** A small, evidence-first project to find out what it
actually takes to host Lisp on Malbolge.

The first slice runs a three-cell guest (`in`, `out`, `halt`) on the existing
fixed-3^19 `bolge19` VM. That is a narrow MalbolgeLISP profile, not a claim of
full parity with the original dynamically widening Unshackled implementation.
See [the baseline](docs/BASELINE.md) before extending the scope.

## Build and reproduce the first slice

Requirements: Zig 0.16.0 and Python 3.12+.

```sh
./tools/build.sh
python3 tools/verify_slice.py --output evidence/m1/slice.json
```

The verifier captures stdout and stderr as bytes, exit status, step/loader
signals, resource limits, and SHA-256 values. It checks variable input,
deterministic output, clean halt, invalid input, loader differences, a guest
mutation, controlled allocation failure, the step limit, and the supervisor's
wall-timeout path. The timeout self-check intentionally expires a child
immediately; it does not establish that a particular Malbolge program loops
forever.

The bounded fixed-`3^19` quine campaign runs with `make quine-smoke` (10 s
wall, at most 10,000 nodes, seed 0). Every run writes a new immutable
directory under `evidence/quine/` with candidate images, raw guest output,
digests, and an append-only index; earlier runs are never overwritten. The
latest verified result is [QUINE_RESEARCH.md](docs/QUINE_RESEARCH.md).

## Project status

- M0 inventory and scope: [BASELINE.md](docs/BASELINE.md)
- Runtime boundary: [ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Evidence and claims: [PARITY_MATRIX.md](docs/PARITY_MATRIX.md)
- Risks: [RISKS.md](docs/RISKS.md)
- Milestones: [PLAN.md](docs/PLAN.md)
- Loader gate L1, a compiled image running on fixed-`3^19`:
  [protocol](evidence/loader_gate_v1/protocol.md)
- Front-end gate H1, our own `.slop` text to canonical image:
  [protocol](evidence/hell_frontend_v1/protocol.md)
- Native branch gate H2 has two fixed 259-cell templates: zero-stop/nonzero-
  echo and zero-double-read/nonzero-echo. See the [original protocol](evidence/h2_branch_v1/protocol.md),
  [both-arms protocol](evidence/both_arms_branch_v1/protocol.md), and [Spanish guide](GUIA.md).
  These remain scoped lowerings, not general control flow or a Lisp guest.
- Native loop gate H3, iterative loop with native control flow:
  [protocol](evidence/h3_loop_v1/protocol.md).
  This is a scoped 259-cell lowering, not general loops or a Lisp guest.
- Native guest memory gate H4, store/load lowering:
  [protocol](evidence/h4_memory_v1/protocol.md).
  This is a scoped 259-cell lowering, not arbitrary dynamic pointers or a Lisp guest.
- Native arithmetic gate H5, add/sub lowering:
  [protocol](evidence/h5_arithmetic_v1/protocol.md).
  This is a scoped 259-cell lowering, not arbitrary ALU pipelines or a Lisp guest.
- Native guest call and return gate H6, call/ret lowering:
  [protocol](evidence/h6_call_return_v1/protocol.md).
  This is a scoped 259-cell lowering, not arbitrary call stacks or a Lisp guest.
- Full-system specification: [SYSTEM_SPEC.md](docs/SYSTEM_SPEC.md)
- Quine research (fixed-3^19): [QUINE_RESEARCH.md](docs/QUINE_RESEARCH.md)
- Specimen-100 research: [SPECIMEN100.md](docs/SPECIMEN100.md) — canonical REPL reproduced; regeneration and truncation research PARTIAL, no behavioral-equivalence claim
- Detailed subsystem plans: [plan index](docs/superpowers/plans/README.md)
- Third-party provenance: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)

No upstream repository is modified. The large MalbolgeLISP specimen and its
manual are not copied here. This repo does not yet contain a Lisp evaluator,
an Unshackled quine, or a proven Unshackled-compatible runtime.
