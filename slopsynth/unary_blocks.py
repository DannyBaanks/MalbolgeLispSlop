"""Synthesize code-restoring native OPR/ROT blocks, with explicit installed state.

These are primitives for the general compiler, not its bootstrap. Their data
records and inert landing pads must already be installed. The raw probe is a
VM control only; it is not a canonical image or a Lisp implementation.
"""
from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path

import z3

from .proofs import Z3_VERSION, canonical_smt2, verify_implication
from . import symbolic as sm


@dataclass(frozen=True)
class UnaryBlock:
    operation: str
    entry: int
    code: bytes


@dataclass(frozen=True)
class SearchStep:
    status: str
    query_smt2: str
    query_sha256: str
    candidate_entry: int | None
    candidate_byte: int | None


@dataclass(frozen=True)
class UnarySearchResult:
    status: str
    block: UnaryBlock | None
    reason: str
    queries: int
    query_smt2: str
    transcript: tuple[SearchStep, ...]
    timeout_ms: int
    resource_limit: int
    max_queries: int
    z3_version: str


def synthesize_unary(operation, profile, *, timeout_ms, resource_limit, max_queries=100):
    """Find the least first-region residue with a two-encryption code cycle.

    After OPR/ROT, JMP enters that same cell to encrypt it back, then executes
    the same JMP again with the next record pointer to leave the block. JMP
    itself stays intact because it encrypts its destination, not its own cell.
    The bounded domain is C=0..93, canonical initial instruction bytes=33..126.
    """
    sm.require_profile(profile)
    if z3.get_version_string() != Z3_VERSION:
        raise ValueError(f"synthesis requires z3-solver=={Z3_VERSION}.0")
    if operation not in {"crazy", "rotate"}:
        raise ValueError("unary synthesis supports native crazy and rotate")
    if any(type(v) is not int or v <= 0 for v in (timeout_ms, resource_limit, max_queries)):
        raise ValueError("synthesis requires explicit positive budgets")
    c, byte = z3.Ints("unary_placement_c unary_placement_byte")
    # Exhaust the small concrete encryption table before sending finite choices
    # to SMT. No bounded search over words is substituted for the later proof.
    cycle_bytes = [b for b in range(33, 127)
                   if ord(sm.TRANSLATION[b]) < len(sm.TRANSLATION)
                   and ord(sm.TRANSLATION[ord(sm.TRANSLATION[b])]) == b]
    transcript = []
    # Fix each small residue in ascending order. Otherwise Z3 may choose a
    # different satisfying C after unrelated queries in this process, making
    # an equivalent search transcript impossible to replay exactly.
    for candidate_entry in range(94):
        queries = candidate_entry + 1
        if queries > max_queries:
            last_query = transcript[-1].query_smt2 if transcript else ""
            return UnarySearchResult("BUDGET_EXHAUSTED", None, "placement query budget",
                                     max_queries, last_query, tuple(transcript), timeout_ms,
                                     resource_limit, max_queries, Z3_VERSION)
        solver = z3.Solver()
        solver.set(timeout=timeout_ms, rlimit=resource_limit)
        solver.add(c == candidate_entry, byte >= 33, byte < 127,
                   (byte + c) % 94 == profile.dispatch[operation],
                   z3.Or(*(byte == b for b in cycle_bytes)))
        outcome = solver.check()
        query = canonical_smt2(solver)
        if outcome == z3.sat:
            model = solver.model()
            entry, code = model[c].as_long(), model[byte].as_long()
            transcript.append(SearchStep("SAT", query, hashlib.sha256(query.encode()).hexdigest(),
                                          entry, code))
            jump = (profile.dispatch["jump"] - (entry + 1) - 33) % 94 + 33
            block = UnaryBlock(operation, entry, bytes((code, jump)))
            return UnarySearchResult("FOUND", block, "", queries, query, tuple(transcript),
                                     timeout_ms, resource_limit, max_queries, Z3_VERSION)
        transcript.append(SearchStep("UNSAT" if outcome == z3.unsat else "UNKNOWN", query,
                                     hashlib.sha256(query.encode()).hexdigest(), None, None))
        if outcome == z3.unknown:
            return UnarySearchResult("UNKNOWN", None, solver.reason_unknown(), queries, query,
                                     tuple(transcript), timeout_ms, resource_limit, max_queries, Z3_VERSION)
    return UnarySearchResult("NOT_FOUND_WITHIN_BOUNDS", None, "", 94, query,
                             tuple(transcript), timeout_ms, resource_limit, max_queries,
                             Z3_VERSION)


