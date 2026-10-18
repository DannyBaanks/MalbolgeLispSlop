# Fixed19 both-arms branch evidence protocol

The `fixed19-zero-double-read-else-echo-v1` lowering recognizes only the
module in `examples/branch_both_arms.slop`. Its first input byte selects the
behavior: zero consumes one byte and then echoes the following byte; nonzero
echoes the immediately following byte. Missing values use the fixed19 EOF byte
`0xda`. This is a second fixed-layout template beside historical H2, not a
general branch linker or certified arbitrary CFG composition.

`tools/verify_both_arms_branch.py` creates a unique run directory. It checks all
256 selector bytes against seven payload/EOF patterns in the concrete model and
`bolge19`, records exact input/stdout/stderr bytes in hexadecimal, and records
model status/output/steps for each corresponding VM run. It separately executes
empty stdin and models it through the full fixed19 address space, covering the
first-read EOF trampoline. It also checks the canonical image with whitespace,
verifies the four nonzero landing copies plus the zero landing, and requires
two canonical image mutants to halt normally with observably incorrect output.
Timeouts, loader errors, and other failures cannot count as successful negative
controls. Run with `python -O` to verify that acceptance checks remain active
when assertions are disabled.

Each run contains both image files, the two negative controls,
`model-traces.json`, `vm-raw.jsonl`, `report.json`, and `SHA256SUMS.txt`. The
report hashes the source, profile, and VM. A pass supports only the named
two-path behavior. General BRZ, relocation/composition, memory, arithmetic,
calls, and MalbolgeLISP remain `NOT_DEMONSTRATED`.

The first two exploratory runs in this directory predate the final negative-
control gate and full-address empty-stdin case. They are preserved as
historical diagnostics, but are superseded and do not count as acceptance
evidence. The run `20261018T191951Z-44715b9f/` is the first run accepted under
the protocol above.
