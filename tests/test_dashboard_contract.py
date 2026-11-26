"""V130-02: distribution and local-history configuration contract."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]

class DashboardContractTests(unittest.TestCase):
    def test_history_uses_only_explicit_local_ha_entities(self):
        dashboard = yaml.safe_load((ROOT / "extras/dashboard/example.yaml").read_text())
        self.assertEqual(dashboard["type"], "vertical-stack")
        card, *graphs = dashboard["cards"]
        self.assertEqual(card["type"], "custom:venta-airwasher-card")
        self.assertTrue(all(graph["type"] == "history-graph" and graph["hours_to_show"] == 24 for graph in graphs))
        history = {entity for graph in graphs for entity in graph["entities"]}
        self.assertEqual(history, {card[role] for role in ("humidity", "temperature", "pm25", "fan", "water_level")})

    def test_browser_fixture_and_ci_are_mandatory_on_github(self):
        fixture = (ROOT / "tests/dashboard_browser.html").read_text()
        self.assertIn('data-result="PENDING"', fixture)
        self.assertIn('dataset.result="PASS"', fixture)
        self.assertIn("320px mobile", fixture)
        self.assertIn("700px desktop", fixture)
        workflow = yaml.safe_load((ROOT / ".github/workflows/validate.yml").read_text())
        steps = workflow["jobs"]["tests"]["steps"]
        browser = next(step for step in steps if step["name"] == "Exercise dashboard in real Chromium")
        self.assertNotIn("continue-on-error", browser)
        self.assertIn("dmitriy1ebedev/venta-aw730-homeassistant", browser["if"])
        self.assertIn("dashboard_browser.html", browser["run"])
        self.assertIn('data-result="PASS"', browser["run"])
        self.assertIn("google-chrome", browser["run"])

    def test_real_ha_frontend_gate_keeps_fixture_isolated(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/validate.yml").read_text())
        step = next(s for s in workflow["jobs"]["ha_runtime_smoke"]["steps"] if s.get("name") == "Exercise real Lovelace and local recorder in isolated HA")
        self.assertNotIn("continue-on-error", step)
        for guard in ("--network none", "--cap-drop ALL", "--security-opt no-new-privileges", "--pids-limit", "/source:ro", "ha_dashboard_frontend_smoke.py client", "docker rm -f"):
            self.assertIn(guard, step["run"])
        fixture = (ROOT / "scripts/ha_dashboard_frontend_smoke.py").read_text()
        for check in ("ThreadingUnixStreamServer", "127.0.0.1", "REAL_LOVELACE_BROWSER_PASS", "state-history-charts", "isLoadingData", "has_touch=mobile", "route_web_socket", "real local recorder fan state timeline"):
            self.assertIn(check, fixture)

if __name__ == "__main__":
    unittest.main()
