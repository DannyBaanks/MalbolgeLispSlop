# Complete native MalbolgeLISP implementation plan

**Authority:** user-approved plan in the Codex conversation, 2026-10-18.
**Base:** 9e76248be8df36b3d1c72f73b75ece5a7a29b063.
**Goal:** original fixed-3^19 guest implementing the MalbolgeLISP v1.2 surface.
**Architecture:** language contract -> interpreter IR -> certified synthesis and
linking -> canonical Malbolge image -> bolge19. Python reference evaluation is
test-only. The executable and generated image must suffice to evaluate new
programs. Quine research is separate and does not block Lisp completion.
**Stack:** Python 3.12, Zig 0.16.0, z3-solver==4.16.0.0 for development only.
**Execution:** inline implementation, independent review at critical boundaries.

## Constraints

- Preserve Program, Module, SearchBudget and synthesis status compatibility.
- Extend module compilation with optional configuration and certified blocks.
- Preserve existing evidence byte-for-byte. New evidence paths are unique.
- No hand-patched generated code, host-side Lisp on the runtime path, upstream
  edits, publication, file deletion or claims of dynamic Unshackled parity.
- Solver unknown/timeout/exhaustion is neither a proof nor an impossibility.
- A task passes only after its named tests run; -O must not disable acceptance.
- Keep a persistent checklist, commands, outcomes and rulings in the ledger.

## Tasks and gates

### Task 1: Consolidate contract and persistent work list
Update SYSTEM_SPEC and plan index for the approved dependency and quine scope.
Pin the development package. Create the ledger and record interface dependencies.
Gate: clean baseline, pinned package imports, reviewed scoped commit.

### Task 2: Freeze compatibility inventory
Create spec/lisp-feature-matrix.json and its checker. Inventory the union of
manual function listing, chapters, overloads, types, syntax, dot commands and
error table. In particular include gcd, lcm, bind', quote aliases and overloads.
Do not redistribute the manual. Feature states distinguish SPECIFIED,
IMPLEMENTED and DEMONSTRATED; each case specifies raw bytes and resource bounds.
Gate: unique IDs, complete source inventory, positive/negative cases and test
IDs; a checker must reject omissions, duplicates and unsupported upgrades.

### Task 3: Resolve language semantics
Write spec/lisp-language-v1.md with bounded unsigned 26-bit arithmetic,
fixed-profile behavior of +'/-', evaluation order, equality, lexical scope,
macros, lazy memoization, printing, EOF and errors. Where the manual conflicts
or is incomplete, run minimal cases against the original local specimen under
the same fixed19 VM and preserve raw outputs and hashes. Record differences.
Gate: exact expectations, no hidden host semantics, no unbounded-arithmetic claim.

### Task 4: Exact symbolic model
Create a Z3 transition model including crazy orientation, actual rotation,
post-jump encryption, per-region dispatch, canonical loading, chain/paged
initialization, byte input, EOF, halt and explicit bounds. Differentially compare
it against the concrete model and bolge19 before using it for verification.
Gate: all native instructions, memory boundaries and mutations agree; unknown
is propagated and failed proofs cannot be accepted under optimized Python.

### Task 5: Certified reusable blocks and bootstrap
Use counterexample-guided synthesis to derive initialization, constants,
transfer, load/store and jumps. Contracts state preconditions, effects, frame
conditions, exits and step bounds. Search stable automodification cycles;
repeated use and composition must be demonstrated. Reproduce H2 by synthesis,
retaining its historical implementation as a regression.
Gate: solver counterexample queries plus real VM runs, repeatability and
negative controls. A straight-line match is not a reusable block certificate.

### Task 6: General module compiler
Link certified blocks for useful branches on both arms, relocation, memory,
arithmetic, loops and nested call/return. Unify JSON/.slop; add text call/return
only with supported lowering. Add module manifests binding IR/profile/generator/
Z3/configuration/certificates/layout/image; retain old manifest verification.
Gate: variable-input memory preservation, countdown, nested calls and relocated
composition execute correctly in bolge19. No guest Lisp implementation before
these prerequisites pass.

### Task 7: Guest runtime services
Generate tagged values, interned symbols, lists, persistent lexical environments,
bounded bump heap and evaluation stack. Closures/lazy values must survive creator
return. Gate: allocation/reset, overflow, shadowing, lifetime and raw VM results.

### Task 8: Reader, printer and core evaluator
Generate documented syntax, application, conditions, definitions, recursion and
macros. Gate: the same image evaluates new arithmetic/list/function expressions
and persistent definitions supplied after startup, independently of Python.

### Task 9: Complete language surface
Add arithmetic/list/higher-order/combinator/indexed/lazy operations by feature
groups. Gate: every overload has positive, negative, boundary and applicable
stateful guest cases; no subset is relabeled complete.

### Task 10: REPL and state
Generate .F/.A/.R/.M/.S/.E/.I/off. State is original, versioned and checked:
truncation, bad pointers and incompatible sizes must not corrupt a live session.
Gate: persistent multi-form sessions, memoization, reset, export/import roundtrip,
corruption and resource tests in the guest.

### Task 11: Reproduction and closure
Build from a clean checkout, reproduce image/manifests, execute all feature rows,
negative controls and -O checks. Update GUIA.md and seal evidence.
Gate: no promised row remains open, host-evaluated or unsupported by guest output.
Report independent-engine status honestly. Quine is not a closure prerequisite.

## Verification and resumption

Each implementation task follows RED -> minimal code -> GREEN -> full relevant
suite -> scoped commit -> ledger update. Critical boundaries get independent
review. Campaigns have explicit budgets and checkpoints; do not repeat an
exhausted campaign unchanged. Preserve failures and do not advance dependent
tasks when a research prerequisite remains NOT_DEMONSTRATED.
