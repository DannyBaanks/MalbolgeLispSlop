"""Independent integer-SMT transitions for the actual fixed19 bolge19 VM.

Z3 is a construction/test dependency, never part of guest execution. Integers
are used deliberately: wrapping at 3**19 is not bit-vector wrapping at 2**32.
No transition is delegated to the concrete model this implementation checks.
"""

from dataclasses import dataclass, fields

import z3

from .canonical import walk_canonical
from .profile import LoaderRule, Profile

PAGE = 65536
TABLE = ((1, 0, 0), (1, 0, 2), (2, 2, 1))
TRANSLATION = ("SOMEBODY MAKE ME FEEL ALIVE"
               "[hj9>,5z]&gqtyfr$(we4{WP)H-Zn,[%\\3dL+Q;>U!pJS72FhOA1CB6v^=I_0/8|jsb9m<.TVac`uY*MK'X~xDl}REokN:#?G\"i@"
               "AND SHATTER ME")


def require_profile(profile):
    expected_loaders = {
        "raw": LoaderRule(False, True, False, (9, 10, 13, 32), None, 0, 256),
        "canonical": LoaderRule(True, False, True, (9, 10, 13, 32), 564, 33, 127),
    }
    if (profile.trits != 19 or profile.end != 3**19 or profile.eof_value != 3**19 - 1
            or dict(profile.dispatch) != dict(jump=4, output=5, input=23, rotate=39,
                                             move=40, crazy=62, nop=68, halt=81)
            or dict(profile.loaders) != expected_loaders):
        raise ValueError("symbolic target is the actual bolge19 fixed19 machine")


def _integer(value):
    if type(value) is int:
        return z3.IntVal(value)
    if not z3.is_int(value):
        raise ValueError("symbolic machine words must be Z3 integers or Python integers")
    return value


def crazy(control, cell, trits=19):
    control, cell = _integer(control), _integer(cell)
    value = z3.IntVal(0)
    for index in range(trits):
        col, row = (control / 3**index) % 3, (cell / 3**index) % 3
        digit = z3.If(row == 0, z3.If(col == 0, 1, 0),
                      z3.If(row == 1, z3.If(col == 0, 1, z3.If(col == 1, 0, 2)),
                            z3.If(col == 2, 1, 2)))
        value += 3**index * digit
    return z3.simplify(value)


