# LispSlop Language Specification v1.0

## 1. Overview and Target Machine

LispSlop is a functional Lisp dialect designed to execute natively in a fixed rotation-width 19-trit Malbolge Unshackled machine (`fixed-3^19`, $END = 3^{19} = 1,162,261,467$). Unlike bloated Brainfuck-emulated Malbolge interpreters that require hundreds of megabytes of unrolled tape instructions, LispSlop synthesizes compact, native Malbolge instructions where single 19-trit cells natively represent pointers and 26-bit integers.

## 2. Value Representation and Type Tags

Every Lisp value in the runtime is an atom represented as a tagged union. In the native machine, a value is represented by a cell or pointer with an explicit tag:

| Tag | Type | Description |
|---|---|---|
| `0` | Number | Unsigned 26-bit integer ($0 \le n < 2^{26} = 67,108,864$). |
| `1` | Symbol | Unbound atom, pointing to an interned ASCII string. |
| `2` | List | Cons pair `(car . cdr)` allocated in the heap. |
| `3` | Closure | Lexical closure: `((parameters body) . environment)`. |
| `4` | Macro | Macro descriptor: `(parameters body)`. |
| `5` | Bind | Partially applied function object via `bind`. |
| `6` | Reverse Bind | Partially applied function object via `bind'`. |
| `7` | Atop | Function composition object via `atop`. |
| `8` | Fork | Function fork object via `fork`. |
| `9` | Nth | Indexed selector object `#N`. |
| `10` | Tack | Tack selector object `$N`. |
| `11` | Lazy | Lazily evaluated expression with captured environment. |
| `12` | Null | Empty list / nil (`null`, `()`, `'()`). |

## 3. Syntax and Reader Grammar

```
toplevel      = s_expr / dot_command
dot_command   = "." [A-Z]
s_expr        = _ (null / comment / number / list / quote / lazy / symbol / nth / tack)
null          = "null"
symbol        = [^ \t\r\n\[\]\(\)\{\}\;\.\'\?\#\$]+
number        = [0-9]+
nth           = "#" number
tack          = "$" number
quote         = "'" s_expr
lazy          = "?" s_expr
list          = parlist / sqlist / forklist
parlist       = "(" listbody
sqlist        = "[" sqlistbody
forklist      = "{" forklistbody
listbody      = _ (s_expr listbody) / ")"
sqlistbody    = _ (s_expr sqlistbody) / "]"
forklistbody  = _ (s_expr forklistbody) / "}"
comment       = ";" [^\n]* "\n" s_expr
_             = [ \t\r\n]*
```

### Infix Transformation
Square bracket lists `[a f b ...]` transform at parse-time into prefix lists `(f a b ...)`. For example:
- `[x + 1]` $\to$ `(+ x 1)`
- `[5 > 3]` $\to$ `(> 5 3)`

### Fork Transformation
Curly brace lists `{f g h}` transform into `(fork f g h)`.

## 4. REPL Protocol and Progress Membrane

The interactive REPL presents a progress membrane:
1. Displays the startup banner:
   ```
   MALBOLGELISPSLOP V1.0 (2026, DANNY & ANTIGRAVITY)
   DOT COMMANDS: .F(eatures) .A(uthor) .R(eset) .M(emory) .S(ymbols) .E(xport) .I(mport)
   % 
   ```
2. For each expression read, the parser emits a dot `.` per parsed character/token.
3. Upon finishing parsing, a pipe `|` is emitted.
4. During evaluation, a dot `.` is emitted for each evaluation step.
5. The evaluated result is formatted and printed, followed by a newline and the `% ` prompt.

## 5. Builtin Feature Inventory (76 Builtins)

The `.F` dot command reports all 76 supported built-in functions:

```
' ~ + - % < > = ! & | * / ^ def defun lambda
cond print atom cons car cdr if let defmacro
iota size nth map filter eval append append'
>= <= max min /= rev any every sort zip id
flatten flatmap tie fold zipwith iterate iterateN
where replicate count take take' drop drop' bind
atop intersperse scan monad dyad selfie commute
fold' scan' uniq off +' -' fork lazy lift bruijn
```

### 5.1 Arithmetic
- `+`, `-`, `*`, `/`, `%`: Unsigned 26-bit arithmetic modulo $2^{26}$.
- `+'`, `-'`: Unbounded arithmetic modulo $3^{19}$ in fixed-19.
- `~`: Boolean negation ($x = 0 \to 1$, $x > 0 \to 0$).
- `!`: Factorial lookup table ($x \le 11$, $x!$, otherwise 0).
- `^`: Exponentiation ($n^m$, $0^0 = 1$).
- `&`, `|`: Logical AND / OR (non-short-circuiting).
- `=`, `/=`, `<`, `>`, `<=`, `>=`: Comparisons returning 1 (truthy) or 0 (falsy).
- `gcd`, `lcm`: Greatest common divisor and least common multiple.
- `min`, `max`: Minimum and maximum of two numbers.

### 5.2 Special Forms & Bindings
- `'` / `quote`: Returns unevaluated argument.
- `def`: Binds a symbol in the global symbol table.
- `defun`: Binds a named function in the global symbol table.
- `lambda`: Creates a lexical closure.
- `if`: Conditional execution `(if cond then else)`. Evaluates condition; if truthy ($>0$), evaluates `then`, otherwise evaluates `else`.
- `cond`: Multi-branch conditional `(cond (c1 e1) (c2 e2) ...)`.
- `let`: Local binding scope `(let ((k1 v1) (k2 v2)) body)`.
- `defmacro`: Macro definition.

### 5.3 Core List Operations
- `cons`: Allocates a cons cell `(a . b)` on the heap.
- `car`: Returns the head of a list.
- `cdr`: Returns the tail of a list.
- `atom`: Returns the integer type tag of a value ($0..12$).
- `print`: Prints value representation and returns it.

### 5.4 Functional Combinators & Sequences
- `monad`: Syntactic helper `(lambda (x) body)`.
- `dyad`: Syntactic helper `(lambda (x y) body)`.
- `map`: Applies function to each element of a list.
- `filter`: Filters list by predicate.
- `fold`, `fold'`: Left and right list reduction.
- `scan`, `scan'`: Cumulative reduction list.
- `iota`: Generates list `(0 1 ... n-1)`.
- `size`: Returns list length.
- `nth`: Retrieves $n$-th element.
- `take`, `take'`, `drop`, `drop'`: Slice prefixes and suffixes.
- `zip`, `zipwith`: Combines two lists.
- `rev`: Reverses a list.
- `bind`, `bind'`: Partial application.
- `atop`: Function composition `(atop f g) x = f(g(x))`.
- `fork`: Fork combinator.
- `lazy`, `lift`: Lazy evaluation thunk and evaluator.
- `off`: Terminates the interpreter cleanly.

## 6. Memory Model and Dot Commands

- **Heap**: Upward-growing memory with a bump allocator.
- **Stack**: Downward-growing call/data stack in high memory.
- `.F`: Displays the list of features.
- `.A`: Displays author and copyright notice.
- `.M`: Displays memory usage in words (`<N>W USED`).
- `.R`: Resets heap and memory allocator to initial state.
- `.S`: Prints the interned global symbols.
- `.E`: Exports memory state to Base64 ASCII dump.
- `.I`: Imports memory state from Base64 ASCII dump.
