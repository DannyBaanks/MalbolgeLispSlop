# MalbolgeLISP Specimen-100 — research closeout

**Date:** 2026-10-18. **Profile:** fixed-3^19 bolge19 / fast20-style execution.
**Result:** canonical artifact and REPL reproduction established; generative
reduction **PARTIAL**; prefix-truncation behavioral equivalence
**NOT_DEMONSTRATED**. This is not 100% Lisp conformance, universal equivalence,
or completion of every originally proposed stress case.

## Scope and evidence chain

The input is the pinned iczelia/malbolge-lisp specimen, not a new Lisp
implementation. The upstream pin is
`0dc37eb1c15548d45be1a019069fcb290b1d78a5`.
`lisp.mb` is 371,331,415 bytes with SHA-256
`092df5cdc240de33a355d3cf82bdf09e0859c5827ee57a65bf93dfc37e8f3256`.

**Correction to the original plan's M0 step 2:** the actual concatenation is
`init_module.mb ++ core.mb`, not `core.mb ++ init_module.mb`.
The 19,392-byte header includes one newline at offset 19,391. M0's byte
comparison and M1's upstream recipe agree on this order
(`evidence/specimen100/m0/inventory.json:53-65`,
`evidence/specimen100/m1/upstream.json:61-72`). The main-repository plan is
preserved rather than silently edited.

M0–M4 are the sealed records from commits 6a14d5f, 4cdfbc5, de0a336,
e13ee8f, d01adfd, 771e75c, 9d0d960 and df2756c. Their manifests were
re-verified at closeout; this does not rerun historical workloads. New M5/M6
records occupy new directories and do not overwrite them.

## Claims table

Per-row source SHA-256 values are in
[`claims.json`](../evidence/specimen100/m6/claims.json). Commands, cwd, observed
exit codes and raw-stream hashes for the new work are in the M5/M6
`execution.json` files. Prior commands and outputs remain in their milestone
records and manifests.

| Milestone / claim | Status | Evidence and limit |
|---|---|---|
| M0 identity, hash inventory and concat order | VERIFIED | `m0/inventory.json`; byte identity, not source regeneration |
| M1 pinned artifacts / documented concat recipe | REPRODUCED_BYTE_EXACT | `m1/upstream.json`; six recorded artifacts match. Zip/manual are committed upstream artifacts, not compiler-build reproduction |
| M2 canonical CRLF REPL session | REPRODUCED | `m2/reproduction.json`: two stdout transcripts and HALT state agree with history; one arithmetic input, not general Lisp conformance |
| M3 measured differential / portability rows | VERIFIED_WITH_LIMITS | `m3/differential_matrix.json`; full proposed guest/quijote/stress matrix is not demonstrated by these rows |
| M4 complete raw-file regeneration | PARTIAL | `m4/g_check.log`; length matches but full hash differs |
| M4 covered raw bytes | VERIFIED | 133,860,553 bytes, fraction 0.360488, covered mismatches zero; independently rechecked in M5 |
| M5 sealed G supplies a nonempty complete suffix | NEGATIVE | `m5/gate_run1.stdout.json` equals run2 byte-for-byte; no strict prefix qualifies |
| M5 full/reduced behavior, semantic liveness or behavioral minimum | NOT_DEMONSTRATED | B not executed: reconstruction prerequisite fails. This is not a semantic counterexample |
| M6 regression suite / existing manifests | VERIFIED | `m6/execution.json`: suite exit 0, 93 tests OK; manifests M0–M4 exit 0. ResourceWarnings retained |

M5 is **PARTIAL under the plan's introductory allowance**. Its strict
equivalence-or-minimal-semantic-counterexample criterion is **not met**. M6
closes reporting and verification, not that scientific gap.

## Reproduction and differential findings

The reproduced REPL input is hex `282b20312032290d0a` (`(+ 1 2)\r\n`).
Both recorded CRLF runs halt at steps **2,408,246,381**, with
`(c,d,a)=(581143360,581861866,10)`. Stdout SHA-256 is
`b3214e2914a175fdac1c3898e7ec8d3b4eef88bcde6da152a551b57d058d02ea`.
LF-only input gives a different step count; it must not be called a matching
reproduction (`m2/reproduction.json:7-42`). Raw stderr contains timings and
is not asserted bit-identical.

The measured Linux fast20 upstream session matches the canonical stdout;
this is related-implementation corroboration, not independent semantic proof.
The historical fast20_fixed variant segfaults on measured Linux cases; its
exact source-level cause remains undemonstrated. Certain old showdown rows
were usage/absent-file executions, not evidence of specimen execution
(`m3/differential_matrix.json:125-196`). Windows-only observations stay
historical. Classic 3^10 controls do not establish fixed-3^19 parity.

## M4 model and limits

