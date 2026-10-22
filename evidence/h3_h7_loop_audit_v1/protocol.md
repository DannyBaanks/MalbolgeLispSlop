# H3 / H7 loop audit (2026-10-22)

Question: do the sealed H3 echo-loop and H7 countdown images loop, or do they
only cover the iteration counts their campaigns recorded?

## Method

`python3 -B tools/audit_h3_h7_loops.py` runs the sealed images unchanged on
upstream `fast20.c` (revision `0dc37eb`, see `../h9_fast20_crosscheck_v1/`) and
on `bolge19`:

- H3 (`h3_loop_v1/runs/20261018T231355Z-906a605f/loop.mb`): selectors 1, 2, 3
  and 65, with 1, 2, 3, 4, 5, 10 and 30 iterations, then a zero selector. The
  original campaign used selector 2 and at most two iterations.
- H7 (`h7_countdown_v1/runs/20261019T012702Z-9a674329/countdown.mb`): every
  `n` from 0 to 11; expected output `n, n-1, ..., 0`.

## Result — `runs/20261022T185435Z-fa30db1e`

| Image | Pass | Detail |
|---|---:|---|
| H3 | 4/28 | One iteration with selectors 1, 2, 3; two iterations only with selector 2. With 30 iterations it still echoes at most two bytes. |
| H7 | 3/12 | Correct only for n in {0, 1, 3}. n = 2 prints nothing; n = 5 prints `5 3 26 24`. |

## Conclusion

Neither image implements a loop. H3 contains a fixed number of unrolled copies
of the echo body; H7 contains hand-placed stages for n = 0, 1 and 3. Their
original runs are correct for the cases they recorded, and remain preserved.
The claims "native loop" (H3) and "composite loop / countdown" (H7) are
**REFUTED** beyond those cases. Native loops are **NOT_DEMONSTRATED** in this
repository. The predicated compiler (H11, `../h10_h12_predicated_v1/`) unrolls
IR loops to a declared bound and says so.
