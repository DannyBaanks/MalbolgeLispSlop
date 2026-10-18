# Fixed-19 synthesis feasibility

**Updated:** 2026-10-18
**Target:** `fixed-3^19`, canonical loader, `bolge19`
**Current gate:** `NOT_DEMONSTRATED` for branch, guest memory, arithmetic, loops, and calls.

## Result

The backend has one certified lowering: straight-line `ReadA, WriteA, Halt`.
It derives the bytes from the fixed profile and returns
`direct-m1-lowering-v1`; generated artifacts and their manifests require that
recognized proof token. The manifest verifier recomputes the lowering from the
declared goal, fixed profile, and search bounds, then compares the exact image;
generation also runs that image in the real `bolge19` executable.

The advanced-module path enumerates canonical dispatch streams, but I/O cases
and structural trace guards are only candidate filters. They cannot establish
that a candidate implements the declared IR semantics. `compile_module`
retains a matching image as `observational_candidate` and never returns
`FOUND` for it until a feature-specific semantic lowering exists. The
capability probe reports `DEMONSTRATED` only for a `FOUND` image carrying a
semantic proof and passing every declared case in the real VM. No advanced
semantic lowerings currently exist.

The regression `branch-lookalike` has two branch arms that halt with identical
empty output. At a 5,000-node bound, the old trace filters accepted an
unrelated dispatch stream as a match; after the fix it remains an
observational candidate and the result is `BUDGET_EXHAUSTED`, with no image or
proof. The countdown cases now require each intermediate value (`03 02 01
00` for input `03`) as well as zero, so a constant-zero output cannot pass its
finite cases.

The post-fix campaign examined 1,000 nodes for each of five targets with
`max_cells=8`, `max_steps=128`, and inclusive `max_address=64`. Every search
returned `BUDGET_EXHAUSTED`; none produced an observational candidate within
these first 1,000 nodes. The last candidate was `bC%N` (SHA-256
`6bb4ef89168f1d9881fa627f53154331ae1c28511c3e3c87fcc7d25eaa6b0d9e`). It
halted in the real VM after 74 steps and emitted `00` for each case, which
mismatched at least one declared output for every target, including the
strengthened countdown. This bounded run does not demonstrate any advanced
feature and does not prove that no implementation exists.

The guest Lisp runtime plan remains blocked by its explicit dependency gate.
Do not treat the typed module descriptions or host-side expected cases as
guest execution evidence.

## Capability records

Every target used `max_cells=8`, `max_nodes=1000`, `max_steps=128`, and
inclusive `max_address=64`. Each bounded search explored exactly 1,000
canonical dispatch sequences and returned `BUDGET_EXHAUSTED`. Each final
candidate had role `last_explored_candidate`; none passed both its I/O cases
and trace filters in this search prefix.

| Target | Declared behavior and cases | Result | Last candidate SHA-256 | Actual VM result |
|---|---|---|---|---|
| Branch on zero | Input `00` emits `Z`; `01` and `ff` emit `N` | `NOT_DEMONSTRATED` | `6bb4ef89168f1d9881fa627f53154331ae1c28511c3e3c87fcc7d25eaa6b0d9e` | `HALT`, 74 steps; outputs `00`, `00`, `00` (mismatch) |
| Guest store/load | Store one input byte at guest address 32, reload it, and emit it for `00`, `01`, `ff` | `NOT_DEMONSTRATED` | same last candidate and digest | `HALT`, 74 steps; outputs `00`, `00`, `00` (mismatch) |
| Add/subtract | Compute `a + b - 1` modulo `3^19`; emit low byte for `0001`, `0101`, `ffff` | `NOT_DEMONSTRATED` | same last candidate and digest | `HALT`, 74 steps; outputs `00`, `00`, `00` (mismatch) |
| Countdown loop | Emit each value while decrementing `00`, `01`, and `03` to zero | `NOT_DEMONSTRATED` | same last candidate and digest | `HALT`, 74 steps; outputs `00`, `00`, `00` (mismatch, including `0100` and `03020100`) |
| Call/return | Call an identity function and return each of `00`, `01`, and `ff` | `NOT_DEMONSTRATED` | same last candidate and digest | `HALT`, 74 steps; outputs `00`, `00`, `00` (mismatch) |

