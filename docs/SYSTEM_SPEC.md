# MalbolgeLispSlop — System Specification

**Status:** Approved design; implementation plan in progress  
**Approved design direction:** fixed `3^19` target; new automatic synthesis backend inspired by BolgeForge  
**Scope:** product and architecture only. This document does not claim that the proposed runtime or synthesizer exists.

## Approved execution amendment — 2026-10-18

The user approved `superpowers/plans/2026-10-18-complete-native-lisp.md` after
H2 commit `9e76248`. This amendment takes precedence over the older wording
below: Lisp completion requires the complete independently implemented v1.2
surface and persistent guest REPL; **the quine is a separate research track,
not a Lisp completion gate**. Z3 (`z3-solver==4.16.0.0`) is explicitly allowed
in development/construction/verification alongside Python 3.12 and Zig 0.16.0;
neither it nor the host reference evaluator may evaluate runtime Lisp inputs.
The target VM/profile remains fixed-3^19. Old evidence is never re-sealed.
Implementation progress and decisions live in `IMPLEMENTATION_LEDGER.md`.

## 1. Purpose

MalbolgeLispSlop will be an original Lisp system whose evaluator runs inside a generated Malbolge guest program using the fixed `3^19` profile. It will include a host-side toolchain, a guest REPL, a conformance suite, reproducible generated source, and a native guest quine.

The joke targets manual opcode purism: reviewing an enormous self-modifying instruction stream character by character is a poor way to establish correctness. The project will review the language contract, generator, synthesis evidence, runtime behavior, and reproducible artifacts instead.

## 2. Target profile and compatibility boundary

- The selected execution profile is the fixed-width 19-trit (`3^19`) machine implemented by `bolge19`. The initial compose calls this “Unshackled 19-trit”; this repo will call it “fixed-3^19” because current evidence does not establish parity with dynamically widening Unshackled.
- Classic Malbolge `3^10`, fixed `3^19`, dynamically widening Unshackled, and Malbolge Free remain separate profiles. A result in one profile does not establish a result in another.
- The existing `bolge19` M1 guest is only an input/output/halt slice. It is not Lisp conformance, a quine, or proof of parity with every Unshackled implementation.
- MalbolgeLISP v1.2 documentation is a historical feature reference, not code to copy and not an unquestioned oracle. The project will write its own language specification and tests. Compatibility claims will be limited to behaviors demonstrated against those tests.
- No upstream source, large Lisp image, manual, or BolgeForge Classic quine is to be copied into the new runtime.

## 3. Product definition

The system has four user-visible outputs:

1. A deterministic host toolchain that accepts the project’s Lisp runtime description and emits a Malbolge guest image.
2. A generated guest interpreter that performs parsing, evaluation, memory management, printing, and REPL behavior inside the selected fixed-3^19 target.
3. A conformance corpus that runs Lisp inputs through that guest and records exact outputs, termination, resource use, and evidence.
4. A guest-side quine whose execution emits its own source bytes and halts. A host tool copying the source file is not a quine.

“Complete” means every feature row in the approved language specification has an implementation and guest-execution evidence. A host reference evaluator may help calculate expected behavior, but it may not evaluate user programs on the product execution path.

The compatibility inventory should cover the documented MalbolgeLISP v1.2 surface where its behavior can be independently specified: reader syntax; numbers, symbols, lists, closures, macros, lazy values and function objects; evaluation and scoping; built-ins and higher-order list operations; REPL behavior; documented dot commands; state import/export; and errors. The exact rows and behavior become fixed in the language specification before implementation expands beyond the current M1 slice.

## 4. Automatic generation boundary

All low-level Malbolge instruction streams, including reusable instruction blocks and the final guest image, must be emitted by the synthesis toolchain. No hand-edited Malbolge bytes, hand-maintained opcode templates, or manual patching of generated images are allowed.

Humans may author the language semantics, a readable evaluator description or intermediate representation, synthesis constraints, cost functions, and the host-side generator. Those are reviewable source inputs. The synthesizer must derive the target instruction sequences and memory layout from them.

The build must be deterministic from declared inputs. Each generated artifact must record at least the target profile, source/specification digest, generator revision, synthesis configuration and seed, generation result, artifact digest, and validation commands. A generated artifact changed by hand must fail regeneration checks.

## 5. Architecture

```text
Lisp language specification + readable evaluator IR
                         |
                         v
       profile-aware synthesis and layout search
                         |
                         v
       generated Malbolge source + build manifest
                         |
                         v
       fixed-3^19 guest VM (resource bounded)
                         |
            guest reader / evaluator / REPL
                         |
                         v
      bytes, status, steps, trace and evidence bundle
```

