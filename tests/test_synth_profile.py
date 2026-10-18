from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from slopsynth.profile import load_profile


ROOT = Path(__file__).resolve().parents[1]


class SynthesisProfileTests(unittest.TestCase):
    def test_profile_has_fixed_3_19_constants(self) -> None:
        profile = load_profile(ROOT / "profiles" / "fixed19.json")

        self.assertEqual(profile.name, "fixed-3^19")
        self.assertEqual(profile.trits, 19)
        self.assertEqual(profile.end, 1_162_261_467)
        self.assertEqual(profile.eof_value, profile.end - 1)
        self.assertEqual(
            dict(profile.dispatch),
            {
                "jump": 4,
                "output": 5,
                "input": 23,
                "rotate": 39,
                "move": 40,
                "crazy": 62,
                "nop": 68,
                "halt": 81,
            },
        )

    def test_loader_contracts_diverge_on_whitespace(self) -> None:
        profile = load_profile(ROOT / "profiles" / "fixed19.json")

        self.assertFalse(profile.loaders["raw"].skip_whitespace)
        self.assertTrue(profile.loaders["raw"].whitespace_is_cell)
        self.assertTrue(profile.loaders["canonical"].skip_whitespace)
        self.assertFalse(profile.loaders["canonical"].whitespace_is_cell)
        self.assertEqual(profile.loaders["canonical"].position_cycle, 564)

    def test_profile_rejects_unknown_dispatch_indices(self) -> None:
        profile_data = json.loads(
            (ROOT / "profiles" / "fixed19.json").read_text(encoding="utf-8")
        )
        profile_data["dispatch"]["halt"] = 94

        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / "invalid-profile.json"
            candidate.write_text(json.dumps(profile_data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "dispatch"):
                load_profile(candidate)


if __name__ == "__main__":
    unittest.main()
