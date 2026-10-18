#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build
zig build-exe -O ReleaseFast src/bolge19.zig -lc -femit-bin=build/bolge19
printf 'built build/bolge19 with Zig %s\n' "$(zig version)"
