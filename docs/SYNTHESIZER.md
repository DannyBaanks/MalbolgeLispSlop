# Fixed-19 synthesizer

The toolchain targets the repository's fixed-width `3^19` VM and canonical
loader. It generates printable source bytes from the profile's dispatch table
and source positions. It does not establish compatibility with dynamically
widening Unshackled or Malbolge Free.

## Synthesize and run the echo guest

Build the VM, then run:

```sh
python3 tools/synthesize_guest.py examples/echo.json \
  --profile profiles/fixed19.json \
  --output build/synth/echo.mb \
  --manifest build/synth/echo.manifest.json \
  --max-cells 3 --max-nodes 10000 --max-steps 8 --max-address 8
```

The tool derives the three bytes from the typed `ReadA`, `WriteA`, and `Halt`
operations and the profile. The generated image is `ubO`. It runs the guest
under `bolge19` for byte-boundary and EOF inputs before reporting success.
`make synth-echo` runs the same command after building the VM.

Output and manifest paths must be new. The command exits with a bounded-search
status and writes no artifact if synthesis does not return `FOUND`. When a
candidate is found, the manifest records the profile and program digests,
generator revision and source digest, algorithm, exact bounds, explored node
count, generated image digest, and actual guest validation cases. The manifest
contains no run timestamp, so equivalent inputs produce identical bytes.

Verify the image and its source inputs with:

```sh
python3 tools/verify_generated_guest.py \
  build/synth/echo.mb build/synth/echo.manifest.json \
  --profile profiles/fixed19.json --goal examples/echo.json
```

Changing the generated image, profile, or goal makes verification fail.

## Guest runner contract

`tools/guest_runner.py` returns raw stdout and stderr as bytes and separates
`HALT`, `MAX_STEPS`, `LOAD_ERROR`, `WALL_TIMEOUT`, `OUTPUT_LIMIT`, and
`PROCESS_ERROR`. It enforces wall time, `RLIMIT_AS`, and the configured stdout
capture limit while draining child pipes. Stderr is drained separately with a
one-MiB cap. A status is never inferred from the process exit code alone.

## Current synthesis boundary

The one-node direct lowering supports straight-line `ReadA`, `WriteA`, and
`Halt`. A separate bounded dispatcher enumerator explores advanced typed
modules, but branch, guest memory, arithmetic, loops, and call/return remain
`NOT_DEMONSTRATED` within the current 1,000-node capability campaign. See
[`SYNTHESIS_FEASIBILITY.md`](SYNTHESIS_FEASIBILITY.md) and its immutable raw
campaign evidence. The full Lisp guest plan cannot start until those gates
demonstrate guest execution.

## Satire estimate

The review-time command measures the selected artifact's current byte length
and reports sequential-reading estimates under explicit assumptions:

```sh
python3 tools/estimate_review_time.py build/synth/echo.mb \
  --bytes-per-second 1 --hours-per-day 8
```

`make review-time-estimate` runs it on the generated echo guest. The estimate
is a joke about character-by-character inspection; it is not a measure of
semantic review or program correctness. The calculation uses the artifact on
disk, not a historical size.
