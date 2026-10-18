# M1 evidence index

- `slice-20261018.json` and `run.log` preserve the first 11-check run before
  the constrained allocation-failure case was added.
- `slice-20261018-final.json` and `run-final.log` are the final 12-check M1
  run, including a 64 MiB child address-space cap that triggers the Zig
  runtime's allocation panic while loading a 16 MiB image.
- `fast20-differential.json` and `.log` record one input-byte comparison with
  the related C `fast20` implementation. This is not an independent oracle.
- `build.log` records the Zig build command and result.

All outputs and source/fixture hashes are listed in `../SHA256SUMS.txt`.
Timeout supervision is tested with an immediate deadline. No infinite guest
has been demonstrated.
