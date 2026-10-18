# Risks and open questions

1. **Dialect naming:** “Unshackled” is not synonymous with fixed-3^19. Keep
   claims pinned to the named profile until an exact semantic comparison is
   available.
2. **Inherited runtime:** `bolge19` is a forensic Zig implementation of
   `fast20`-style behavior. A guest passing it is not independent backend
   agreement.
3. **Upstream licensing:** the MalbolgeLISP README and its local license
   metadata disagree about the core program's license. Do not redistribute
   `lisp.zip`, `core.mb`, `init_module.mb`, the manual, or derived large images
   until provenance and permission are resolved.
4. **EOF and encoding:** the fixed VM consumes one byte per input operation
   and maps EOF to `END - 1`. These semantics differ from the original
   dynamically widening implementation.
5. **Quine transfer:** a Classic Malbolge quine is not evidence of a
   fixed-3^19 or original-Unshackled quine.
6. **Scale:** the reported full MalbolgeLISP specimen is hundreds of MB and
   resource intensive. This project starts with tiny fixtures and imposes
   process limits.
7. **Timeout evidence:** the M1 supervisor self-check validates timeout
   capture and termination, but does not show that a crafted guest loops
   forever. That remains open.

Before a public release of a Lisp artifact, revisit licensing, attribution,
resource bounds, and independent execution evidence.

## Specimen-100 findings (2026-10-18)

See [SPECIMEN100.md](SPECIMEN100.md) for the bounded closeout. The canonical
REPL is reproduced, not a general conformance suite. The partial generative
image is not runnable evidence of equivalence: unknown tail bytes remain, and
M5's behavioral battery was not run after its reconstruction prerequisite
failed. A length-only deviation map does not restore omitted contents.
The model uses whole-specimen metadata; prefix-only generation is unproved.
`generate.py check` exit zero is not a byte-exact verdict; inspect its JSON.
The regression suite passes but emits retained unclosed-file ResourceWarnings;
maintenance reports #8141 and #8144 track these limitations. Licensing and
non-redistribution restrictions above remain unchanged.
