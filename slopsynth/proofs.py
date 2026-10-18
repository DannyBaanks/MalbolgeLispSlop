"""Bounded SMT implication checks; no search outcome is promoted to proof."""
from dataclasses import dataclass
import hashlib
import re

import z3

Z3_VERSION = "4.16.0"


def canonical_smt2(solver):
    """Alpha-rename Z3's generated ``$xNN`` let binders for stable replay hashes."""
    mapping = {}

    def rename(match):
        symbol = match.group(0)
        if symbol not in mapping:
            mapping[symbol] = f"$let_{len(mapping)}"
        return mapping[symbol]

    # Z3 uses both $xN let binders and ?xN array terms. Both counters depend
    # on every query previously built in the process.
    return re.sub(r"(?:\$x\d+|\?x\d+)", rename, solver.to_smt2())


@dataclass(frozen=True)
class ProofResult:
    status: str
    phase: str
    reason: str
    witnesses: dict
    query_smt2: str
    query_sha256: str
    z3_version: str
    timeout_ms: int
    resource_limit: int
    feasibility_smt2: str
    feasibility_sha256: str
    feasibility_witnesses: dict


def verify_implication(preconditions, guarantees, *, timeout_ms, resource_limit, witnesses=None):
    """Check feasible P and absence of P & !Q. All free variables are universal.

    VERIFIED means exactly this bounded mathematical implication. It does not
    identify a VM image, prove the caller modeled that image, or certify a
    reusable block. Those bindings belong to the block verifier and manifest.
    Both queries have explicit time/resource limits; UNKNOWN is preserved at
    either phase, including when the precondition could not be shown feasible.
    """
    if z3.get_version_string() != Z3_VERSION:
        raise ValueError(f"proof replay requires z3-solver=={Z3_VERSION}.0")
    if (type(timeout_ms) is not int or timeout_ms <= 0
            or type(resource_limit) is not int or resource_limit <= 0):
        raise ValueError("proof checks require positive integer budgets")
    # Contracts may arrive as generators. Freeze them ONCE before validation,
    # otherwise the validation traversal could erase every asserted condition.
    preconditions, guarantees = tuple(preconditions), tuple(guarantees)
    if not preconditions or not guarantees:
        raise ValueError("proof check needs explicit preconditions and guarantees")
    for expression in (*preconditions, *guarantees):
        if type(expression) is not bool and not z3.is_bool(expression):
            raise ValueError("contract expressions must be Boolean")
    witnesses = {} if witnesses is None else dict(witnesses)
    if any(not isinstance(name, str) or not z3.is_int(term) for name, term in witnesses.items()):
        raise ValueError("witnesses must name integer expressions")

    def solver():
        value = z3.Solver()
        value.set(timeout=timeout_ms, rlimit=resource_limit)
        value.add(*preconditions)
        return value

    feasibility_query = ""
    feasibility_values = {}

    def result(status, phase, query, reason="", values=None):
        smt2 = canonical_smt2(query)
        if phase == "precondition":
            feasibility_smt2 = smt2
            feasibility_sha256 = hashlib.sha256(smt2.encode()).hexdigest()
            feasibility_witnesses = values or {}
        else:
            feasibility_smt2 = feasibility_query
            feasibility_sha256 = hashlib.sha256(feasibility_smt2.encode()).hexdigest()
            feasibility_witnesses = feasibility_values
        return ProofResult(status, phase, reason, values or {}, smt2,
                           hashlib.sha256(smt2.encode()).hexdigest(), Z3_VERSION,
                           timeout_ms, resource_limit, feasibility_smt2,
                           feasibility_sha256, feasibility_witnesses)

    feasible = solver()
    outcome = feasible.check()
    if outcome == z3.unsat:
        return result("INFEASIBLE_PRECONDITION", "precondition", feasible)
    if outcome != z3.sat:
        return result("UNKNOWN", "precondition", feasible, feasible.reason_unknown())
    feasibility_query = canonical_smt2(feasible)
    feasible_model = feasible.model()
    feasibility_values = {
        name: feasible_model.eval(term, model_completion=True).as_long()
        for name, term in witnesses.items()
    }
    violation = solver()
    violation.add(z3.Not(z3.And(*guarantees)))
    outcome = violation.check()
    if outcome == z3.unsat:
        return result("VERIFIED", "violation", violation)
    if outcome != z3.sat:
        return result("UNKNOWN", "violation", violation, violation.reason_unknown())
    model = violation.model()
    values = {name: model.eval(term, model_completion=True).as_long()
              for name, term in witnesses.items()}
    return result("COUNTEREXAMPLE", "violation", violation, values=values)
