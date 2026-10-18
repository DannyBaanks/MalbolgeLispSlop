# M5 preregistration — exact suffix eligibility of the sealed G

Date: 2026-10-18. Source revision: df2756c. Research only; no VM changes.

## Question and null hypothesis

Can the fixed M4G1 model from M4 supply a completely defined, nonempty tail
`[S', S)` after retaining a raw prefix `[0, S')`?

H0: no strict prefix `S' < S` has a fully defined remaining suffix under this
specific model. The model is fixed before the measurement. This is a test of
reconstruction eligibility, **not** of behavioral equivalence or semantic liveness.
It says nothing about a different generator, additional literal residues, other
specimens, or future refinements.

## Metric and exhaustive decision

Parse the M4G1 intervals independently of generate.py: literal header, each
`[st, st + gl + lag)` and any literal fix. Merge by interval union, keeping
occupancy separate from byte values. Let `u` be the last uncovered byte, if any.
Then a tail is fully defined iff `S' > u`; the smallest eligible prefix is
`u + 1` (or zero if no byte is uncovered). This establishes the eligibility
threshold exhaustively; it is not binary search and assumes no behavioral
monotonicity.

The actual suffix witness, coverage total, gap total, and first/last gaps are
recorded in both repeated outputs. Independently scan raw bytes to verify the
canonical SHA-256, alphabet, absence of op-zero, and exact inverse under the
observed alphabet plus the header's newline exception. Also re-run the sealed
G check and inspect its JSON fields, not its exit status alone.

## Baseline and controls

- Baseline: sealed full specimen SHA-256 092df5cd… and M4 check's coverage.
- Null-cut control: `[S,S)` is empty and eligible; savings zero.
- Literal control: the complete header `[0,19392)` is defined.
- Synthetic positive: coverage `[0,8)` has smallest eligible prefix zero.
- Synthetic negative: coverage `[0,7)` leaves byte 7 unknown, so only prefix 8
  is eligible. Synthetic interior gap `[0,3) U [4,8)` has threshold 4.
- Repeat the entire suffix measurement twice; deterministic JSON must match.

## Conditional behavioral battery B (not executed if the gate fails)

Candidates: init_module with EOF; full lisp.mb with EOF; full lisp.mb with
CRLF bytes `(+ 1 2)\r\n`; repo tiny in/out/halt guest with byte A and EOF.
For each, full and reduced images must have identical stdout bytes, process
exit, termination reason, HALT steps and `(c,d,a)` on two repetitions.
Raw stderr must be retained; wall-time, file path, image size and loader/overlay
diagnostics are reported separately, not silently treated as semantic output.
Matching B would not prove universal equivalence. Neither S' monotonicity nor a
behavioral minimum is assumed.

If no nonempty suffix is eligible, do not fill holes with zero and call that
materialization; do not substitute bolge19's EOF crazy-chain/page rule. Mark
behavioral runs NOT_RUN_PRECONDITION and all behavioral claims NOT_DEMONSTRATED.
M5 is then PARTIAL under the plan's introductory allowance, not a pass of its
strict equivalence-or-semantic-counterexample acceptance criterion.

## Next experiment

If the gate fails, supply an explicit content-bearing residue for the unknown
tail (or derive and independently validate a stronger rule), then repeat this
eligibility check before executing B. A raw-prefix+existing-loader experiment
would be a separately named hypothesis, not execution of this protocol.
