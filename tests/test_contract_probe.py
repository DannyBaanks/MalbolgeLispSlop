"""Reference probes preserve bytes and cannot overwrite previous evidence."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ContractProbeTests(unittest.TestCase):
    def test_probe_captures_guest_bytes_identity_and_limits(self):
        try:
            from tools.probe_language_contract import capture_probe
        except ImportError:
            self.fail("contract probe recorder does not exist")
        from tools.guest_runner import RunConfig
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            image = base / "echo.mb"
            image.write_bytes(b"ubO")
            target = base / "evidence"
            result = capture_probe(image, b"\xff", target,
                                   RunConfig("canonical", 8, 5, 536870912, 8),
                                   engine=ROOT / "build/bolge19", label="echo control")
            self.assertEqual(result["status"], "HALT")
            self.assertEqual((target / "stdout.bin").read_bytes(), b"\xff")
            request = json.loads((target / "request.json").read_text())
            self.assertEqual(request["config"]["max_steps"], 8)
            self.assertEqual(request["image_sha256"], hashlib.sha256(b"ubO").hexdigest())
            for name, digest in json.loads((target / "hashes.json").read_text()).items():
                self.assertEqual(hashlib.sha256((target / name).read_bytes()).hexdigest(), digest)
            before = {p.name: p.read_bytes() for p in target.iterdir()}
            with self.assertRaises(FileExistsError):
                capture_probe(image, b"A", target,
                              RunConfig("canonical", 8, 5, 536870912, 8),
                              engine=ROOT / "build/bolge19", label="repeat")
            self.assertEqual(before, {p.name: p.read_bytes() for p in target.iterdir()})


if __name__ == "__main__":
    unittest.main()
