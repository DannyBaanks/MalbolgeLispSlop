# MalbolgeLISP v1.2 / LispSlop Language Contract

**Status:** working freeze; this document defines both the external reference boundaries from MalbolgeLISP v1.2 and the internal native language definition for LispSlop on `fixed-3^19`. Unresolved features remain `DECLARED` in `lisp-feature-matrix.json`.

The reference executable is `/tmp/opencode/specimen100-m1-lisp.mb`, run by the same fixed19 VM with the raw loader. Every result below has immutable request, input, output, result and hash files under `evidence/language_contract_v1/`. Supervisor timeout and VM step exhaustion are observations, not Lisp errors or proof that an expression is undefined.

## 1. Fixed Target Choices

- Lisp integers are unsigned 26-bit values: `0 <= n < 2^26` (`2^26 = 67,108,864`). This language domain is narrower than the VM word domain `0 .. 3^19-1`.
- `+` and `+'` return the sum modulo `2^26`. Both returned `0` for `67,108,863 + 1` in the reference runs.
- `-` and `-'` return the nonnegative modular difference in the same domain. This is the target contract choice for subtraction. It does not define other partial operations such as division by zero. The reference underflow probes `(- 0 1)` and `(-' 0 1)` did not finish within 240 seconds / 15,000,000,000 VM steps; their behavior remains `NOT_DEMONSTRATED` against the reference.
- Numeric equality and inequality, numeric ordering, and `~` return `0` for false and `1` for true. The reference returned the expected values for `=`, `/=`, `~`, `<`, and `>` in the cases below. This fixes result encoding; truth tests for nonnumeric Lisp values are still open.

These arithmetic choices are part of our fixed19 profile. They are not a claim that the original MalbolgeLISP image implements 26-bit modular semantics for all inputs. Any additional confirmed difference will be recorded beside its fixture before the feature row advances.

## 2. Captured Reference Cases

| Input | Output | Evidence | Result |
|---|---:|---|---|
| `(+ 2 1)` | `3` | `runs/20261018T-safe-arithmetic/` | `MAX_STEPS` after later input; this row was emitted |
| `(* 3 3)` | `9` | `runs/20261018T-safe-arithmetic/` | `MAX_STEPS` after later input; this row was emitted |
| `(% 5 2)` | `1` | `runs/20261018T-safe-arithmetic/` | `MAX_STEPS` after later input; this row was emitted |
| `(> 5 6)` / `(< 5 6)` | `0` / `1` | `runs/20261018T-safe-arithmetic/` | `MAX_STEPS` after later input |
| `(= 6 6)` | `1` | `runs/20261018T-safe-arithmetic/` | `MAX_STEPS` after later input |
| `(= 6 7)` / `(= 6 6)` | `0` / `1` | `runs/20261018T-equality-truth/` | `HALT`, 6,934,983,070 VM steps |
| `(/= 6 7)` / `(/= 6 6)` | `1` / `0` | `runs/20261018T-equality-truth/` | `HALT`, 6,934,983,070 VM steps |
| `(~ 0)` / `(~ 1)` | `1` / `0` | `runs/20261018T-equality-truth/` | `HALT`, 6,934,983,070 VM steps |
| `(+' 67108863 1)` | `0` | `runs/20261018T1840Z-numbers-primed/` | `WALL_TIMEOUT` during the following underflow form |
| `(+ 67108863 1)` | `0` | `runs/20261018T1840Z-numbers-bounded/` | `WALL_TIMEOUT` during the following underflow form |
| `(scan + 10 '(1 2))` | `E095` | `runs/20261018T1828Z-semantics-01/` | `HALT`; this was the first form, later forms did not run |

## 3. Value Representation and Type Tags

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

## 4. Syntax and Reader Grammar

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

## 7. Unresolved Before Guest-Language Gate

- Semantics and evaluation order for every overload, including list equality, arithmetic arity and error cases, `gcd`, `lcm`, `bind'`, and stateful operators. Documented binary arithmetic operators take two operands; unary operators such as `!` and `~` take one. No variadic extension is assumed.
- Lexical shadowing, closures after creator return, recursion, macro expansion, short-circuiting and lazy memoization, checked against minimal original cases.
- Reader and printer edge cases, numeric token overflow, malformed forms, language error continuation, EOF, and all `.F/.A/.R/.M/.S/.E/.I/off` behaviors.
- Whether the original reaches different results if given more than the explicit step and wall budgets. Current timeouts do not answer that.

No guest code may consume this document as a substitute for the missing cases. Each row remains `DECLARED` until the feature matrix has exact positive and negative fixtures; implementation and demonstration need separate guest tests and replayed evidence.
