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

## Project status

- M0 inventory and scope: [BASELINE.md](docs/BASELINE.md)
- Runtime boundary: [ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Evidence and claims: [PARITY_MATRIX.md](docs/PARITY_MATRIX.md)
- Risks: [RISKS.md](docs/RISKS.md)
- Milestones: [PLAN.md](docs/PLAN.md)
- Full-system specification: [SYSTEM_SPEC.md](docs/SYSTEM_SPEC.md)
- Detailed subsystem plans: [plan index](docs/superpowers/plans/README.md)
- Third-party provenance: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)

No upstream repository is modified. The large MalbolgeLISP specimen and its
manual are not copied here. This repo does not yet contain a Lisp evaluator,
an Unshackled quine, or a proven Unshackled-compatible runtime.
