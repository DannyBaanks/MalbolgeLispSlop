# H4 — native guest memory store/load lowering (2026-10-18)

## Scope and result

`DEMONSTRATED_SCOPED`: our `.slop` frontend can emit a canonical fixed-3^19
guest that executes guest-memory store and load (`st` / `ld`) **inside bolge19**.
An input byte is read into `A`, stored into guest memory, reloaded from guest memory
back into `A`, written to stdout, and halted.
`examples/store_load.slop` describes this single-block sequence with `read`, `st`, `ld`, `write`, and `halt`.
One 259-cell image implements it natively; no host computation participates once
bolge19 starts the guest.

This is the certified Gate H4 slice, demonstrating guest variable storage without
Brainfuck emulated tape bloat. `tools/assemble.py` dispatches recognized store/load modules
to `lower_memory`. Arbitrary dynamic pointer indirection and heap structures remain unsupported.

## Hypotheses and controls

| Claim | Status | Falsifier |
|---|---|---|
| This store/load sequence runs from our generated source with native memory | DEMONSTRATED_SCOPED | Any input byte mismatches or does not HALT. |
| Whitespace formatting preserves the canonical guest | DEMONSTRATED_SCOPED | Formatted image differs in output/status for a recorded case. |
| The test detects a corrupted pointer relay | DEMONSTRATED_SCOPED | Mutating cell 2 still passes byte input. |
| The test detects corrupted memory data | DEMONSTRATED_SCOPED | Mutating data cell 71 still passes byte input. |
| Arbitrary dynamic memory, general heap, Lisp runtime | NOT_DEMONSTRATED | Outside this implementation. |

## Construction

The lowering uses native Malbolge opcodes and pointer/data constraints over the fixed19 profile:

1. **Involution Storage**: Byte 121 (`'y'`) satisfies $\text{crazy}(\text{crazy}(x, 121), 121) = x$
   for all 256 byte values $x \in [0, 255]$. In fixed19, $121 = 11111_3$ acts as an exact bitwise
   involution mask across the lower 5 trits.
2. **Consecutive Canonical Data Cells**: Positions 71 and 72 both decode to valid canonical opcodes
   with byte 121 ($192 \equiv 4$ `jump`, $193 \equiv 5$ `output`).
3. **Pointer Relay Chain**:
   - At cell 0: `jump` (byte 98, $98 \equiv 4$) jumps to cell 99, setting $D=1$.
   - At cell 99: `input` reads byte $x$ into register $A$, setting $D=2$.
   - At cell 100: `move` reads $M[2]=115$, setting $D=116$.
   - At cell 101: `move` reads $M[116]=46$, setting $D=47$.
   - At cell 102: `move` reads $M[47]=70$, setting $D=71$.
4. **Store and Load Execution**:
   - At cell 103: `crazy` executes on $D=71$, storing $\text{crazy}(x, 121)$ into cell 71; $D \to 72$.
   - At cell 104: `crazy` executes on $D=72$, reloading $\text{crazy}(\text{crazy}(x, 121), 121) = x$ into $A$; $D \to 73$.
   - At cell 105: `output` emits $A \% 256 = x$.
   - At cell 106: `halt` terminates cleanly in exactly 8 CPU steps.
5. **Canonical Loader**: Every cell in the 259-cell image satisfies
   $(byte + pos) \pmod{94} \in \{4, 5, 23, 39, 40, 62, 68, 81\}$ and $33 \le byte < 127$.

## Evidence

`tools/verify_h4_memory.py` executes a full verification campaign against `build/bolge19 --loader canonical`:
- Exhaustive single-byte payload test across all 256 byte values ($0..255$) passes byte-exact.
- EOF test (empty stdin) passes.
- Spacing neutrality on formatted images (`mem-spaced.mb`).
- Negative controls: mutant pointer (`mutant-pointer.mb`) and mutant data (`mutant-data.mb`).
- Total: 263 real VM executions bit-exact on native binary.
