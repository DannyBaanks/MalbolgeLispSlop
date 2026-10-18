# Architecture boundary

## First vertical slice

```text
fixture bytes + input bytes
          │
          ▼
fixed-3^19 `bolge19` VM ──► captured stdout/stderr, exit code, step signal
          │
          ▼
Python conformance harness ──► bounded child process + SHA-256 report
```

The current guest is exactly three cells, `ubO`, which decode at positions
0–2 to input, output, and halt. The canonical loader ignores whitespace and
checks opcode validity; the raw loader counts every byte as a cell. The
verifier tests both conventions explicitly.

## Ownership boundaries

- `src/bolge19.zig` is a verbatim copy of the MIT-licensed forensic VM source
  identified in `THIRD_PARTY_NOTICES.md`. It is the execution substrate for
  this slice, not new VM research by this repo.
- `fixtures/` contains tiny authored probes only. The large upstream Lisp
  image, modules, and manual are intentionally absent.
- `tools/verify_slice.py` is an external process supervisor. It bounds child
  memory, CPU time, output file size, and wall time, and records raw byte
  digests. Its checks do not prove language completeness.
- Future Lisp parsing/evaluation must run as guest computation. A host-side
  evaluator that merely prints Lisp answers cannot satisfy the project goal.

## Current limits

This slice inherits the fixed-3^19 runtime's memory, input, EOF, and loader
semantics. It does not establish compatibility with the dynamically widening
Unshackled implementation, nor with Classic 3^10 Malbolge. It has no second
independent 3^19 backend yet.
