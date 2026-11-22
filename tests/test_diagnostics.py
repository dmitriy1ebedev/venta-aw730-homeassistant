"""P02.3 diagnostics: no secrets, safe reconnect recovery, no device writes."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "venta_homekit_native"
SPEC = importlib.util.spec_from_file_location(
    "venta_privacy_safe_diagnostics", COMPONENT / "diagnostics.py"
)
assert SPEC and SPEC.loader
diag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diag)

ENTITY_IDS = {
    "humidifier": "humidifier.fixture_venta",
    "fan": "select.fixture_fan",
    "led": "switch.fixture_led",
    "brightness": "select.fixture_brightness",
    "temperature": "sensor.fixture_temperature",
    "humidity": "sensor.fixture_humidity",
}
PRIVATE = ("local_key=MY_SECRET_123", "192.168.47.80", "aa:bb:cc:dd:ee:ff", "pairing-pin=111-22-333", "fixture_venta", "fixture_fan", "fixture_bridge_private_id")


class FakeEntries:
    def __init__(self):
        self.localtuya = [SimpleNamespace(state=SimpleNamespace(value="loaded"))]
        self.bridge = SimpleNamespace(runtime_data=SimpleNamespace(homekit=SimpleNamespace(
            status="running", driver=object(), bridge=object()
        )))

    def async_entries(self, domain):
        return self.localtuya if domain == "localtuya" else []

    def async_get_entry(self, value):
        return self.bridge if value == "fixture_bridge_private_id" else None


class DiagnosticsContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        localtuya = self.root / "custom_components" / "localtuya"
        localtuya.mkdir(parents=True)
        (localtuya / "manifest.json").write_text(
            json.dumps({"version": "2026.10.0", "local_key": "MY_SECRET_123"})
        )
        self.states = {name: SimpleNamespace(
            state="off" if k == "humidifier" else "12",
            attributes={"local_key": "MY_SECRET_123", "ip": "192.168.47.80"},
        ) for k, name in ENTITY_IDS.items()}
        self.hass = SimpleNamespace(
            states=self.states, config=SimpleNamespace(config_dir=str(self.root)),
            config_entries=FakeEntries(), services=SimpleNamespace(async_call=self._no_calls),
        )
        self.calls = 0

    def _no_calls(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("Diagnostic must not invoke a Home Assistant service")

    def collect(self, entity_ids=None, bridge="fixture_bridge_private_id"):
        return diag.collect_diagnostics(
            self.hass,
            entity_ids=dict(ENTITY_IDS if entity_ids is None else entity_ids),
            bridge_entry_id=bridge,
            home_assistant_version="2026.11.1",
            integration_dir=COMPONENT,
        )

    def assert_redacted(self, report):
        payload = json.dumps(report, sort_keys=True)
        for private in PRIVATE:
            self.assertNotIn(private, payload)
        self.assertFalse(any(k in payload for k in ('"ip"', '"device_id"', '"local_key"', '"entity_id"', '"pairing"')))
        self.assertEqual(self.calls, 0)

    def test_healthy_baseline_includes_only_allowlisted_versions_and_status(self):
        report = self.collect()
        self.assertEqual(report["schema"], 1)
        self.assertEqual(report["integration_version"], "1.0.4")
        self.assertEqual(report["home_assistant_version"], "2026.11.1")
        self.assertEqual(report["localtuya_version"], "2026.10.0")
        self.assertEqual(report["configuration"], "complete")
        self.assertEqual(report["localtuya"], "loaded")
        self.assertEqual(report["humidifier"], "off")
        self.assertEqual(report["homekit_bridge"], "ready")
        self.assertEqual(report["recommendation"], "none")
        self.assertEqual(set(report["linked_entities"]), {"fan", "led", "brightness", "temperature", "humidity"})
        self.assert_redacted(report)

    def test_localtuya_not_configured_is_not_mislabeled_not_installed(self):
        self.hass.config_entries.localtuya = []
        report = self.collect()
        self.assertEqual(report["localtuya"], "not_configured")
        self.assertEqual(report["recommendation"], "check_localtuya_configuration")
        self.assert_redacted(report)

    def test_localtuya_configured_but_not_loaded(self):
        self.hass.config_entries.localtuya = [SimpleNamespace(state="setup_error")]
        report = self.collect()
        self.assertEqual(report["localtuya"], "not_loaded")
        self.assertEqual(report["recommendation"], "check_localtuya_load_state")
        self.assert_redacted(report)

    def test_unknown_localtuya_api_and_corrupt_manifest_are_safe(self):
        self.hass.config_entries.async_entries = None
        manifest = self.root / "custom_components/localtuya/manifest.json"
        manifest.write_text("invalid JSON")
        report = self.collect()
        self.assertEqual(report["localtuya"], "unknown")
        self.assertEqual(report["localtuya_version"], "unknown")
        self.assert_redacted(report)

    def test_missing_configuration_has_no_raw_entity_ids(self):
        broken = dict(ENTITY_IDS)
        broken["humidity"] = None
        report = self.collect(broken, bridge=None)
        self.assertEqual(report["configuration"], "incomplete")
        self.assertEqual(report["linked_entities"]["humidity"], "not_configured")
        self.assertEqual(report["recommendation"], "review_venta_configuration")
        self.assert_redacted(report)

    def test_unavailable_and_unknown_prefer_connection_log_recommendation(self):
        for state in ("unavailable", "unknown"):
            self.states[ENTITY_IDS["humidifier"]].state = state
            report = self.collect()
            self.assertEqual(report["humidifier"], state)
            self.assertEqual(report["recommendation"], "check_localtuya_connection_logs")
            self.assertEqual(report["protocol_error"], "not_available_from_entity_state")
            self.assert_redacted(report)

    def test_missing_humidifier_and_linked_sensor(self):
        self.states.pop(ENTITY_IDS["humidifier"])
        report = self.collect()
        self.assertEqual(report["humidifier"], "missing")
        self.assertEqual(report["recommendation"], "check_localtuya_connection_logs")
        self.assert_redacted(report)
        self.states[ENTITY_IDS["humidifier"]] = SimpleNamespace(state="on", attributes={})
        self.states.pop(ENTITY_IDS["temperature"])
        report = self.collect()
        self.assertEqual(report["linked_entities"]["temperature"], "missing")
        self.assertEqual(report["recommendation"], "check_missing_linked_entities")
        self.assert_redacted(report)

    def test_homekit_not_ready_and_missing_entry(self):
        self.hass.config_entries.bridge.runtime_data.homekit.driver = None
        report = self.collect()
        self.assertEqual(report["homekit_bridge"], "not_ready")
        self.assertEqual(report["recommendation"], "check_existing_homekit_bridge")
        self.assert_redacted(report)
        report = self.collect(bridge="unmapped_bridge_private_id")
        self.assertEqual(report["homekit_bridge"], "not_found")
        self.assert_redacted(report)

    def test_restart_then_reconnect_does_not_change_device_state(self):
        self.hass.config_entries.bridge.runtime_data.homekit = None
        self.states[ENTITY_IDS["humidifier"]].state = "unavailable"
        first = self.collect()
        self.assertEqual(first["homekit_bridge"], "not_ready")
        self.assertEqual(first["humidifier"], "unavailable")
        self.assertEqual(first["recommendation"], "check_localtuya_connection_logs")
        self.hass.config_entries.bridge.runtime_data.homekit = SimpleNamespace(
            status="running", driver=object(), bridge=object()
        )
        self.states[ENTITY_IDS["humidifier"]].state = "off"
        recovered = self.collect()
        self.assertEqual(recovered["homekit_bridge"], "ready")
        self.assertEqual(recovered["humidifier"], "off")
        self.assertEqual(recovered["recommendation"], "none")
        self.assert_redacted(first)
        self.assert_redacted(recovered)

    def test_malicious_manifest_version_is_never_echoed(self):
        manifest = self.root / "custom_components/localtuya/manifest.json"
        for fake_version in ("2026.10.0 token=MY_SECRET_123", "2026.10.0+TOKEN123", "2026.10.0b1"):
            manifest.write_text(json.dumps({"version": fake_version}))
            report = self.collect()
            self.assertEqual(report["localtuya_version"], "unknown")
            self.assertNotIn(fake_version, json.dumps(report))
            self.assert_redacted(report)

    def test_log_diagnostics_service_is_declared_read_only(self):
        services = (COMPONENT / "services.yaml").read_text()
        self.assertIn("log_diagnostics:", services)
        self.assertIn("read-only", services)
        init = (COMPONENT / "__init__.py").read_text()
        self.assertIn('hass.services.async_register(DOMAIN, "log_diagnostics", log_diagnostics)', init)
        self.assertIn("collect_diagnostics(", init)
        self.assertNotIn("local_key", json.dumps(self.collect()))


if __name__ == "__main__":
    unittest.main()
