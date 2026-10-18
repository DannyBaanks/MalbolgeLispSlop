# MalbolgeLispSlop implementation plan set

These plans implement the approved [system specification](../../SYSTEM_SPEC.md).
They are proposals; no runtime or synthesizer work has been performed from
them yet.

## Order and dependencies

```text
fixed-3^19 synthesis backend ──► guest Lisp runtime and conformance
               │
               └──────────────► native quine research
```

1. [Fixed-3^19 synthesis backend](2026-10-18-fixed19-synthesis-backend.md)
   establishes reproducible source generation. It must synthesize variable
   behavior, branch, memory access, and a loop before the full Lisp guest can
   start.
2. [Guest Lisp runtime](2026-10-18-guest-lisp-runtime.md) depends on that
   synthesis gate. It defines the language contract first, then implements and
   tests every promised feature in the guest.
3. [Native quine research](2026-10-18-fixed19-native-quine.md) can start after
   the synthesis backend has its first working vertical slice. It is an
   independent research track; a failed bounded search is reported as
   `NOT_DEMONSTRATED`, never as proof that no quine exists.

The complete product is achieved only when the guest-runtime and native-quine
gates both pass, with the evidence and reproducibility requirements from the
system specification. A Classic `3^10` result never substitutes for a
fixed-`3^19` result.

## Shared implementation conventions

- Host toolchain and conformance code: Python 3.12 standard library; use
  `unittest` unless a later approved plan changes the dependency policy.
- Guest execution engine: existing Zig 0.16.0 `build/bolge19`, with
  `--loader canonical` for generated text images unless a fixture explicitly
  tests raw loading.
- Build command: `./tools/build.sh`.
- Test command: `python3 -m unittest discover -s tests -v`.
- Generated images and temporary search output go under ignored `build/`.
  Durable evidence goes under a new, unique `evidence/<milestone>/<run-id>/`
  path; never overwrite an earlier run.
- No hand-authored or hand-patched Malbolge instruction bytes. Declarative
  guest IR, language semantics, constraints, and the host generator are
  reviewable source; the target instruction stream must be generated.
- The target is the fixed-`3^19` profile implemented by `bolge19`. No plan
  establishes parity with dynamically widening Unshackled or Malbolge Free.
- A host Lisp model is permitted as a test oracle only. The product guest must
  parse and evaluate every claimed Lisp form itself.
- Do not publish, push, release, or modify upstream repositories as part of
  these plans.
