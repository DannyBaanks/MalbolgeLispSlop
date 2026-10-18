# Parity and evidence matrix

| Surface | Fixed-3^19 `bolge19` / MalbolgeLISP profile | Original Unshackled reference | Classic Malbolge |
|---|---|---|---|
| Address-space model | Fixed `END = 3^19` in inspected source | Random initial width, dynamic growth per inspected semantics notes | Separate 3^10 model |
| Runtime under this repo | Vendored Zig forensic VM; tiny M1 probe passes (see report) | Not implemented here | Not used for M1 |
| Loader | `raw` and strict `canonical` options in the VM | Canonical text-loading behavior is related but not full semantic parity | Different artifact/loader conventions |
| I/O | Byte input/output; EOF maps to `END - 1` in this VM | Unicode and EOF semantics differ per local notes | Not tested here |
| Independent backend agreement | `[NOT_DEMONSTRATED]` | `[NOT_DEMONSTRATED]` | Classic backends do not establish 3^19 agreement |
| Lisp semantics in guest | `[NOT_DEMONSTRATED]` | `[NOT_DEMONSTRATED]` | `[NOT_DEMONSTRATED]` |
| Quine | `[NOT_DEMONSTRATED]` | `[NOT_DEMONSTRATED]` | Existing Classic quines are out of scope |

M1 established only the exact tiny guest cases in its run report. It does not
upgrade any row about full Unshackled parity, Lisp semantics, backend
independence, or quines. A related C `fast20` executable matched the Zig VM on
one input byte; that comparison is recorded in
`evidence/m1/fast20-differential.json` and is not independent validation.