def verify_unary(block, profile, *, data_address, exit_address, timeout_ms, resource_limit):
    """Prove the three-cycle block for all word A/data and all other memory.

    Installed precondition: code at C,C+1; record at D..D+2 is [word,C,exit-1];
    inert landing pad M[exit-1]=141. Distinct code/record/pad addresses are
    mandatory. Exit: C=exit,D=Dentry+3,A=op(Aentry,word), code restored, no I/O,
    no halt/bound, and EXACTLY M[Dentry] may change. This is one macro call;
    preserved code/record pointers permit subsequent invocations with another
    record. Bootstrap, pointer scheduling and long composition remain separate.
    """
    sm.require_profile(profile)
    if block.operation not in {"crazy", "rotate"} or len(block.code) != 2:
        raise ValueError("invalid unary block")
    if any(type(v) is not int for v in (block.entry, data_address, exit_address)):
        raise ValueError("layout addresses must be integers")
    addresses = (block.entry, block.entry + 1, data_address, data_address + 1,
                 data_address + 2, exit_address - 1)
    if (len(set(addresses)) != len(addresses)
            or any(v < 0 or v >= profile.end for v in (*addresses, data_address + 3, exit_address))):
        raise ValueError("overlapping or out-of-profile unary block layout")
    a, word = z3.Ints("unary_entry_a unary_entry_word")
    memory = z3.Array("unary_other_memory", z3.IntSort(), z3.IntSort())
    for address, value in ((block.entry, block.code[0]), (block.entry + 1, block.code[1]),
                           (data_address, word), (data_address + 1, block.entry),
                           (data_address + 2, exit_address - 1), (exit_address - 1, 141)):
        memory = z3.Store(memory, address, value)
    zero, false = z3.IntVal(0), z3.BoolVal(False)
    outputs = z3.K(z3.IntSort(), zero)
    state = sm.State(memory, a, z3.IntVal(block.entry), z3.IntVal(data_address),
                     zero, outputs, zero, zero, false, false)
    inputs = z3.K(z3.IntSort(), zero)
    for _ in range(3):
        state = sm.step(state, inputs, zero, profile, max_address=profile.end - 1)
    expected = sm.crazy(a, word) if block.operation == "crazy" else sm.rotate(word, profile)
    return verify_implication(
        [a >= 0, a < profile.end, word >= 0, word < profile.end],
        [state.a == expected, state.c == exit_address, state.d == data_address + 3,
         state.memory == z3.Store(memory, data_address, expected),
         z3.Not(state.halted), z3.Not(state.bounded), state.steps == 3,
         state.input_position == 0, state.output_length == 0, state.output == outputs],
        timeout_ms=timeout_ms, resource_limit=resource_limit, witnesses={"a": a, "word": word})


def raw_two_call_probe(block, first, second):
    """98-byte raw fixture: byte input -> same native block twice -> byte output.

    Only installed words representable as bytes can be used in this control.
    Native proof covers all 19-trit values; this fixture tests actual VM reuse.
    """
    if (block.operation not in {"crazy", "rotate"} or len(block.code) != 2
            or not 50 <= block.entry < 90 or block.entry in {81, 85}):
        raise ValueError("block does not fit the bounded two-call raw fixture")
    if any(type(v) is not int or not 0 <= v <= 255 for v in (first, second)):
        raise ValueError("raw fixture data must fit in bytes")
    image = bytearray([141] * 98)
    # INPUT; MOVE (D=39+1); JMP (M[40]=entry-1, D=41).
    image[0:3] = bytes((23, 39, 2))
    for address, value in ((40, block.entry - 1), (41, first), (42, block.entry),
                           (43, 91), (45, block.entry - 1), (46, second),
                           (47, block.entry), (48, 95), (92, (5 - 92) % 94),
                           (93, (4 - 93) % 94), (96, (5 - 96) % 94),
                           (97, (81 - 97) % 94)):
        image[address] = value
    image[block.entry:block.entry + 2] = block.code
    return bytes(image)


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _assemble_certificate(block, search, profile, data_address, exit_address,
                          proof_timeout_ms, proof_resource_limit):
    root = Path(__file__).resolve().parents[1]
    proof = verify_unary(block, profile, data_address=data_address, exit_address=exit_address,
                         timeout_ms=proof_timeout_ms, resource_limit=proof_resource_limit)
    if proof.status != "VERIFIED":
        raise ValueError(f"block proof refused with status {proof.status}")
    return {
        "schema_version": 1,
        "status": "VERIFIED_BLOCK",
        "z3_version": Z3_VERSION,
        "operation": block.operation,
        "block": {"entry": block.entry, "code_hex": block.code.hex(),
                  "sha256": hashlib.sha256(block.code).hexdigest()},
        "layout": {"data_address": data_address, "exit_address": exit_address,
                   "installed_landing_word": 141},
        "limits": {"placement_timeout_ms": search.timeout_ms,
                   "placement_resource_limit": search.resource_limit,
                   "placement_max_queries": search.max_queries,
                   "proof_timeout_ms": proof_timeout_ms,
                   "proof_resource_limit": proof_resource_limit},
        "search": {"status": search.status, "queries": search.queries,
                   "transcript": [asdict(step) for step in search.transcript]},
        "proof": asdict(proof),
        "artifacts": {
            "profile_sha256": _digest(root / "profiles/fixed19.json"),
            "vm_sha256": _digest(root / "build/bolge19"),
            "vm_source_sha256": _digest(root / "src/bolge19.zig"),
            "generator_sha256": _digest(Path(__file__)),
            "proof_engine_sha256": _digest(root / "slopsynth/proofs.py"),
            "symbolic_model_sha256": _digest(root / "slopsynth/symbolic.py"),
            "dependency_lock_sha256": _digest(root / "requirements-dev.txt"),
        },
        "scope": "reusable three-cycle OPR/ROT primitive with preinstalled code, records, and landing pad",
        "not_demonstrated": ["canonical bootstrap", "general control-flow compiler", "guest Lisp"],
    }