The final VM campaign ran the last generated candidate for every exact case
and captured raw stdout/stderr. A separate zero-node control returns
`BUDGET_EXHAUSTED` with `explored_nodes=0`, so an unsearched goal is never
reported as unsatisfiable.

## Operation contracts in the typed IR

- `BranchZero(value, zero_target, nonzero_target)` transfers to the named
  block according to whether the guest value is zero.
- `Jump(target)` transfers unconditionally to a block in the current function.
- `Load(destination, address)` reads one guest word; `Store(address, value)`
  writes one guest word. Address bounds are part of the compile/run budget.
- `Add` and `Sub` operate on fixed-profile words modulo `3^19`.
- `Call(function, arguments, destination)` enters a function and binds its
  return value when a destination is present; `Return(value)` returns that
  value to the caller.
- The countdown example combines zero branching, subtraction, and a backward
  jump. Its small input cases do not demonstrate an arbitrary-width loop.

These are IR contracts only. None has a demonstrated guest implementation.

## Route implication (2026-10-18)

[Gate L1](../evidence/loader_gate_v1/protocol.md) shows an already-compiled
opcode-aligned-text image from the HeLL/LMFAO line running correctly on this
same VM: 5/5 sealed oracles byte-exact, agreeing with the upstream `Unshackled`
engine, with the raw loader as a negative control. That does not move any row of
the table above — the search lowering still has no guest implementation for
branch, memory, arithmetic, loops or calls — but it changes what the gate is
evidence *about*. The blocker is candidate generation, not the machine: a guest
program can already reach `fixed-3^19` by compilation, so the search route now
competes against a compiler route rather than being the only route. Any move to
the compiler route needs its own licensing and reproduction decision first
(LMFAO is GPLv3, ELVM is MIT, this repository is MIT, and the workspace rule is
copy-and-revalidate, never import).

[Gate H1](../evidence/hell_frontend_v1/protocol.md) took that decision the same
day, in the direction that needs no import: `slopsynth/lang.py` is a textual
`.slop` front-end of our own over the IR and encoder that already existed, and
`slopsynth/assemble.py` relocates a guest to an absolute cell address and refuses
to emit any image the canonical loader would reject. It certifies two guests —
the echo text reaching `ubO` byte-identically, and a guest placed at cells
564–566 that runs under `--loader canonical` and breaks under `raw`. That is a
compiler route with nothing GPLv3 in it, but its emitted language is still the
three-opcode straight-line subset: the search lowering this table measures has
not gained branch, memory, arithmetic, loops or calls, and the compiler route
gained branch in Gate H2 and scoped loop in Gate H3.

## Reproduction

Run from the repository root:

```sh
./tools/build.sh
python3 -m unittest tests.test_synth_capabilities tests.test_synth_echo -v
python3 -m unittest discover -s tests -v
python3 tools/probe_synthesis_capabilities.py --max-cells 8 --max-nodes 1000 --max-steps 128 --max-address 64
```

The final campaign command, generated candidates, exact input/output bytes,
actual VM stdout/stderr, report, and per-file SHA-256 entries are stored in
`evidence/synthesis/capability-search-2026-10-18T074621Z/`. Its report records
revision `19162614bf6b18723753de892317c8c30f80bf05`; `report.json` SHA-256 is
`757e98d404e0fa766587b6f5505737abd1958473e62dc6c0fe305022b8fa62f9`. The
`073257Z/` campaign is pre-hardening historical evidence, and the `074512Z/`
campaign is a preserved intermediate run before the proof-manifest commit.
The full discovered suite covers the profile, model, straight-line synthesis,
and capability-gate contracts; it does not turn any `NOT_DEMONSTRATED` row
into a guest pass.
