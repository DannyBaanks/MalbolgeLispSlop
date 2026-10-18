# MalbolgeLISP v1.2 language contract (working freeze)

**Status:** partial; this document is not a claim of implementation or full
reference conformance. The independent guest must follow the target choices
below. Unresolved features stay open in `lisp-feature-matrix.json`.

The local manual is the surface reference, but it is not redistributed here.
The reference executable is `/tmp/opencode/specimen100-m1-lisp.mb`, run by the
same fixed19 VM with the raw loader. Every result below has immutable request,
input, output, result and hash files under `evidence/language_contract_v1/`.
Supervisor timeout and VM step exhaustion are observations, not Lisp errors or
proof that an expression is undefined.

## Fixed target choices

- Lisp integers are unsigned 26-bit values: `0 <= n < 2^26` (`2^26 =
  67,108,864`). This language domain is narrower than the VM word domain
  `0 .. 3^19-1`.
- `+` and `+'` return the sum modulo `2^26`. Both returned `0` for
  `67,108,863 + 1` in the reference runs.
- `-` and `-'` return the nonnegative modular difference in the same domain.
  This is the target contract choice for subtraction. It does not define other
  partial operations such as division by zero. The reference underflow probes
  `(- 0 1)` and `(-' 0 1)` did not finish within 240 seconds / 15,000,000,000
  VM steps; their behavior remains `NOT_DEMONSTRATED` against the reference.
- Numeric equality and inequality, numeric ordering, and `~` return `0` for
  false and `1` for true. The reference returned the expected values for
  `=`, `/=`, `~`, `<`, and `>` in the cases below. This fixes result encoding;
  truth tests for nonnumeric Lisp values are still open.

These arithmetic choices are part of our fixed19 profile. They are not a claim
that the original MalbolgeLISP image implements 26-bit modular semantics for
all inputs. Any additional confirmed difference will be recorded beside its
fixture before the feature row advances.

## Captured reference cases

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

The evidence folders preserve raw CRLF/LF input bytes, exact VM diagnostics,
exit/timeout status and SHA-256 values. They must not be edited to improve the
apparent result.

## Still unresolved before the guest-language gate

- Semantics and evaluation order for every overload, including list equality,
  arithmetic arity and error cases, `gcd`, `lcm`, `bind'`, and stateful
  operators. Documented binary arithmetic operators take two operands; unary
  operators such as `!` and `~` take one. No variadic extension is assumed.
- Lexical shadowing, closures after creator return, recursion, macro expansion,
  short-circuiting and lazy memoization, checked against minimal original cases.
- Reader and printer edge cases, numeric token overflow, malformed forms,
  language error continuation, EOF, and all `.F/.A/.R/.M/.S/.E/.I/off`
  behaviors.
- Whether the original reaches different results if given more than the
  explicit step and wall budgets. Current timeouts do not answer that.

No guest code may consume this document as a substitute for the missing cases.
Each row remains `DECLARED` until the feature matrix has exact positive and
negative fixtures; implementation and demonstration need separate guest tests
and replayed evidence.
