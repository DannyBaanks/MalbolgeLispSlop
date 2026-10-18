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
