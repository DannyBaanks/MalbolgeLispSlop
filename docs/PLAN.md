# Milestones

## M0 — Read-only inventory

**Complete.** Recorded inspected sources, revisions, hashes, the fixed-3^19
scope decision, claims, and risks. See `BASELINE.md` and
`evidence/m0/inventory.txt`.

## M1 — Small executable slice

**Complete for the stated narrow slice.** Vendor the licensed fixed-3^19 VM, add a minimal input/output
guest, and record byte-level runs for variable input, deterministic output,
halt, loader rejection/difference, mutation, controlled allocation failure,
step cap, and wall-timeout supervision. Keep a wall-timeout self-check distinct
from a demonstrated infinite guest.

Gate result: all ordinary guest outcomes are captured with input/output hashes,
return code, loader mode, and halt/limit status. The report states the resource
limits and missing independent backend. The final 12-check run is in
`evidence/m1/slice-20261018-final.json` and `evidence/m1/run-final.log`; the
earlier 11-check report is retained as historical evidence. A related `fast20`
C executable also matched one sample byte, without establishing independent
agreement. This is not Lisp conformance, original-Unshackled parity, or a quine
result.

## M2 — Quine research

Research a native quine for a precisely named target dialect. Do not infer
transfer from Classic 3^10. Preserve every candidate and its generation
method; require independent byte-for-byte reproduction before calling it a
quine.

## M3 — Lisp by demonstrated subsets

Add small language subsets only when each operation is performed by the guest
program running in the target VM. Include source programs, expected byte
outputs, runtime/step bounds, negative cases, and a mutation control. A host
interpreter or canned output is not conformance.

## Release boundaries

No upstream edits, publishing, push, or pull request are part of these
milestones. Any future publication requires a separate user request and
resolved artifact licensing.

## Full-system implementation plan

The M0/M1 claims above remain the recorded baseline. The approved full-system
specification and its split, dependency-ordered implementation plans are
indexed in [`docs/superpowers/plans/README.md`](superpowers/plans/README.md).
The synthesis-backend capability gate must pass before implementation of the
guest Lisp runtime begins. Native quine research remains a separate track.
