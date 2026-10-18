# Fixed-19 synthesis feasibility

**Run date:** 2026-10-18  
**Target:** `fixed-3^19`, canonical loader, `bolge19`  
**Current gate:** `NOT_DEMONSTRATED` for branch, guest memory, arithmetic, loops, and calls.

## Result

The backend synthesizes the straight-line `ReadA, WriteA, Halt` guest and
checks it against the semantic model and real `bolge19` executable. Its
advanced-module path enumerates canonical dispatch streams in increasing cell
count and profile dispatch order, and applies I/O cases plus structural trace
guards. Every byte is derived from the profile's opcode indices and canonical
positions.

The bounded campaign examined 1,000 nodes for each of five targets with
`max_cells=8`, `max_steps=128`, and inclusive `max_address=64`. Each run used
all 1,000 nodes before finishing the bounded search, so the synthesis status
is `BUDGET_EXHAUSTED`, not an unsatisfiability result. The last candidate was
`bC%N` (SHA-256
`6bb4ef89168f1d9881fa627f53154331ae1c28511c3e3c87fcc7d25eaa6b0d9e`). It
halted in the real VM after 74 steps for every listed case and emitted `00`.
That matched the countdown outputs but did not pass the loop trace guard; the
other targets had at least one output mismatch. Each search covered all
1-cell, 2-cell, and 3-cell streams, then the first 416 of 4,096 4-cell streams;
the remaining search space was not reached. No target is demonstrated.

The guest Lisp runtime plan remains blocked by its explicit dependency gate.
Do not treat the typed module descriptions or host-side expected cases as
guest execution evidence.

## Capability records

Every target used `max_cells=8`, `max_nodes=1000`, `max_steps=128`, and
inclusive `max_address=64`. Each bounded search explored exactly 1,000
canonical dispatch sequences and returned `BUDGET_EXHAUSTED`.

| Target | Declared behavior and cases | Result | Last candidate SHA-256 | Actual VM result |
|---|---|---|---|---|
| Branch on zero | Input `00` emits `Z`; `01` and `ff` emit `N` | `NOT_DEMONSTRATED` | `6bb4ef89168f1d9881fa627f53154331ae1c28511c3e3c87fcc7d25eaa6b0d9e` | `HALT`, 74 steps; outputs `00`, `00`, `00` (mismatch) |
| Guest store/load | Store one input byte at guest address 32, reload it, and emit it for `00`, `01`, `ff` | `NOT_DEMONSTRATED` | same last candidate and digest | `HALT`, 74 steps; outputs `00`, `00`, `00` (mismatch) |
| Add/subtract | Compute `a + b - 1` modulo `3^19`; emit low byte for `0001`, `0101`, `ffff` | `NOT_DEMONSTRATED` | same last candidate and digest | `HALT`, 74 steps; outputs `00`, `00`, `00` (mismatch) |
| Countdown loop | Decrement `00`, `01`, and `03` to zero and halt | `NOT_DEMONSTRATED` | same last candidate and digest | `HALT`, 74 steps; outputs `00`, `00`, `00`; cases match but loop trace guard fails |
| Call/return | Call an identity function and return each of `00`, `01`, and `ff` | `NOT_DEMONSTRATED` | same last candidate and digest | `HALT`, 74 steps; outputs `00`, `00`, `00` (mismatch) |

The VM campaign ran the last generated candidate for every exact case and
captured raw stdout/stderr. A separate zero-node control returns
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

## Reproduction

Run from the repository root:

```sh
./tools/build.sh
python3 -m unittest tests.test_synth_capabilities tests.test_synth_echo -v
python3 -m unittest discover -s tests -v
python3 tools/probe_synthesis_capabilities.py --max-cells 8 --max-nodes 1000 --max-steps 128 --max-address 64
```

The campaign command, generated last candidates, exact input/output bytes,
actual VM stdout/stderr, report, and per-file SHA-256 entries are stored in
`evidence/synthesis/capability-search-2026-10-18T073257Z/`. The earlier
`2026-10-18-capability-gate-01/` directory preserves the pre-enumerator test
run and is historical. The full discovered suite covers the profile, model,
straight-line synthesis, and capability-gate contracts; it does not turn any
`NOT_DEMONSTRATED` row into a guest pass.
