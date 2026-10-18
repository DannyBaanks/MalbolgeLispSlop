# M0 baseline inventory

**Captured:** 2026-10-18 (America/Mexico_City)
**State:** M0 complete; M1 slice is a separate, explicitly bounded claim.

## Scope decision

“MalbolgeLispSlop” starts against the **fixed 3^19 profile implemented by
`bolge19` and described as the MalbolgeLISP/`fast20` profile**. `bolge19` has
`END = 1,162,261,467 = 3^19`, and its source says it reproduces `fast20.c`
dispatch semantics. This is the concrete executable target referenced by the
MalbolgeLISP compose.

The name “Unshackled” has a separate, broader meaning in the inspected
`MALDOOM/vendor/Unshackled.c`: the original implementation starts with a
randomized width and grows it dynamically. The local MalbolgeFree semantics
notes therefore mark exact K=19 parity with that implementation
`NOT_DEMONSTRABLE`. We will call the first target **fixed-3^19** in claims and
tests. No general Unshackled parity is implied.

## Inspected repositories and provenance

The source of truth is the sibling repository `malbolge-lisp-forensics`, not
the older language checkout. Both were clean when inspected. The project
copies only the 428-line Zig VM listed below; it does not modify either source
repository.

| Item | Observed revision / digest | Finding |
|---|---|---|
| `malbolge-lisp-forensics` | `main` at `a0ce1642f7c3ba46175d6623edfead5197d6a7c5`, clean; `src/bolge19/main.zig` SHA-256 `47758a3f667f4089f6029d86130b94f14f082d4c113a212b8ff571d84113e8a3` | Fixed-3^19 VM source; MIT forensic-additions license |
| `malbolge-lisp-forensics/LICENSE` | SHA-256 `e922e7d34068ba65bb0466f19be10a4d6b8c10ea6bc76fed5b7180eca5e6297a` | Covers forensic additions in `src/`, `scripts/`, `docs/`, and `evidence/` |
| `malbolge-lisp` | `master` at `c64eececd6351fc8d297e932cde73be698ade6ec`, clean, one commit ahead of origin | Separate upstream language checkout; not changed |
| `malbolge-lisp/fast20.c` | SHA-256 `89d6e89101d36dce39c0b9abcbab344f9a530b08690db9231c4861d2df55552f` | Current C interpreter inspected for context |
| `malbolge-lisp/fast20_original.c` | SHA-256 `607467b591f3446e7e54dfccfee0fff867a03f325ca2767ff49be71e8a431143` | Original C version inspected for context |

The forensics notes describe two `fast20` corrections: Cygwin's
`mmap(MAP_FIXED)` failure was changed to `mprotect`, and the Linux translation
table read now checks that the index is below 135. These are reported as
forensics findings; this project does not claim to have independently
reproduced those defects.

## Claims table

| Claim | Status | Evidence / limit |
|---|---|---|
| `bolge19` models a fixed 3^19 address space | `[DEMONSTRATED IN SOURCE]` | `src/bolge19/main.zig` pins `END` to 1,162,261,467 and performs fixed-region dispatch; hash above |
| `bolge19` can execute a full MalbolgeLISP REPL | `[REPORTED; NOT REPRODUCED IN M0]` | Forensics reproduction notes report a large specimen run; this project does not redistribute or rerun it |
| Original Unshackled is exactly the fixed-3^19 profile | `[CONTRADICTED]` | Inspected semantics notes describe randomized initial width and dynamic growth |
| A small guest can be executed and observed byte-for-byte here | `[TO VERIFY IN M1]` | The M1 fixture and verifier are in this repository |
| Lisp evaluation takes place inside Malbolge | `[NOT_DEMONSTRATED]` | No evaluator has been implemented or independently shown in this repo |
| A native Unshackled quine exists | `[NOT_DEMONSTRATED]` | No such artifact is included or established by the inspected evidence |

## Environment observed

- Linux x86_64, Ubuntu 24.04 host
- Python 3.12.3
- Zig 0.16.0
- GCC 13.3.0 and Clang 18.1.3

The source snippets and hashes above are recorded in
[`evidence/m0/inventory.txt`](../evidence/m0/inventory.txt). M1 execution
evidence is recorded separately and must not be used to upgrade unrelated
claims.
