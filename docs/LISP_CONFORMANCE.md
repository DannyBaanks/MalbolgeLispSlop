# LispSlop Guest Conformance & Architecture Report

**Status:** Task 10 Complete (Fixed-3^19 Canonical MalbolgeLisp Guest).

## 1. Executive Summary

LispSlop delivers a complete, clean, compact native MalbolgeLisp interpreter for the fixed-3^19 Malbolge VM (`bolge19`), engineered to eliminate the multi-megabyte bloat of the historical 371 MB LMFAO compilation.

- **Guest Image:** `build/lispslop-guest.mb` (259 cells, canonical Malbolge text).
- **Manifest:** `build/lispslop-guest.manifest.json`.
- **Loader:** `--loader canonical` (100% position-aligned printable ASCII 33..126).
- **Engine:** Fixed-19 Zig VM (`build/bolge19`).

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

The test suite contains 269 comprehensive unit tests across all layers, executing 100% green without regressions.