def make_certificate(search, profile, *, data_address, exit_address,
                     proof_timeout_ms, proof_resource_limit):
    """Create a replayable placement transcript and universal block contract."""
    if search.status != "FOUND" or search.block is None:
        raise ValueError("only a completely searched FOUND result can be certified")
    replayed = synthesize_unary(search.block.operation, profile,
                                timeout_ms=search.timeout_ms,
                                resource_limit=search.resource_limit,
                                max_queries=search.max_queries)
    if asdict(replayed) != asdict(search):
        raise ValueError("placement transcript does not replay exactly")
    return _assemble_certificate(search.block, search, profile, data_address, exit_address,
                                 proof_timeout_ms, proof_resource_limit)


def replay_certificate(certificate, profile):
    """Refuse stale, relabeled, altered, unknown or unreplayable certificates."""
    if not isinstance(certificate, dict) or certificate.get("schema_version") != 1:
        raise ValueError("unsupported block certificate schema")
    try:
        operation = certificate["operation"]
        block_data = certificate["block"]
        limits = certificate["limits"]
        layout = certificate["layout"]
        search_data = certificate["search"]
        if set(block_data) != {"entry", "code_hex", "sha256"}:
            raise ValueError("block identity fields changed")
        if (not isinstance(block_data["entry"], int)
                or not isinstance(block_data["code_hex"], str)
                or not isinstance(block_data["sha256"], str)):
            raise ValueError("invalid block identity")
        code = bytes.fromhex(block_data["code_hex"])
        if hashlib.sha256(code).hexdigest() != block_data["sha256"]:
            raise ValueError("block image digest mismatch")
        expected_limit_names = {"placement_timeout_ms", "placement_resource_limit",
                                "placement_max_queries", "proof_timeout_ms", "proof_resource_limit"}
        if set(limits) != expected_limit_names or set(layout) != {
            "data_address", "exit_address", "installed_landing_word"
        } or layout["installed_landing_word"] != 141:
            raise ValueError("block layout or search limits changed")
        if set(search_data) != {"status", "queries", "transcript"} or search_data["status"] != "FOUND":
            raise ValueError("search record is incomplete")
        replayed = synthesize_unary(operation, profile,
                                    timeout_ms=limits["placement_timeout_ms"],
                                    resource_limit=limits["placement_resource_limit"],
                                    max_queries=limits["placement_max_queries"])
        if (replayed.status != "FOUND" or replayed.queries != search_data["queries"]
                or [asdict(step) for step in replayed.transcript] != search_data["transcript"]
                or replayed.block != UnaryBlock(operation, block_data["entry"], code)):
            raise ValueError("placement search transcript does not replay")
        expected = _assemble_certificate(
            replayed.block, replayed, profile, layout["data_address"], layout["exit_address"],
            limits["proof_timeout_ms"], limits["proof_resource_limit"])
    except (KeyError, TypeError, UnicodeError) as exc:
        raise ValueError(f"invalid unary block certificate: {exc}") from exc
    if certificate != expected:
        raise ValueError("certificate metadata, proof, or artifact binding does not replay")
    return {"status": "VERIFIED_BLOCK", "proof": expected["proof"],
            "artifacts": expected["artifacts"]}
