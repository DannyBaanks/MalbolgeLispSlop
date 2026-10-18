#!/usr/bin/env python3
"""Assemble a ``.slop`` guest into canonical fixed-3^19 source.

Prints the layout the assembler resolved, the image, and the loader-side walk
that had to accept it. ``--check`` re-walks an existing image instead of
emitting one, which is how a reviewer can falsify the rule against a foreign
specimen without touching the assembler.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from slopsynth.assemble import AssemblyError, assemble
from slopsynth.canonical import opcode_names, walk_canonical
from slopsynth.encode import encode_program
from slopsynth.ir_json import load_program
from slopsynth.lang import LangError, format_placed, parse_placed
from slopsynth.profile import load_profile

DEFAULT_PROFILE = REPO / "profiles" / "fixed19.json"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?", help="guest source (.slop)")
    parser.add_argument("--out", type=Path, help="write the image here")
    parser.add_argument(
        "--line-width",
        type=int,
        default=None,
        help="break the image into lines of N cells; the canonical loader ignores them",
    )
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--round-trip", action="store_true", help="re-render the parsed guest")
    parser.add_argument(
        "--against",
        type=Path,
        help="require byte-identity with the image this JSON contract emits",
    )
    parser.add_argument("--check", type=Path, help="walk an existing image, emit nothing")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    if (args.source is None) == (args.check is None):
        parser.error("give exactly one of a guest source or --check")

    profile = load_profile(args.profile)

    if args.check is not None:
        image = args.check.read_bytes()
        walk = walk_canonical(image, profile)
        if not args.quiet:
            print(f"check {args.check.name}: {len(image)} bytes")
            print(f"  accepted_cells={walk.accepted_cells}")
            print(f"  first_opcodes={list(walk.opcodes[:64])}")
            print(f"  names={list(opcode_names(walk.opcodes[:64], profile))}")
            if walk.accepted:
                print("  verdict=ACCEPTED")
            else:
                print(
                    f"  verdict=REJECTED offset={walk.rejected_offset} "
                    f"byte={walk.rejected_byte} reason={walk.reason}"
                )
        return 0 if walk.accepted else 1

    placed = parse_placed(args.source.read_text(encoding="utf-8"))
    if placed.program is None:
        return _assemble_branch(args, placed, profile)

    try:
        built = assemble(placed, profile, line_width=args.line_width)
    except AssemblyError as exc:
        print(f"{args.source.name}: assembly refused: {exc}", file=sys.stderr)
        return 1

    if args.against is not None:
        reference = encode_program(load_program(args.against), profile)
        emitted = built.image.replace(b"\n", b"")
        if reference != emitted:
            print(
                f"NOT byte-identical to {args.against}: "
                f"json={reference!r} text={emitted!r}",
                file=sys.stderr,
            )
            return 1
        if not args.quiet:
            print(f"byte-identical to {args.against}")

    if not args.quiet:
        print(f"{args.source.name}: guest {placed.name}, {built.cells} cells")
        for index, operation in enumerate(placed.program.operations):
            print(f"  cell {built.layout.addresses[index]:>8}  {type(operation).__name__}")
        for address, label in built.layout.labels:
            print(f"  label {label:<12} = cell {address}")
        if built.layout.padded_cells:
            print(f"  padded with {built.layout.padded_cells} nop cell(s)")
        print(f"  walk: accepted_cells={built.walk.accepted_cells} verdict=ACCEPTED")
        if built.line_width is not None:
            unbroken = assemble(placed, profile)
            same = unbroken.image == built.image.replace(b"\n", b"")
            print(f"  spacing-neutral: {same}")
        preview = built.image[:72]
        print(f"  image[0:{len(preview)}]={preview.decode('latin-1')!r}")
        print(f"  image_sha256={_sha(built.image)}")

    if args.round_trip:
        rendered = format_placed(placed)
        reparsed = parse_placed(rendered)
        if reparsed != placed:
            print("round trip changed the parse", file=sys.stderr)
            return 1
        ref = encode_program(reparsed.program, profile)
        if ref != built.image.replace(b"\n", b""):
            print("round trip changed the image", file=sys.stderr)
            return 1
        if not args.quiet:
            print("round-trip: identical")

    if args.out is not None:
        args.out.write_bytes(built.image)
        if not args.quiet:
            print(f"wrote {args.out} ({len(built.image)} bytes)")
    return 0


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _assemble_branch(args, placed, profile) -> int:
    from slopsynth.branch import lower_branch

    if args.against is not None:
        print("--against requires a straight-line JSON goal", file=sys.stderr)
        return 3
    try:
        built = lower_branch(placed.module, profile, line_width=args.line_width)
        if args.round_trip:
            reparsed = parse_placed(format_placed(placed))
            if (reparsed != placed or lower_branch(
                    reparsed.module, profile, line_width=args.line_width).image != built.image):
                raise AssemblyError("round trip changed the module or image")
        if args.out is not None:
            # Evidence and previous outputs are never silently replaced.
            with args.out.open("xb") as stream:
                stream.write(built.image)
    except (AssemblyError, OSError) as exc:
        print(f"{args.source.name}: assembly refused: {exc}", file=sys.stderr)
        return 3
    if not args.quiet:
        print(f"{args.source.name}: guest {placed.name}, {built.cells} cells")
        print(f"  lowering={built.lowering} (scoped H2; general control flow remains unsupported)")
        for label, addresses in built.labels:
            print(f"  label {label}: cells {','.join(map(str, addresses))}")
        print(f"  walk: accepted_cells={built.cells} verdict=ACCEPTED")
        print(f"  image_sha256={_sha(built.image)}")
        if args.round_trip:
            print("round-trip: identical")
        if args.out is not None:
            print(f"wrote {args.out} ({len(built.image)} bytes)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except LangError as exc:
        print(f"syntax error: {exc}", file=sys.stderr)
        sys.exit(2)
