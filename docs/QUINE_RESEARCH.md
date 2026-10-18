# Fixed-3^19 Native Quine Research

This document reports the latest verified fixed-`3^19` quine campaign and its
raw evidence. Earlier runs are never deleted or overwritten: every campaign
gets a unique run directory under `evidence/quine/`, an append-only
`index.jsonl`, and a per-run `SHA256SUMS.txt`.

**Status: no quine demonstrated.** The bounded smoke campaign stopped on its
declared wall-clock budget; that is `BUDGET_EXHAUSTED`, not a proof that no
fixed-`3^19` quine exists. The system specification's quine gate remains open.

## Latest campaign

- Run: `evidence/quine/20261018T084122Z-seed-0`
- Budget: `quine/budget-smoke.json` — at most 10,000 candidate nodes, 10.0 s
  wall, 1,000,000 guest steps per candidate, 2.0 s / 536,870,912 bytes per
  candidate process, 100,000 bytes maximum per candidate image, seed 0.
- Algorithm: `fixed19-profile-dispatch-product-v1` (candidates are
  profile-derived dispatch-name products, `seed_rule =
  rotate-by-dispatch-count; reverse-on-odd-quotient-v1`).
- Result: `BUDGET_EXHAUSTED` — "global wall_seconds budget exhausted before
  search completion".
- Candidates attempted: 2,082 of the 10,000 allowed nodes; the wall budget,
  not the node budget, stopped the campaign.
- Outcomes: 1,997 candidates halted with `stdout != source` bytes
  (`NOT_DEMONSTRATED`), 84 ended `MAX_STEPS` under the declared step limit,
  and 1 — the final candidate, started with the global wall budget already
  spent and its per-candidate timeout truncated to ~0 — is recorded
  `WALL_TIMEOUT` even though its stderr telemetry shows a step-1 halt (see
  "Wall-boundary classification" below).
- Canonical re-verification: the 1,997 candidates recorded as `HALT` were
  re-run through `quine.verify.verify_candidate` with the same contract and
  budget; all 1,997 came back `NOT_DEMONSTRATED`. The pass loaded the
  candidate files from disk again, so its digests are independent of the
  search-time records. The wall-boundary candidate is excluded from this
  pass because its search record is inconclusive; it cannot be a quine here
  (empty stdout against a 4-byte source), and a future campaign re-attempts
  boundary candidates under a fresh budget.

No candidate was hosted-copied, stubbed, or accepted without a guest `HALT`
and byte-exact stdout. Nothing in this campaign is transferred from Classic
`3^10` quine claims.

## Environment

- `bolge19` binary SHA-256:
  `d42284300da101032759fbe7d123aaac619467e2f25d0c9b43045eb46c9d9380`
  (built by `./tools/build.sh`, Zig 0.16.0).
- Python 3.12.3; repo HEAD `296e06979575e8efebe9082e0ede79a8b43a3f72` when the
  campaign ran.

## Evidence digests

| Artifact | SHA-256 |
|---|---|
| `report.json` | `e69cea38a6a31d3bc24652b2ea812246f52f512921a50fddf0edb371c2bc8006` |
| `search-manifest.json` | `f31d5350db469aab0dda8a4c30cec98861930ca20f0d1889ccf537233abfef42` |
| `candidate-records.jsonl` | `851818e37e420ac986ddc026d549c1f46fed7d797a0e0e477a5509ae416b2b49` |
| `verification-records.jsonl` | `4cea70edbf28f7196aed54af45cca750ac23b317787536d4023940fe7c096417` |
| `verification-pass.json` | `5da94862a1aaf9afdab68aa8fb12c6109c669f5405c9d531674dbb7ef3d5db7a` |
| `SHA256SUMS.txt` (6,251 files covered; all verified) | `cc1f1437cc36b10cf5a94adff2ac4e86c6a8211cd5604dfb0fe972718d3fe046` |
| Last retained candidate `candidates/002082.mb` | `42cc4e2a432ce24136c6ae8ad8982d61b92ff983176b503832522bc9448f3627` |

The run directory keeps, for every attempted candidate, the candidate image,
its raw guest stdout and stderr, and a record with digests, guest status,
step count, and the failure reason.

## Reproduce

```sh
./tools/build.sh
make quine-smoke
# or, equivalently:
python3 tools/search_fixed19_quine.py --contract quine/contract.json \
  --budget quine/budget-smoke.json --output-root evidence/quine
```

