"""Repairs flow safety tests: synthetic HA only, no bridge or device I/O."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_config_flow as flow_fixture

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "venta_homekit_native"


class FakeRepairsFlow:
    def async_abort(self, *, reason):
        return {"type": "abort", "reason": reason}

    def async_show_form(self, *, step_id, data_schema, errors=None):
        return {
            "type": "form", "step_id": step_id,
            "schema": data_schema, "errors": errors or {},
        }

    def async_create_entry(self, *, title, data):
        return {"type": "create_entry", "title": title, "data": data}


class VentaRepairTests(unittest.TestCase):
    def setUp(self):
        self.fixture = flow_fixture.VentaFlowTests(
            methodName="test_start_offers_existing_device_and_bridge"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        pkgname = self.fixture.module.__package__
        components = types.ModuleType("homeassistant.components")
        components.__path__ = []
        repairs_base = types.ModuleType("homeassistant.components.repairs")
        repairs_base.RepairsFlow = FakeRepairsFlow
        mocked = patch.dict(sys.modules, {
            "homeassistant.components": components,
            "homeassistant.components.repairs": repairs_base,
        })
        mocked.start()
        self.addCleanup(mocked.stop)
        spec = importlib.util.spec_from_file_location(
            pkgname + ".repairs",
            ROOT / "custom_components/venta_homekit_native/repairs.py",
        )
        assert spec and spec.loader
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

        self.entry = SimpleNamespace(
            entry_id="synthetic-venta-entry", domain=DOMAIN,
            data={
                "humidifier_entity": "humidifier.venta_fixture",
                "bridge_entry_id": "existing-bridge",
                "bridge_title": "Existing HomeKit Bridge",
                "confirmed_unclassified": [],
                **self.fixture.mapping,
            },
        )
        self.hass = self.fixture.hass
        self.hass.config_entries.async_get_entry = lambda item: (
            self.entry if item == self.entry.entry_id else None
        )
        self.flow = self.module.VentaBindingRepairFlow(self.entry.entry_id)
        self.flow.hass = self.hass

    def run_flow(self, coro):
        return asyncio.run(coro)

    def test_factory_rejects_issue_without_matching_entry_id(self):
        for issue, data in (
            ("other_issue", {"entry_id": self.entry.entry_id}),
            ("binding_fake", {"entry_id": self.entry.entry_id}),
            ("binding_" + self.entry.entry_id, None),
        ):
            with self.subTest(issue=issue), self.assertRaises(ValueError):
                self.run_flow(self.module.async_create_fix_flow(
                    self.hass, issue, data,
                ))

    def test_factory_accepts_registered_issue(self):
        repaired = self.run_flow(self.module.async_create_fix_flow(
            self.hass,
            "binding_" + self.entry.entry_id,
            {"entry_id": self.entry.entry_id},
        ))
        self.assertIsInstance(repaired, FakeRepairsFlow)

    def test_live_mapping_verified_before_issue_can_close(self):
        review = self.run_flow(self.flow.async_step_init())
        self.assertEqual(review["step_id"], "init")
        self.assertEqual(review["errors"], {})
        incomplete = self.run_flow(self.flow.async_step_init({
            "confirm_review": False,
        }))
        self.assertEqual(
            incomplete["errors"]["base"], "review_confirmation_required"
        )
        complete = self.run_flow(self.flow.async_step_init({
            "confirm_review": True,
        }))
        self.assertEqual(complete["type"], "create_entry")
        self.assertEqual(complete["data"], {})
        self.assertEqual(self.entry.data["led_entity"], "switch.led_power")

    def test_missing_led_blocks_repair_completion(self):
        self.hass.registry.entities.pop("switch.led_power")
        result = self.run_flow(self.flow.async_step_init({
            "confirm_review": True,
        }))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"]["base"], "binding_not_restored")

    def test_changed_device_ownership_blocks_repair(self):
        self.hass.registry.entities["switch.led_power"].device_id = "other-device"
        r = self.run_flow(self.flow.async_step_init({
            "confirm_review": True,
        }))
        self.assertEqual(r["errors"]["base"], "binding_not_restored")

    def test_missing_homekit_bridge_blocks_repair(self):
        self.fixture.bridges.clear()
        r = self.run_flow(self.flow.async_step_init({
            "confirm_review": True,
        }))
        self.assertEqual(r["errors"]["base"], "binding_not_restored")

    def test_excluded_bridge_blocks_repair(self):
        self.fixture.bridges[0].options["filter"]["include_entities"] = ["light.other"]
        r = self.run_flow(self.flow.async_step_init({
            "confirm_review": True,
        }))
        self.assertEqual(r["errors"]["base"], "binding_not_restored")

    def test_yaml_owner_prevents_repairs_flow(self):
        self.hass.data[DOMAIN] = {"patched": True}
        self.assertEqual(
            self.run_flow(self.flow.async_step_init())["reason"],
            "yaml_or_other_owner",
        )

    def test_missing_or_other_domain_entry_rejected(self):
        self.entry.domain = "another_integration"
        self.assertEqual(
            self.run_flow(self.flow.async_step_init())["reason"],
            "entry_missing",
        )
        self.entry.domain = DOMAIN
        self.hass.config_entries.async_get_entry = lambda _id: None
        self.assertEqual(
            self.run_flow(self.flow.async_step_init())["reason"],
            "entry_missing",
        )


if __name__ == "__main__":
    unittest.main()
