"""End-to-end regressions for the October 20 audit."""
import hashlib
import json
import unittest

from guest_ir.lisp.repl import LispSession, repl_step
from guest_ir.lisp.reader import parse_lisp_tokens
from guest_ir.lisp.builtins_numeric import apply_numeric
from guest_ir.lisp.state_image import export_state_image, import_state_image


class AuditRegressions(unittest.TestCase):
    def evaluate(self, source):
        return repl_step(source, LispSession())[0].strip()

    def test_modular_arithmetic_through_repl(self):
        for source, expected in [
            (b"(+ 67108863 1)", b"0"), (b"(- 0 1)", b"67108863"),
            (b"(* 67108863 2)", b"67108862"),
            (b"(+' 67108863 1)", b"0"), (b"(-' 0 1)", b"67108863"),
        ]:
            with self.subTest(source=source):
                self.assertEqual(self.evaluate(source), expected)
        self.assertEqual(apply_numeric("+'", [67108863, 1]), 0)
        self.assertEqual(apply_numeric("-'", [0, 1]), 67108863)

    def test_connected_builtins(self):
        for source, expected in [
            (b"(/ 8 2)", b"4"),
            (b"(map (lambda (x) (+ x 1)) '(1 2))", b"(2 3)"),
            (b"(fold + 0 '(1 2 3))", b"6"),
            (b"(append' '(1 2) 3)", b"(1 2 3)"),
            (b"((atop (bind + 1) (bind * 2)) 3)", b"7"),
            (b"((bind' - 2) 7)", b"5"),
            (b"((monad (+ x 1)) 4)", b"5"),
            (b"((dyad (+ x y)) 4 5)", b"9"),
        ]:
            with self.subTest(source=source):
                self.assertEqual(self.evaluate(source), expected)

    def test_apostrophe_in_identifier_and_quote(self):
        self.assertEqual(parse_lisp_tokens(b"(+' 1 2)"), ["(", "+'", "1", "2", ")"])
        self.assertEqual(self.evaluate(b"'(a b)"), b"(a b)")
        self.assertEqual(self.evaluate(b"(fold' + 0 '(1 2))"), b"3")

    def test_rejects_malformed_forms_before_evaluation(self):
        for source in [b"(+ 1 2", b"(+ 1 2])", b"'", b")", b"(+ 1 2) (+ 3 4)"]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.evaluate(source)
        for source in [b"(+ 1)", b"(+ 1 2 3)"]:
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "arity"):
                self.evaluate(source)

    def test_advertises_only_registered_features(self):
        features = repl_step(b".F", LispSession())[0].split()
        self.assertIn(b"map", features)
        self.assertIn(b"bind'", features)
        self.assertNotIn(b"defmacro", features)
        self.assertNotIn(b"lazy", features)

    def test_state_roundtrip_preserves_closures_and_recursion(self):
        original = LispSession()
        repl_step(b"(def inc (let ((n 2)) (lambda (x) (+ x n))))", original)
        repl_step(b"(defun fact (n) (if (= n 0) 1 (* n (fact (- n 1)))))", original)
        repl_step(b"(def pair (cons 1 2))", original)
        restored = LispSession()
        restored.env.define("stale", 99)
        self.assertTrue(import_state_image(export_state_image(original), restored))
        self.assertNotIn("stale", restored.env.bindings)
        self.assertEqual(repl_step(b"(inc 3)", restored)[0], b"5\n")
        self.assertEqual(repl_step(b"(fact 5)", restored)[0], b"120\n")
        self.assertEqual(repl_step(b"pair", restored)[0], b"(1 . 2)\n")

    def test_unsupported_state_fails_explicitly(self):
        session = LispSession()
        session.env.define("opaque", object())
        with self.assertRaises(ValueError):
            export_state_image(session)
        session.env.bindings["opaque"] = [object()]
        with self.assertRaises(ValueError):
            export_state_image(session)

    def test_failed_import_is_atomic(self):
        session = LispSession()
        session.env.define("keep", 42)
        before = export_state_image(session)
        payload = json.dumps({"heap_words": 123, "bindings": []}).encode()
        blob = b"LISP" + (1).to_bytes(2, "little") + len(payload).to_bytes(4, "little") + payload + hashlib.sha256(payload).digest()
        self.assertFalse(import_state_image(blob, session))
        self.assertEqual(export_state_image(session), before)
