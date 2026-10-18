"""Independent expectations for the fixed19 symbolic machine."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SymbolicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from slopsynth.profile import load_profile
        cls.profile = load_profile(ROOT / "profiles/fixed19.json")

    def api(self):
        try:
            from slopsynth import symbolic
        except ImportError:
            self.fail("exact symbolic machine is not implemented")
        return symbolic

    def test_symbolic_vm_refuses_profiles_that_do_not_describe_bolge19(self):
        from dataclasses import replace
        sm = self.api()
        altered = dict(self.profile.dispatch)
        altered["nop"] = 69
        with self.assertRaises(ValueError):
            sm.initial_state(b"ubO", replace(self.profile, dispatch=altered))
        loaders = dict(self.profile.loaders)
        loaders["canonical"] = replace(loaders["canonical"], byte_min=32)
        with self.assertRaises(ValueError):
            sm.initial_state(b"ubO", replace(self.profile, loaders=loaders), loader="raw")

    def test_operators_use_cell_row_and_keep_top_rotation_trit(self):
        import z3
        sm = self.api()
        def number(value):
            return z3.simplify(value).as_long()
        self.assertEqual(number(sm.crazy(z3.IntVal(0), z3.IntVal(0), 1)), 1)
        self.assertEqual(number(sm.crazy(z3.IntVal(1), z3.IntVal(0), 1)), 0)
        self.assertEqual(number(sm.crazy(z3.IntVal(0), z3.IntVal(1), 1)), 1)
        third = 3 ** 18
        self.assertEqual(number(sm.rotate(z3.IntVal(third + 1), self.profile)), third + 3**17)

    def test_integer_constants_in_symbolic_helpers_are_exact(self):
        import z3
        sm = self.api()
        for value in (0, 1, 2, 255, 3**18, self.profile.end - 1):
            self.assertTrue(z3.is_true(z3.simplify(
                sm.rotate(value, self.profile) == sm.rotate(z3.IntVal(value), self.profile))))
            for cell in (0, 1, 2, 255, self.profile.end - 1):
                self.assertTrue(z3.is_true(z3.simplify(
                    sm.crazy(value, cell) == sm.crazy(z3.IntVal(value), z3.IntVal(cell)))))

    def test_lazy_memory_matches_independently_rebuilt_chain_and_page_phase(self):
        import z3
        sm = self.api()
        from slopsynth.model import _Memory
        actual = sm.initial_memory(b"ubO", self.profile)
        reference = _Memory([117, 98, 79], self.profile, self.profile.end - 1, None, None)
        for address in (0, 2, 3, 4, 5, 19, 65535, 65536, 65537,
                        3**18 - 1, 3**18, 2 * 3**18, self.profile.end - 1):
            with self.subTest(address=address):
                self.assertEqual(z3.simplify(z3.Select(actual, address)).as_long(),
                                 reference.get(address))

    def test_memory_fill_at_page_aligned_image_sizes(self):
        import z3
        sm = self.api()
        from slopsynth.model import _Memory
        for size in (65535, 65536, 65537):
            cells = b"ubO" + bytes(size - 3)
            memory = sm.initial_memory(cells, self.profile)
            concrete = _Memory(list(cells), self.profile, self.profile.end - 1, None, None)
            for address in (size - 1, size, size + 1, 131071, 131072, 3**18, 2 * 3**18):
                self.assertEqual(z3.simplify(z3.Select(memory, address)).as_long(), concrete.get(address))

    def test_symbolic_echo_and_eof_have_exact_results(self):
        import z3
        sm = self.api()
        for data, expected in ((b"A", b"A"), (b"\xff", b"\xff"), (b"", b"\xda")):
            result = sm.run_concrete(b"ubO", data, self.profile,
                                     loader="canonical", max_steps=8, max_address=8)
            self.assertEqual(result["status"], "HALT")
            self.assertEqual(result["stdout"], expected)
            self.assertEqual(result["steps"], 2)

    def test_every_native_instruction_matches_existing_concrete_model(self):
        sm = self.api()
        from slopsynth.encode import encode_dispatch_sequence
        from slopsynth.model import run_model
        from tools.guest_runner import RunConfig, run_guest
        import re
        import tempfile
        for opcode in self.profile.dispatch:
            image = encode_dispatch_sequence([opcode, "input", "output", "halt"], self.profile)
            for stdin in (b"", b"\x00", b"\xff"):
                with self.subTest(opcode=opcode, stdin=stdin):
                    concrete = run_model(image, stdin, self.profile, loader="canonical",
                                         max_steps=12, max_address=256)
                    symbolic = sm.run_concrete(image, stdin, self.profile,
                                              loader="canonical", max_steps=12, max_address=256)
                    self.assertEqual((symbolic["status"], symbolic["stdout"],
                                      symbolic["steps"], symbolic["a"], symbolic["c"], symbolic["d"]),
                                     (concrete.status.value, concrete.stdout, concrete.steps,
                                      concrete.final_a, concrete.final_c, concrete.final_d))
                    with tempfile.TemporaryDirectory() as directory:
                        path = Path(directory) / "instruction.mb"
                        path.write_bytes(image)
                        vm = run_guest(path, stdin, RunConfig("canonical", 12, 5, 536870912, 32))
                    if symbolic["status"] != "MODEL_BOUND":
                        self.assertEqual((symbolic["status"], symbolic["stdout"]), (vm.status.value, vm.stdout))
                        if vm.status.value == "HALT":
                            telemetry = re.search(rb"HALT steps=(\d+) c=(\d+) d=(\d+) a=(\d+)", vm.stderr)
                            self.assertIsNotNone(telemetry)
                            self.assertEqual(tuple(map(int, telemetry.groups())),
                                             (symbolic["steps"], symbolic["c"], symbolic["d"], symbolic["a"]))

    def test_loader_distinguishes_empty_file_from_whitespace_only_canonical(self):
        sm = self.api()
        from slopsynth.model import run_model
        from tools.guest_runner import RunConfig, run_guest
        import tempfile
        for image, loader in ((b"", "canonical"), (b"", "raw"),
                              (b" ", "canonical"), (b"\n\t\r", "canonical")):
            with self.subTest(image=image, loader=loader):
                concrete = run_model(image, b"", self.profile, loader=loader,
                                     max_steps=1, max_address=self.profile.end - 1)
                symbolic = sm.run_concrete(image, b"", self.profile, loader=loader,
                                          max_steps=1, max_address=self.profile.end - 1)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "probe.mb"
                    path.write_bytes(image)
                    vm = run_guest(path, b"", RunConfig(loader, 1, 5, 536870912, 8))
                self.assertEqual(symbolic["status"], concrete.status.value)
                self.assertEqual(symbolic["status"], vm.status.value)
                self.assertEqual(symbolic["steps"], concrete.steps)

    def test_one_symbolic_input_is_universally_echoed(self):
        import z3
        sm = self.api()
        x = z3.Int("symbolic_echo_input")
        inputs = z3.Store(z3.K(z3.IntSort(), 0), 0, x)
        state = sm.initial_state(b"ubO", self.profile, loader="canonical")
        for _ in range(3):
            state = sm.step(state, inputs, z3.IntVal(1), self.profile, max_address=8)
        solver = z3.Solver()
        solver.set(timeout=5000)
        solver.add(x >= 0, x <= 255,
                   z3.Or(z3.Not(state.halted), state.bounded,
                         state.output_length != 1, z3.Select(state.output, 0) != x))
        self.assertEqual(solver.check(), z3.unsat)

    def state(self, memory, *, a=1, c=0, d=1):
        import z3
        sm = self.api()
        return sm.State(memory, a, c, d, 0, z3.K(z3.IntSort(), 0), 0, 0, False, False)

    def test_arbitrary_entry_states_cover_regions_and_code_data_aliases(self):
        import z3
        from slopsynth.model import _crazy, _rotate, _dispatch_offsets, _TRANSLATION
        sm = self.api()
        offsets = _dispatch_offsets(self.profile.end)
        for region in range(3):
            c = region * (self.profile.end // 3) + 10
            for alias in (False, True):
                for opcode in (*self.profile.dispatch.values(), 0, 93):
                    d = c if alias else c + 100
                    code = (opcode - c - offsets[region]) % 94 + 94
                    memory = z3.Store(z3.K(z3.IntSort(), 0), c, code)
                    if not alias:
                        memory = z3.Store(memory, d, 42)
                    data = code if alias else 42
                    a, newc, newd, steps = 1, c, d, 0
                    expected_memory = {c: code, d: data}
                    if opcode != 81:
                        if opcode == 4:
                            newc = data
                        elif opcode == 23:
                            a = self.profile.eof_value
                        elif opcode == 40:
                            newd = data
                        elif opcode in (39, 62):
                            a = _rotate(data, self.profile.end) if opcode == 39 else _crazy(a, data, 19)
                            expected_memory[d] = a
                        current = expected_memory.get(newc, 0)
                        if current < len(_TRANSLATION):
                            expected_memory[newc] = ord(_TRANSLATION[current])
                        newc, newd, steps = (newc + 1) % self.profile.end, (newd + 1) % self.profile.end, 1
                    result = sm.step(self.state(memory, c=c, d=d), z3.K(z3.IntSort(), 0),
                                     0, self.profile, max_address=self.profile.end - 1)
                    def number(value):
                        return z3.simplify(value).as_long()
                    with self.subTest(region=region, alias=alias, opcode=opcode):
                        self.assertEqual((number(result.a), number(result.c), number(result.d),
                                          number(result.steps)), (a, newc, newd, steps))
                        for address, expected in expected_memory.items():
                            self.assertEqual(number(z3.Select(result.memory, address)), expected)

    def test_post_jump_translation_boundaries_and_destination_alias(self):
        import z3
        sm = self.api()
        for byte in (0, 134, 135, 140, 141, 255):
            memory = z3.Store(z3.Store(z3.Store(z3.K(z3.IntSort(), 0), 0, 4), 1, 7), 7, byte)
            result = sm.step(self.state(memory), z3.K(z3.IntSort(), 0), 0,
                             self.profile, max_address=8)
            expected = ord(sm.TRANSLATION[byte]) if byte < 141 else byte
            self.assertEqual(z3.simplify(z3.Select(result.memory, 7)).as_long(), expected)
            self.assertEqual(z3.simplify(z3.Select(result.memory, 0)).as_long(), 4)
        # Destination aliases D: the destination word is also the jump address.
        memory = z3.Store(z3.Store(z3.K(z3.IntSort(), 0), 0, 4), 1, 1)
        result = sm.step(self.state(memory), z3.K(z3.IntSort(), 0), 0,
                         self.profile, max_address=8)
        self.assertEqual(z3.simplify(z3.Select(result.memory, 1)).as_long(), ord(sm.TRANSLATION[1]))

    def test_fetch_data_and_post_jump_bounds_preserve_exact_partial_state(self):
        import z3
        sm = self.api()
        for c, d, opcode, target, finalc in ((9, 1, 4, 1, 9),
                                           (0, 9, 4, 1, 0),
                                           (0, 1, 4, 9, 9)):
            memory = z3.Store(z3.Store(z3.K(z3.IntSort(), 0), c, (opcode - c) % 94), d, target)
            result = sm.step(self.state(memory, c=c, d=d), z3.K(z3.IntSort(), 0), 0,
                             self.profile, max_address=8)
            self.assertTrue(z3.is_true(result.bounded))
            self.assertEqual(z3.simplify(result.c).as_long(), finalc)
            self.assertEqual(z3.simplify(result.steps).as_long(), 0)
            self.assertTrue(z3.is_true(z3.simplify(result.memory == memory)))
        # NOP ignores an invalid D; data-dependent operations do not.
        memory = z3.Store(z3.K(z3.IntSort(), 0), 0, 68)
        result = sm.step(self.state(memory, d=9), z3.K(z3.IntSort(), 0), 0,
                         self.profile, max_address=8)
        self.assertFalse(z3.is_true(result.bounded))
        self.assertEqual(z3.simplify(result.d).as_long(), 10)

    def test_word_wrap_and_stopped_state_stuttering(self):
        import z3
        from dataclasses import replace
        from slopsynth.model import _dispatch_offsets
        sm = self.api()
        end = self.profile.end
        code = (23 - (end - 1) - _dispatch_offsets(end)[2]) % 94
        memory = z3.Store(z3.K(z3.IntSort(), 0), end - 1, code)
        state = self.state(memory, c=end - 1, d=end - 1)
        result = sm.step(state, z3.K(z3.IntSort(), 0), 0, self.profile, max_address=end - 1)
        self.assertEqual(z3.simplify(result.c).as_long(), 0)
        self.assertEqual(z3.simplify(result.d).as_long(), 0)
        self.assertEqual(z3.simplify(result.a).as_long(), end - 1)
        for stopped in (replace(result, halted=z3.BoolVal(True)), replace(result, bounded=z3.BoolVal(True))):
            again = sm.step(stopped, z3.K(z3.IntSort(), 0), 0, self.profile, max_address=end - 1)
            for field in stopped.__dataclass_fields__:
                self.assertTrue(z3.is_true(z3.simplify(getattr(again, field) == getattr(stopped, field))))

    def test_h2_exceptional_and_eof_jumps_match_vm(self):
        sm = self.api()
        from slopsynth.branch import lower_branch
        from slopsynth.lang import parse_placed
        from tools.guest_runner import RunConfig, run_guest
        import tempfile
        module = parse_placed((ROOT / "examples/branch.slop").read_text()).module
        image = lower_branch(module, self.profile).image
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "branch.mb"
            path.write_bytes(image)
            for data in (b"\x00A", b"\x6cA", b"\x6dB", b""):
                result = sm.run_concrete(image, data, self.profile, loader="canonical",
                                         max_steps=128, max_address=self.profile.end - 1)
                vm = run_guest(path, data, RunConfig("canonical", 128, 5, 536870912, 8))
                self.assertEqual((result["status"], result["stdout"]), (vm.status.value, vm.stdout))


if __name__ == "__main__":
    unittest.main()
