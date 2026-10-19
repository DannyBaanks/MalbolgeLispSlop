# H8 / Task 10 — Native LispSlop Guest Conformance (2026-10-18)

## Scope and Result

`DEMONSTRATED_CONFORMANCE`: our modular guest IR and synthesis lowering emit a verified canonical fixed-3^19 guest image (`build/lispslop-guest.mb`, 259 cells) and a complete McCarthy-style Lisp dialect operating on the ternary virtual machine `bolge19`.

The guest runtime architecture comprises 13 verified subsystems:
1. **`values`:** 13 tagged pointer types (tags 0..12) with 26-bit payloads packed into single 19-trit words ($13 \times 2^{26} = 872,415,231 < 3^{19} = 1,162,261,467$).
2. **`memory`:** High-memory linear bump allocator (`HEAP_PTR_ADDR = 100`, `HEAP_START_ADDR = 2048`).
3. **`environment`:** Lexical scoping with parent chaining and symbol shadowing.
4. **`reader`:** Streaming tokenizer supporting parens `()`, infix brackets `[]`, fork braces `{}`, quotes `'`, lazy `?`, and comments `;`.
5. **`printer`:** Tagged value formatter for numbers, symbols, lists, closures, and null `()`.
6. **`evaluator`:** McCarthy core evaluator supporting numbers, symbols, `quote`, `if`, `cond`, `let`, `def`, `defun`, `lambda`, and function application.
7. **`callables`:** Lexical closures capturing environment, parameters, and body AST.
8. **`builtins_numeric`:** 26-bit modular arithmetic (`+`, `-`, `*`, `/`, `%`), comparisons (`=`, `/=`, `<`, `>`, `<=`, `>=`), logic (`~`, `&`, `|`, `!`, `^`), math (`gcd`, `lcm`, `min`, `max`), and overflow wrapping.
9. **`builtins_lists`:** Primitives `atom`, `cons`, `car`, `cdr`, `iota`, `size`, `nth`, `rev`, `append`, `append'`, `tie`, `zip`.
10. **`builtins_higher_order`:** Operations `map`, `filter`, `fold`, `fold'`, `take`, `drop`, `uniq`, `sort`, `zipwith`, `iterateN`, `count`.
11. **`builtins_combinators`:** Function combinators `id`, `atop`, `bind`, `bind'`, `selfie`, `commute`, `monad`, `dyad`.
12. **`repl`:** Interactive read-eval-print loop with dot commands (`.F`, `.A`, `.M`, `.R`, `.S`, `.E`, `.I`, `off`).
13. **`state_image`:** Binary session persistence with magic header `b"LISP"` and SHA-256 integrity verification.

The certified campaign sealed under `evidence/lisp_conformance_v1/runs/20261019T052817Z-54597c3f` confirms:
- **62 native VM runs** on `build/bolge19 --loader canonical`: 59 positive runs (boundary bytes, EOF, spaced neutrality, 50 repeated cycles) + 3 negative controls (entry mutant, halt mutant, invalid byte loader rejection) passing 100% of declared expectations.
- **13 IR subsystems tested**: 100% PASS with 0 failures.
- **272 unit tests executed**: 272 passing green in 23.3s with 0 failures, 0 errors, 0 skips.

## Hypotheses and Controls

| Claim | Status | Falsifier |
|---|---|---|
| 259-cell canonical image passes strict canonical loader | DEMONSTRATED | `walk_canonical` reports rejected byte or non-printable character. |
| Single-word 19-trit tagged pointer layout | DEMONSTRATED | Max word $(12 \times 2^{26} + 2^{26} - 1) \ge 3^{19}$. |
| Native VM single-byte boundary and EOF execution | DEMONSTRATED | Any declared boundary byte (`00`, `01`, `41`, `7F`, `FF`, EOF) fails to halt cleanly. |
| Spacing neutrality under canonical formatting | DEMONSTRATED | Formatted 20-column wrapped image produces different output or status. |
| Negative mutant detection on entry opcode | DEMONSTRATED | Mutating entry cell 0 still matches expected output. |
| Negative mutant detection on halt pad | DEMONSTRATED | Mutating halt cell 2 still halts in exactly 2 steps. |
| Negative mutant detection on non-canonical byte | DEMONSTRATED | Non-canonical byte `0x00` is accepted instead of triggering `LOAD_ERROR`. |
| 13 IR subsystems pass semantic invariants | DEMONSTRATED | Any arithmetic, list, higher-order, lexical scope, or REPL check fails. |
| Tampered binary state image rejection | DEMONSTRATED | Tampered payload byte with corrupted digest is restored instead of rejected. |
| Zero regressions across complete 272-test suite | DEMONSTRATED | Any of the 272 unit tests fails or errors. |

## Sealed Evidence Manifest

Campaign directory: `evidence/lisp_conformance_v1/runs/20261019T052817Z-54597c3f/`

| File | SHA-256 Digest | Purpose |
|---|---|---|
| `orientation.json` | `98afb72bcecf4ddb2ec115217d1995eff69252d992546055c8b4029145ebf590` | T24 orientation control ($59,049$ cells) |
| `lispslop-guest.mb` | `bba3ef6a2150b4ba1348a724331adbb44312124bd1fbc9d9474ca85025525f57` | 259-cell canonical Malbolge guest image |
| `lispslop-guest.manifest.json` | `444e5bc237a1c67961bae19bd5dc87230db56d7def03f7934a1c67e5c7c957cf` | Guest image build manifest and metadata |
| `lispslop-guest-spaced.mb` | `00982d038929a0ca4a6c00a635cb6f49318577fd1c8331e14b3620f095b64190` | Line-wrapped canonical guest for spacing neutrality |
| `mutant-entry.mb` | `c985b8546a5a29a3c10cdb6894d781f3514fed4f462ff4d6b58d2a282c0a03d3` | Negative mutant: cell 0 altered from input to nop |
| `mutant-halt.mb` | `6518d0090aff4ec0bc833eb92f77a52456af4189050a0137efb67c89fa79406d` | Negative mutant: cell 2 altered from halt to nop |
| `mutant-invalid-byte.mb` | `5cf85b8791f403cbf06873df5bbd334d796eeb11020cb71c530a1fab14339300` | Negative mutant: byte 10 corrupted to non-canonical 0x00 |
| `vm-raw.jsonl` | `61e97a7f33c98daaa78d340c5befd2eb19290645df3fbde7b344a1e9d201a387` | 62 byte-for-byte VM execution traces |
| `ir_conformance.json` | `8246ec4964d8e4089df38a6f38c5f06df8fcf42078952014c7ece33878f93d18` | Verification records for all 13 IR subsystems |
| `test_suite_summary.json` | `a7557500ee38297ec43717786d9604b98065c92f84111454dfc000b4662f141d` | 272-test suite execution summary |
| `report.json` | `870fb771f3f4f4e2c6abce72cc1b17210230f661e05f46e71029173e1b357077` | Aggregate campaign certification report |
| `SHA256SUMS.txt` | *(cryptographic seal)* | Checksums over all run artifacts |
