# Third-party notices

## `src/bolge19.zig`

Copied verbatim from `malbolge-lisp-forensics/src/bolge19/main.zig` at the
M0-inspected revision. Source SHA-256:

```text
47758a3f667f4089f6029d86130b94f14f082d4c113a212b8ff571d84113e8a3
```

The forensics repository's MIT license covers forensic additions in `src/`,
`scripts/`, `docs/`, and `evidence/`; its license file SHA-256 is
`e922e7d34068ba65bb0466f19be10a4d6b8c10ea6bc76fed5b7180eca5e6297a`. The
source identifies its relationship to the `fast20.c` MalbolgeLISP profile.
The original MalbolgeLISP upstream code is not copied into this repository.

## MalbolgeLISP upstream

`fast20.c` and `fast20_original.c` were inspected for the M0 baseline; the
patched `fast20.c` was also compiled and run once as a local differential. They
are not included here. The upstream repository's metadata is inconsistent about
the license applying to the core program. No upstream Lisp specimen or manual
is redistributed by this project.