def rotate(word, profile):
    word = _integer(word)
    third = profile.end // 3
    low = word % third
    return z3.simplify(low / 3 + (low % 3) * (third // 3) + word - low)


def _crazy_constant(control, cell, trits):
    result, place = 0, 1
    for _ in range(trits):
        result += TABLE[cell % 3][control % 3] * place
        control //= 3
        cell //= 3
        place *= 3
    return result


def _choices(index, values, default=0):
    value = z3.IntVal(default)
    end = len(values) - 1
    while end >= 0:
        start, item = end, values[end]
        # Loaded padding often has long runs. Keep the exact array compact at
        # page boundaries instead of constructing 65,536 identical branches.
        while (start > 0 and type(item) is int and type(values[start - 1]) is int
               and values[start - 1] == item):
            start -= 1
        condition = index == start if start == end else z3.And(index >= start, index <= end)
        value = z3.If(condition, item, value)
        end = start - 1
    return value


def initial_memory(cells: bytes, profile: Profile):
    """Exact loaded cells + continuous chain + paged default, as a Z3 array.

    The recurrence is detected as an actual repeated pair, not guessed from a
    six-element prefix. Thus the eager chain needs no 65,536-branch expression.
    """
    require_profile(profile)
    if len(cells) > profile.end:
        raise ValueError("invalid loaded image size")
    older = cells[-2] if len(cells) > 1 else 0
    newer = cells[-1] if cells else 0
    seen, sequence = {}, []
    while (older, newer) not in seen:
        if len(sequence) >= 64:
            raise ValueError("fixed19 fill recurrence did not stabilize within its bound")
        seen[(older, newer)] = len(sequence)
        value = _crazy_constant(newer, older, profile.trits)
        sequence.append(value)
        older, newer = newer, value
    prefix = seen[(older, newer)]
    cycle = sequence[prefix:]

    def fill(offset):
        return z3.If(offset < prefix, _choices(offset, sequence[:prefix]),
                     _choices((offset - prefix) % len(cycle), cycle))

    size = len(cells)
    zone = ((size + PAGE - 1) // PAGE) * PAGE
    # pat begins after the entire eager chain, regardless of later writes.
    pattern = [z3.simplify(fill(z3.IntVal(zone - size + i))).as_long() for i in range(6)]
    address = z3.Int("fixed19_initial_address")
    page_base = (address / PAGE) * PAGE
    phase = (page_base % (profile.end // 3) + address - page_base) % 6
    return z3.Lambda(address,
                     z3.If(address < size, _choices(address, cells),
                           z3.If(address < zone, fill(address - size), _choices(phase, pattern))))


@dataclass(frozen=True)
class State:
    memory: object
    a: object
    c: object
    d: object
    input_position: object
    output: object
    output_length: object
    steps: object
    halted: object
    bounded: object


def initial_state(image: bytes, profile: Profile, *, loader="canonical"):
    require_profile(profile)
    if not image or len(image) > profile.end:
        raise ValueError("invalid source image size")
    if loader == "canonical":
        walk = walk_canonical(image, profile)
        if not walk.accepted:
            raise ValueError("canonical load rejected")
        cells = bytes(b for b in image if b not in profile.loaders[loader].whitespace_bytes)
    elif loader == "raw":
        cells = image
    else:
        raise ValueError("unknown loader")
    zero = z3.IntVal(0)
    return State(initial_memory(cells, profile), zero, zero, zero, zero,
                 z3.K(z3.IntSort(), zero), zero, zero, z3.BoolVal(False), z3.BoolVal(False))


def step(state: State, inputs, input_length, profile: Profile, *, max_address: int):
    """One cycle, including exact partial state on a post-jump model bound.

    Caller contracts constrain symbolic word values to [0, END), input length
    to a nonnegative integer and live input bytes to [0,255]. Stopped states
    stutter; reaching a horizon is handled by the caller, never called HALT.
    """
    require_profile(profile)
    if not 0 <= max_address < profile.end:
        raise ValueError("max_address must be inside the profile")
    a, c, d, memory = state.a, state.c, state.d, state.memory
    third = profile.end // 3
    one = ((94 - (((profile.end - 1) // 6 - 29524) % 94) - third) % 94) + 94
    two = 94 - (((profile.end - 1) // 3 - 59048) % 94) - ((2 * third) % 94) + 94
    offset = z3.If(c < third, 0, z3.If(c < 2 * third, one, two))
    opcode = z3.simplify((z3.Select(memory, c) + c + offset) % 94)
    jump, output, read, rot, move, opr, halt = [opcode == profile.dispatch[name]
        for name in ("jump", "output", "input", "rotate", "move", "crazy", "halt")]
    live = z3.Not(z3.Or(state.halted, state.bounded))
    def valid(address):
        return z3.And(address >= 0, address <= max_address, address < profile.end)
    access_ok = z3.And(valid(c), z3.Or(z3.Not(z3.Or(jump, rot, move, opr)), valid(d)))
    active = z3.And(live, access_ok, z3.Not(halt))
    data = z3.simplify(z3.Select(memory, d))
    rotated, transformed = rotate(data, profile), crazy(a, data, profile.trits)
    after_memory = z3.If(rot, z3.Store(memory, d, rotated),
                         z3.If(opr, z3.Store(memory, d, transformed), memory))
    after_a = z3.If(read, z3.If(state.input_position < input_length,
                              z3.Select(inputs, state.input_position), profile.eof_value),
                    z3.If(rot, rotated, z3.If(opr, transformed, a)))
    after_c, after_d = z3.If(jump, data, c), z3.If(move, data, d)
    encryption_ok = valid(after_c)
    byte = z3.simplify(z3.Select(after_memory, after_c))
    translated = _choices(byte, tuple(map(ord, TRANSLATION)))
    encrypted_memory = z3.If(z3.And(byte >= 0, byte < len(TRANSLATION)),
                             z3.Store(after_memory, after_c, translated), after_memory)
    successful = z3.And(active, encryption_ok)
    result = State(
        z3.If(active, z3.If(encryption_ok, encrypted_memory, after_memory), memory),
        z3.If(active, after_a, a),
        z3.If(active, z3.If(encryption_ok, (after_c + 1) % profile.end, after_c), c),
        z3.If(active, z3.If(encryption_ok, (after_d + 1) % profile.end, after_d), d),
        state.input_position + z3.If(z3.And(active, read, state.input_position < input_length), 1, 0),
        z3.If(z3.And(active, output), z3.Store(state.output, state.output_length, a % 256), state.output),
        state.output_length + z3.If(z3.And(active, output), 1, 0),
        state.steps + z3.If(successful, 1, 0),
        z3.Or(state.halted, z3.And(live, access_ok, halt)),
        z3.Or(state.bounded, z3.And(live, z3.Not(access_ok)),
              z3.And(active, z3.Not(encryption_ok))),
    )
    return State(*(z3.simplify(getattr(result, field.name)) for field in fields(State)))


def run_concrete(image, stdin, profile, *, loader, max_steps, max_address):
    """Evaluate ground symbolic transitions for differential tests, not Lisp."""
    if type(max_steps) is not int or max_steps <= 0:
        raise ValueError("max_steps must be positive")
    require_profile(profile)
    if not 0 <= max_address < profile.end:
        raise ValueError("invalid max_address")
    try:
        state = initial_state(image, profile, loader=loader)
    except ValueError:
        return {"status": "LOAD_ERROR", "stdout": b"", "steps": 0, "a": 0, "c": 0, "d": 0}
    inputs = z3.K(z3.IntSort(), 0)
    for position, byte in enumerate(stdin):
        inputs = z3.Store(inputs, position, byte)
    for _ in range(max_steps):
        state = step(state, inputs, z3.IntVal(len(stdin)), profile, max_address=max_address)
        if z3.is_true(state.halted) or z3.is_true(state.bounded):
            break
    def number(value):
        return z3.simplify(value).as_long()
    status = "HALT" if z3.is_true(state.halted) else "MODEL_BOUND" if z3.is_true(state.bounded) else "MAX_STEPS"
    return {"status": status,
            "stdout": bytes(number(z3.Select(state.output, i)) for i in range(number(state.output_length))),
            "steps": number(state.steps), "a": number(state.a), "c": number(state.c), "d": number(state.d)}
