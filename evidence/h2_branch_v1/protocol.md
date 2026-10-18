# H2 — one native input-dependent branch (2026-10-18)

## Scope and result

`DEMONSTRATED_SCOPED`: our `.slop` frontend can emit a canonical fixed-3^19
guest that reads one selector and branches **inside bolge19**. Zero halts;
nonzero reads another byte, writes it, and halts. `examples/branch.slop`
describes that exact three-block CFG. One 259-cell image implements it for
all selector bytes and EOF; no host dispatches on guest input.

This is the first H2 slice, not completion of H2's general control-flow and
initialization work. `assemble()` still handles H1; the CLI dispatches this
recognized module to `lower_branch`. Other modules are refused with exit 3.
The search backend and its semantic-proof enum are unchanged.

## Hypotheses and controls

| Claim | Status | Falsifier |
|---|---|---|
| This CFG can run from our generated source with native input-dependent control flow | DEMONSTRATED_SCOPED | Any selector/payload case mismatches or does not HALT. |
| Whitespace formatting preserves the canonical guest | DEMONSTRATED_SCOPED | Formatted image differs in output/status for a recorded case. |
| The test detects an always-stop implementation | DEMONSTRATED_SCOPED | Changing entry cell 99 to HALT still passes nonzero input. |
| The test detects zero falling through to echo | DEMONSTRATED_SCOPED | Changing zero cell 1 to NOP still passes zero input. |
| General BRZ/JMP, arbitrary arms, reusable bootstrap, guest memory/arithmetic/loops/calls | NOT_DEMONSTRATED | Outside this implementation. |
| Lisp guest / Unshackled parity | NOT_DEMONSTRATED | No corresponding implementation or conformance battery. |

## Construction, with the machine's operand order

Orientation is `crazy(ctrl, cell) = TABLE[cell][ctrl]`. Before each campaign,
T24's entire Classic 59,049-cell fill is rebuilt against the independent
`oracle_classic.py` reference: zero mismatches in this orientation, 18,709
when swapped. That is an orientation control, **not** Classic evidence for
the 3^19 guest. Reference source and specimen hashes are recorded read-only.

The new lowering is original code over this repository's opcode profile;
it imports neither HeLL nor LMFAO. It emits named native instructions plus
pointer/data constraints, then independently walks canonical acceptance.
There is no literal Malbolge image embedded in the generator.

1. Native JMP at 0 enters 99, encrypting cell 98 on its way.
2. Moves at 100..103 use `2 → 67 → 127 → 85 → 78` to position D. ROT at 104
   is a bootstrap operation whose own encrypted byte becomes HALT. Input at
   105 replaces its temporary accumulator and advances D to 80.
3. OPRs at 106/107 compute `f(x)=crazy(crazy(x,82),112)` and store it at 81.
   The first seed has trits `10001`; the second `11011`. On byte input the
   composition fixes zero and maps each nonzero trit to a nonzero trit.
   Consequently `f(x)=0` iff `x=0` over the full byte domain, rather than just
   the examples. MOVE at 108 uses cell 82 to restore D=81.
4. JMP at 109 reads that computed word. Zero lands at cell 1 (HALT).
   Nonzero byte landings occupy several disjoint intervals. NOP funnels lead
   to copies of the same nonzero block at 42, 96, 123 and 256. After the
   96/97 input/output pair, the encrypted bootstrap now supplies the halt at
   104. The landing at 109 itself takes a second native jump through 81.
5. EOF's computed landing is 581130816: the VM's lazy-memory pattern there
   supplies JMP through the reset pointer to 81, then reaches 96/97/104.
   The exact source tail and this VM's lazy initialization are dependencies.
   This path is separately traced and run, and never called independent
   Unshackled agreement. EOF on the second read emits the low byte `da`.

The first input is consumed inside the guest. Between each selected payload
read and its output no operation changes A, so payload forwarding does not
depend on the payload value. Exhaustive payload tests cover all four copies.
Named labels determine the recognized CFG, not their spelling or declaration
order. Cases only reject contradictions; they do not select image bytes.

The verifier uses explicit acceptance checks, not Python `assert` statements.
A regression runs it under `python3 -O` with an injected VM boundary that
always returns HALT with empty output: that run must record `FAIL` and return
nonzero. The initial implementation incorrectly accepted it under `-O`;
`validation/optimized-red.txt` preserves the failing regression, and the final
suite includes the repair. The external Classic oracle is test-only; bytecode
generation is disabled during its import so the control does not write into
that sibling repository.

## Evidence

`tools/verify_h2_branch.py` creates a fresh `runs/<UTC>-<random>/` directory
and never overwrites a previous run. Each complete campaign records:

- 256 real selector runs, with marker `41`, plus 256 missing-payload runs;
- one empty-input EOF run;
- 1,280 payload runs (all 256 values at four physical arm paths and the
  exceptional landing on JMP at 109);
- five formatted-image runs, and two negative controls;
- 257 model selector traces, including the EOF far-memory path;
- exact stdout/stderr bytes in `vm-raw.jsonl` (hex, unedited), status, exit
  code, source/engine/image hashes, environment, exact invocation and bounds;
- `report.json`, `orientation.json`, and per-run `SHA256SUMS.txt`.

Total: 1,800 native VM executions. This is finite-domain coverage for the
recognized CFG, not a general proof about arbitrary programs. The initial
exploratory campaign is `runs/20261018T174433Z-f10e3ad1/`; it had 1,544 runs
and used selector 108 twice for the same physical copy instead of testing
all payloads at copy 123. Its complete selector grid did exercise that copy
with marker 41. The final campaign adds selector 109 to close the payload
coverage gap; the exploratory evidence is preserved unchanged. The red
regression output and final suite/build output are
preserved separately in this pack's `validation/` directory.

The final source-pinned campaign is
[`runs/20261018T175032Z-f10a45e6/report.json`](runs/20261018T175032Z-f10a45e6/report.json),
executed under optimized Python after repairing the acceptance checks.
The final full suite ran 136 tests successfully. It retains the existing
guest-runner ResourceWarnings about unclosed pipes; those warnings were also
present before H2 and were not changed as part of this gate.

Reproduce from the repository root:

```sh
bash tools/build.sh
python3 tools/assemble.py examples/branch.slop --round-trip
python3 -m unittest discover -s tests -q
python3 tools/verify_h2_branch.py
```

To verify a run, change to its directory and execute
`sha256sum -c SHA256SUMS.txt`. Run hashes cover its artifacts; the pack-level
manifest additionally covers this protocol and validation logs. The VM source
remains byte-identical to H1 (`47758a3f…`). Previous sealed evidence is untouched.

## Documentation drift

README and PARITY_MATRIX now link this narrower result. Their old M6/L1/H1
pins remain historical; `documentation_drift.json` records old/new values
without changing any previous manifest. Do not run M6 `finalize.py` on HEAD.