Each invocation writes a new run directory plus an `index.jsonl` entry; an
existing run directory is never reused or overwritten. Candidate order is
deterministic for a declared seed; how far the campaign gets inside the wall
budget depends on machine speed, and the stopping node moves with it.
Control-flow records are stable, but record digests embed stderr telemetry
(`elapsed=Ns`), so individual digests can drift across second boundaries
under load; the candidate space, order, and verdicts do not.

Regenerate `verification-records.jsonl` and `verification-pass.json` for the
latest run with the exact generator used for this campaign (this re-executes
`bolge19` once per recorded `HALT` candidate, about a minute):

```sh
python3 - <<'EOF'
import hashlib, json
from pathlib import Path
from quine.evidence import load_contract
from quine.search import load_budget
from quine.verify import verify_candidate

run = Path("evidence/quine/20261018T084122Z-seed-0")
contract = load_contract(Path("quine/contract.json"))
budget = load_budget(Path("quine/budget-smoke.json"))
records = [json.loads(line) for line in (run / "candidate-records.jsonl").read_text().splitlines()]
halted = [r for r in records if r["guest_status"] == "HALT"]
lines = []
by_status = {}
for r in halted:
    rep = verify_candidate(run / r["candidate_path"], contract, budget)
    by_status[rep.status] = by_status.get(rep.status, 0) + 1
    lines.append(json.dumps({
        "node": r["node"],
        "candidate_path": r["candidate_path"],
        "status": rep.status,
        "source_sha256": rep.source_sha256,
        "stdout_sha256": rep.stdout_sha256,
        "steps": rep.steps,
    }, sort_keys=True))
records_path = run / "verification-records.jsonl"
records_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
summary = {
    "schema_version": 1,
    "verifier": "quine.verify.verify_candidate",
    "source_records": "candidate-records.jsonl (guest_status HALT)",
    "candidates_verified": len(halted),
    "by_status": by_status,
    "verification_records_path": "verification-records.jsonl",
    "verification_records_sha256": hashlib.sha256(records_path.read_bytes()).hexdigest(),
}
(run / "verification-pass.json").write_text(
    json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
EOF
```

This generator was re-executed against the committed run directory after the
evidence commit (output staged outside the repo); it reproduced both files
byte-for-byte (`verification-records.jsonl` `4cea70ed…`, `verification-pass.json`
`5da94862…`).

## Interpretation

- What this shows: within the declared bounds, no fixed-`3^19` candidate
  demonstrated byte-exact self-reproduction with `HALT`; the harness,
  verifier, and evidence chain work end to end.
- What this does not show: it is not evidence that no fixed-`3^19` quine
  exists. A bounded search failure is `NOT_DEMONSTRATED` /
  `BUDGET_EXHAUSTED`, never "no quine exists". A future campaign with a new
  immutable budget file can continue the search.
- No upstream repository was modified, and nothing was published or pushed
  from this campaign.

## Wall-boundary classification

The final attempted candidate (node 2082, `candidates/002082.mb`) is recorded
`WALL_TIMEOUT` with `returncode: null`, but its raw stderr shows
`bolge19: HALT steps=1 c=1 d=1 a=1162261466 elapsed=0s`. Mechanism:
`quine/search.py` truncates the per-candidate timeout to the remaining global
wall (`min(2.0, remaining)`), and `tools/guest_runner.py` sets `wall_timeout`
when the deadline has already passed and gives it precedence over the stderr
classification, even when the child had already exited. So a candidate whose
truncated budget is ~0 can be recorded inconclusive (`WALL_TIMEOUT`, which the
verifier maps to `BUDGET_EXHAUSTED`) instead of `HALT`. It cannot be a quine
in this run (empty stdout against a 4-byte source), and it was excluded from
the verification pass; a future campaign should re-attempt wall-boundary
candidates under a fresh budget before drawing conclusions. The runner's
precedence behavior is shared with the synthesis-backend track and was not
modified here; the record is preserved exactly as written, and this section
is the correction.

## Run history

- `20261018T084122Z-seed-0` — smoke campaign, seed 0, budget
  `quine/budget-smoke.json`; `BUDGET_EXHAUSTED` after 2,082 candidates; no
  candidate demonstrated. (This file; evidence above.)

New campaigns append entries here, newest last, without editing earlier ones.
