"""Research isolation and distribution contracts (not a substitute for Go CI)."""
from pathlib import Path
import re
import unittest
from scripts.build_release import component_files

ROOT = Path(__file__).resolve().parents[1]
POC = ROOT / "extras/transport-poc"


class TransportResearchTests(unittest.TestCase):
    def test_not_in_production_package(self):
        self.assertFalse(any("transport-poc" in name for _, name in component_files()))

    def test_stdlib_only_simulation(self):
        self.assertEqual((POC / "go.mod").read_text().split(), ["module", "venta-transport-poc", "go", "1.22"])
        files = {p.name for p in POC.glob("*.go")}
        self.assertEqual(files, {"adapter.go", "migration.go", "adapter_test.go"})
        allowed = {"encoding/json", "errors", "fmt", "sync", "testing"}
        for source in POC.glob("*.go"):
            raw = source.read_text()
            for block in re.findall(r"import\s*\((.*?)\)", raw, re.S):
                self.assertTrue(set(re.findall(r'"([^"]+)"', block)) <= allowed)
            self.assertTrue(set(re.findall(r'import\s+"([^"]+)"', raw)) <= allowed)
            self.assertNotIn("package main", raw)

    def test_research_explicitly_limits_claims(self):
        research = (ROOT / "docs/TRANSPORT_RESEARCH.md").read_text()
        for value in ("NO-GO", "GPL-3.0", "Apache-2.0", "404", "not measured", "no monetary savings", "no upstream implementation"):
            self.assertIn(value.lower(), research.lower())
        self.assertIn("simulation", (POC / "README.md").read_text().lower())
