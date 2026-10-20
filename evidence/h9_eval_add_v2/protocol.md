# H9 v2: native fixed-frame digit addition

Date: 2026-10-20. Scope: `(+ a b)`, a/b decimal digits 0..9, optional LF/CRLF,
then EOF, at most nine input bytes. Decimal output 0..18 without newline.
Malformed frames up to nine bytes halt without output. The caller closes stdin.
General Lisp, longer inputs, nesting and multi-digit operands: NOT_DEMONSTRATED.

## Construction and cause

The v1 image overwrote its first operand. V2 saves the nine read values into
separate data cells. A native circuit verifies punctuation and line endings,
decodes two digit values into one-hot flags, ANDs the operands, then combines
sum rails into decimal units and tens. Every operation executes as canonical
Malbolge instructions. The host does not evaluate the runtime input.

The data ring spans 40..94; register loads restore their value via two CRAZY
operations controlled by EOF. Fixed-size action blocks make relocation stable.
Two layout passes synthesize the conditional landing addresses. `WriteDecimal`
is an explicit module IR operation; the old byte-output H9 template is rejected.
The compiler emits the same image regardless of which consistent cases are used.

## Campaign

Command: `python3 -B tools/verify_h9_eval_add.py --engine build/h9-v2/bolge19`.
The VM was freshly compiled from `src/bolge19.zig` using Zig 0.16.0 ReleaseFast.
The source digest, binary digest, platform, Python version, command, cwd, status,
raw bytes and per-run expectations are recorded in each unique run directory.

Final run: `runs/20261020T082407Z-ae2db440/`.

| Claim/control | Observation | Status |
|---|---|---|
| Each pair a,b in 0..9, for EOF/LF/CRLF | 300 native outputs match independently computed decimal sums | DEMONSTRATED_SCOPED |
| Malformed frames | 10 representative frames halt with no output | DEMONSTRATED_SCOPED (not exhaustive malformed-input coverage) |
| Source line wrapping | Three wrapped-image executions match | DEMONSTRATED_SCOPED |
| Remove first/second operand read or final output | All three mutants fail the expected output | Negative controls passed |
| Historical v1 | All three counterexamples still fail addition | Historical claim refuted |
| Independent Python transition model | `(+ 1 1)` -> `2`, `(+ 9 9)` -> `18` | Matches native VM |
| Image size | 4,837,558 canonical cells | Measured |
| Valid execution steps | 4,837,453 / 4,837,454, excluding terminal HALT | Measured VM telemetry |
| General Lisp or generic IR lowering | Not implemented by this backend | NOT_DEMONSTRATED |

Total: 319 native runs, all expectations met; two independent model runs. These
counts distinguish intentional mutant failures from successful sum evaluations.
Each run is sealed by its own SHA256SUMS.txt. No v1 raw evidence is changed.

A first v2 campaign under `runs/20261020T082152Z-f6622882/` also passed; the final
campaign additionally uses the fresh VM binary and the anchored backend profile
path. Source snapshots are identified by their hashes, not assumed from prose.