BolgeForge is a source of synthesis ideas and experimental techniques. Its current quine generator is specific to a Classic `3^10` quine architecture and is not a direct Lisp compiler or a drop-in 19-trit backend. Any adapted search or macro-discovery method must be re-derived and validated against the selected profile. No change to upstream BolgeForge is in scope.

The high-level evaluator representation and synthesis engine run on the host. Once the generated guest starts, all Lisp parsing and evaluation claimed by the project must happen in that guest. The host may load, execute, bound, and observe the guest; it may not substitute its own Lisp result.

## 6. Verification contract

Every claimed feature must have at least one guest-execution fixture with exact input and expected output. Important semantic operations need variable and negative cases so a constant-output stub cannot pass. Each run records the guest image digest, VM identity, loader, input/output bytes, stderr, return code, halt/limit status, step and memory limits, and trace/evidence references.

The verification suite should include:

- deterministic regeneration of the guest image and manifest;
- variable input, nested expressions, state across REPL expressions, malformed input, type errors, allocation failure, step limit, and wall timeout;
- differential comparison against a separately written host reference model, explicitly labeled as an oracle rather than the product runtime;
- a second genuinely independent 19-trit backend when one is available. Wrappers around the same implementation do not count as independent. Until then, reports must say `single-implementation verification`;
- quine validation using byte-for-byte `stdout == source`, a real guest halt, no extra output, and explicit file newline rules;
- negative controls that alter an input, generated source, loader, or target profile and demonstrate the expected failure or changed result.

Timeout, step exhaustion, rejected load, and HALT are distinct outcomes. Evidence must preserve raw output and hashes; a printed `PASS` label is not evidence by itself.

## 7. Completion gates

The implementation plan should use small gates and should not call the product complete until all of these hold:

1. **Profile gate:** target width, loader rules, I/O, EOF, memory initialization, and halt semantics are written down and covered by fixtures.
2. **Synthesizer gate:** ordinary guest control flow and I/O are generated from readable inputs, with no hand-written target instruction stream, and regeneration is deterministic.
3. **Guest runtime gate:** the reader, value representation, heap, environments, evaluator, printer, and REPL execute in the guest and pass the approved feature matrix.
4. **Language surface gate:** every feature promised by the specification has positive, negative, and where applicable stateful tests; anything else remains clearly marked incomplete.
5. **Quine gate:** a native fixed-19-trit guest emits its own source bytes exactly and halts under the declared convention.
6. **Evidence gate:** a clean checkout can regenerate and replay the evidence bundle with declared tools and resource limits. Independent-engine status is reported honestly.

The quine is a separate synthesis challenge. It may proceed after the synthesizer’s first vertical slice, but it must not be used to imply that Lisp features are implemented, and Lisp progress must not be described as a quine result.

## 8. Review method and satire metric

Review focuses on the specification, readable IR, synthesizer, search constraints, generated-artifact provenance, conformance results, and falsifying cases. Reviewers are not expected to infer program correctness by inspecting every self-modifying output instruction.

The historical MalbolgeLISP manual describes its interpreter as roughly 350 MB. As a deliberately absurd scale illustration, reading 350 million bytes at one byte per second takes about 11 years without breaks, or about 33 years at eight hours per day; that is only sequential inspection, not semantic review. Any such number in project material must be labeled as an estimate based on the manual, not a measured size of this project’s generated image.

An optional report may display a tongue-in-cheek “manual review years” estimate from artifact size and a declared reading rate. It is a satire metric only and must never replace the real evidence gates.

## 9. Non-goals and limits

- No hand-programming or manual cleanup of generated Malbolge source.
- No claim that Classic BolgeForge output runs under the fixed-`3^19` profile.
- No claim of dynamic-width Unshackled or Malbolge Free compatibility from this fixed-width target.
- No host-side Lisp evaluator presented as native guest execution.
- No record, speed, or “most advanced” claim without comparable measurements and independent evidence.
- No upstream edits, publication, push, release, or pull request without a separate user request.

## 10. Risks and first implementation questions

- The generator may become the dominant research problem; the implementation plan must measure a small target-specific synthesis slice before estimating full-image cost.
- BolgeForge’s Classic macro/search strategy may not transfer to 19-trit semantics. Every reused method needs a profile-specific proof or counterexample.
- A full Lisp evaluator and the historical image size may require substantial memory and execution time. Resource limits and generated-image size must be measured, not assumed.
- The 19-trit execution profile is intentionally narrower than dynamic-width Unshackled. The project must retain that wording in every compatibility claim.
- The historical manual has licensing and behavioral uncertainties. The implementation will use independently written code and a locally authored specification; unclear claims remain unresolved until tested.
- The choice of host implementation language, search algorithm, artifact storage strategy, and independent verification backend remains open for the implementation plan.

