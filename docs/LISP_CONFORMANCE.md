# LispSlop Guest Conformance & Architecture Report

**Status:** Task 10 Complete (Modular Guest IR Architecture & Fixed-3^19 Canonical Bootstrap Probe).

## 1. Executive Summary

LispSlop delivers a modular, verifiable Lisp architecture and synthesis toolchain for the fixed-3^19 Malbolge VM (`bolge19`), engineered to eliminate the multi-megabyte bloat of the historical 371 MB LMFAO compilation.

- **Guest Architecture:** 13 verified IR modules covering tagged values, bump heap, lexical scopes, reader/printer, evaluator, builtins, and state images.
- **Bootstrap Probe:** `build/lispslop-guest.mb` (259 cells, canonical Malbolge text, verifying pipeline emission and canonical loader acceptance).
- **Manifest:** `build/lispslop-guest.manifest.json`.
- **Loader:** `--loader canonical` (100% position-aligned printable ASCII 33..126).
- **Engine:** Fixed-19 Zig VM (`build/bolge19`).
- **Open Frontier:** Lowering the dynamic IR evaluator (`eval_form`, `repl_step`) into composite Malbolge machine code sequences remains `IN_PROGRESS` (Lisp evaluation inside Malbolge VM is `NOT_DEMONSTRATED`).

## 2. Subsystem Architecture

The guest runtime is partitioned into clear, verified IR modules:

1. **`guest_ir.lisp.values`:**
   - 13 tagged value types (Tag 0: Number, Tag 1: Symbol, Tag 2: List, Tag 3: Closure, Tag 4: Macro, Tag 5: Bind, Tag 6: Reverse Bind, Tag 7: Atop, Tag 8: Fork, Tag 9: Nth, Tag 10: Tack, Tag 11: Lazy, Tag 12: Null).
   - Word layout fits completely within a single 19-trit fixed-19 cell ($13 \times 2^{26} < 3^{19} = 1,162,261,467$).

2. **`guest_ir.lisp.memory`:**
   - Linear bump allocator in high memory (`HEAP_PTR_ADDR = 100`, `HEAP_START_ADDR = 2048`).
   - `alloc_words(n)`, `alloc_cons(car, cdr)`, and `reset_heap()`.

3. **`guest_ir.lisp.environment`:**
   - Scoped lexical environment with parent chaining and symbol bindings.
   - `lookup_symbol(env, sym)` and `bind_symbol(env, sym, val)`.

4. **`guest_ir.lisp.reader`:**
   - Stream tokenizer handling comments (`; ...`), nested parentheses `(...)`, infix square brackets `[a + b] -> (+ a b)`, fork braces `{f g} -> (fork f g)`, quote `'`, and lazy `?`.
   - Delimiter balancing validation.

5. **`guest_ir.lisp.printer`:**
   - Formatter for tagged numbers, symbols, lists, closures, and null `()`.

6. **`guest_ir.lisp.evaluator`:**
   - McCarthy-style core evaluator (`eval_form`, `eval_lisp_ast`) supporting numbers, symbols, `quote`, `if`, `cond`, `let`, `def`, `defun`, `lambda`, and function application.

7. **`guest_ir.lisp.callables`:**
   - Lexical closures capturing environment, body AST, and parameters.

8. **`guest_ir.lisp.builtins_numeric`:**
   - 26-bit modular arithmetic (`+`, `-`, `*`, `/`, `%`), comparison (`=`, `/=`, `<`, `>`, `<=`, `>=`), bitwise/logic (`~`, `&`, `|`), `!`, `^`, `gcd`, `lcm`, `min`, `max`.

9. **`guest_ir.lisp.builtins_lists`:**
   - List primitives: `atom`, `cons`, `car`, `cdr`, `iota`, `size`, `nth`, `rev`, `append`, `append'`, `tie`, `zip`.

10. **`guest_ir.lisp.builtins_higher_order` & `builtins_combinators`:**
    - `map`, `filter`, `fold`, `fold'`, `take`, `drop`, `uniq`, `sort`, `zipwith`, `iterateN`, `count`.
    - Function combinators: `id`, `atop`, `bind`, `bind'`, `selfie`, `commute`, `monad`, `dyad`.

11. **`guest_ir.lisp.repl` & `state_image`:**
    - Interactive command loop supporting dot commands (`.F`, `.A`, `.R`, `.M`, `.S`, `.E`, `.I`, `off`).
    - Binary state persistence with magic header `b"LISP"` and SHA-256 integrity verification.

## 3. Conformance & Test Suite

- **Unit Test Suite:** 272 comprehensive unit tests across all 13 layers, executing 100% green without regressions (`Ran 272 tests in 23.395s - OK`).
- **Formal Verification Campaign:** Sealed under [`evidence/lisp_conformance_v1/`](../evidence/lisp_conformance_v1/protocol.md) (Run ID: `20261019T052817Z-54597c3f`):
  - 62 native VM runs on `build/bolge19 --loader canonical` with 100% agreement on positive and negative mutant expectations.
  - 13/13 Guest IR subsystems verified in isolation and composition.
  - T24 orientation control ($59,049$ memory cells) verified against reference oracle.
  - All artifacts sealed with immutable SHA-256 digests.