G operates on `op[i]=(raw[i]+i)%94`. This is not a byte bijection in general.
For this specimen the alphabet is `{0x0a} U [0x21,0x7e]`; resolve to the
printable representative, then restore the literal newline at 19,391.
The new full-file scan found zero op-zero bytes and zero inverse mismatches
after that fix. Occupancy in the new checker is interval-based, independent
of byte values (`m5/suffix_gate.py`).

The M4G1 model uses a literal header plus lag-12/7/9/2/11 runs, units and
coordinates discovered from the **whole specimen**, not inferred solely from
a retained prefix. It is 17,953,343 bytes, SHA-256
`6e7fa25df5bd645773398cf1c33a67ec8d29d1bcb137e9a4366d6c3dcd4f1b6d`.
The recorded xz baseline for the op image is 8,479,600 bytes; G is larger and
only partially reconstructs the file. These are different coverage guarantees,
not evidence that G beats xz.

The partial raw artifact, with undefined bytes filled by 0x00, has SHA-256
`cc8dcfbc23f6ec85203a83f874d02d71d3f2a906a6e4ccb558819e7c8f486904`;
it is not the specimen. The exact G check reports 237,470,862 undefined bytes
in 1,289,356 gaps, first beginning at 19,511. The older exploratory union has
slightly different boundary counts. Its `devmap_v1.bin` stores lengths only;
it is neither an independent positional map nor the final G's exact gap list.

`generate.py check` returning zero means the command completed. Its JSON
`byte_exact` and `covered_mismatches` fields must be inspected; exit zero is
not a byte-exact gate. Generic alphabet handling, the misleading bijection
docstring and exit-policy hardening are a maintainer/coder handoff, not fixed
as part of this research closeout (Bridge maintenance report #8141).

## M5 experiment: suffix eligibility before behavior

Preregistered protocol: [`m5/protocol.md`](../evidence/specimen100/m5/protocol.md).
H0: the fixed, sealed G covers no nonempty suffix `[S',S)` for `S'<S`.
Baseline: the sealed canonical specimen and M4 check. Controls: complete
literal header, empty omitted tail, synthetic complete/incomplete/interior-gap
interval unions. Metric: the last uncovered byte and the union's coverage.

Independent parsing and interval union, repeated twice, found:

```text
covered_bytes = 133860553
last_gap = [371331413, 371331415)
smallest_prefix_with_fully_defined_suffix = 371331415
maximum_supported_tail_omission_bytes = 0
eligible_nonempty_suffix_exists = false
```

All strict prefixes omit the last byte, which this G leaves undefined. That
single witness decides eligibility for every strict prefix; no binary search
or behavioral monotonicity assumption is needed. H0 holds for this fixed
model. The two raw gate outputs share SHA-256
`e718cf419fbaf589029f8d42e904e311668ea37fda8ca142f295a0fc426c19bb`.

The conditional B in the protocol is **NOT_RUN_PRECONDITION**, not passed and
not behaviorally falsified. Adding literals, refining the generator, allowing
zero holes or using the existing EOF loader would change the experiment.
No VM flag or production implementation was added. No claim of semantic tail
liveness, universal incompressibility, or minimum behavioral prefix follows.

## Commands and verification

Executed from the worktree (outputs are exclusive-create / retained):

```sh
python3 evidence/specimen100/m5/run_experiment.py
python3 evidence/specimen100/m6/run_verification.py
```

M5 captures the independent gate twice and the sealed `generate.py check`.
M6 captures `python3 -m unittest discover` and `sha256sum -c SHA256SUMS.txt`
in each M0–M4 evidence directory. Each command exited zero. The suite ran
**93 tests in 2.936s, OK**, with unclosed-file ResourceWarnings preserved in
`m6/unittest.stderr.txt:1-11` and reported for maintenance (#8144).

The research pack is built and verified with `isyco researcher pack`; run that
CLI from the main ISyCo root with absolute worktree paths (the worktree lacks
an `.iesyroot` marker). Its artifacts remain in this worktree. Local raw
outputs, source scripts, claim hashes, and documentation hashes are sealed by
the new M5/M6 manifests. Full blobs, model and compressed image remain only
in scratch; regeneration checks require those scratch inputs.

## Next experiment and handoff

Before running B, derive and validate a stronger rule or explicitly account
for content-bearing residues, then repeat suffix eligibility. Prefix-only
derivation of model metadata is a separate requirement. Define whether the
whole post-S memory image must match or only B is being tested. A loader-only
truncation experiment must be named separately; the loader's EOF seeds/page
phase can change the memory beyond the original file too.

The remaining scientific claims are NOT_DEMONSTRATED, not unfinished runs
hidden behind a green suite. Implementing a new VM materializer or hardening
G is a coder task after a new experiment is justified. No publication, push,
upstream modification, or redistribution of the specimen/manual is authorized.
