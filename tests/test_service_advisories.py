import importlib.util
import sys
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "custom_components/venta_homekit_native/service_advisories.py"
spec = importlib.util.spec_from_file_location("venta_service_advisories", path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

class AdvisoryTests(unittest.TestCase):
    def test_two_low_samples(self):
        self.assertEqual(module.classify_service_state({"water_level": 8}, {"water_level": 20}, available=True), ())
        self.assertEqual(module.classify_service_state({"water_level": 8}, {"water_level": 9}, available=True)[0].kind, "check_water_level")
    def test_missing_and_reconnect(self):
        self.assertEqual(module.classify_service_state({}, {}, available=False)[0].kind, "device_unavailable")
        self.assertEqual(module.classify_service_state({"water_level": 0}, {"water_level": 0}, available=True, previous_available=False), ())
    def test_invalid(self):
        for v in (-1, 101, float("nan"), float("inf"), "0", True, None):
            self.assertEqual(module.classify_service_state({"water_level": v}, {"water_level": 0}, available=True), ())
    def test_counter_inspection(self):
        values = {"filter_days": 0, "cleaning_days": 0, "service_days": 0}
        result = module.classify_service_state(values, values, available=True)
        self.assertEqual(len(result), 3)
        self.assertTrue(all(x.severity == "info" for x in result))
    def test_safe_home_assistant_sample(self):
        from types import SimpleNamespace
        states = {
            "sensor.private_water": SimpleNamespace(state="8", attributes={"local_key": "secret"}),
            "sensor.private_filter": SimpleNamespace(state="unavailable"),
            "sensor.private_cleaning": SimpleNamespace(state="0"),
            "sensor.private_service": SimpleNamespace(state="nan"),
        }
        mapping = {
            "water_level": "sensor.private_water",
            "filter_days": "sensor.private_filter",
            "cleaning_days": "sensor.private_cleaning",
            "service_days": "sensor.private_service",
        }
        sample = module.sample_service_states(states, mapping)
        self.assertEqual(sample, {
            "water_level": 8.0, "filter_days": None,
            "cleaning_days": 0.0, "service_days": None,
        })
        self.assertNotIn("private", str(sample))
        self.assertNotIn("secret", str(sample))

    def test_notification_dedup_and_recovery(self):
        from types import SimpleNamespace
        calls = []
        states = {
            "humidifier.venta": SimpleNamespace(state="on"),
            "sensor.water": SimpleNamespace(state="8"),
        }
        class FakeServices:
            async def async_call(self, domain, action, data):
                calls.append((domain, action, data))
        class FakeHass:
            services = FakeServices()
            def __init__(self):
                self.states = states
            def async_create_task(self, coro):
                import asyncio
                asyncio.run(coro)
        monitor = module.ServiceAdvisoryMonitor(
            FakeHass(), "humidifier.venta", {"water_level": "sensor.water"}
        )
        monitor.update()
        self.assertEqual(calls, [])
        monitor.update()
        self.assertEqual([x[1] for x in calls], ["create"])
        monitor.update()
        self.assertEqual(len(calls), 1)
        states["sensor.water"].state = "80"
        monitor.update()
        self.assertEqual([x[1] for x in calls], ["create", "dismiss"])
        self.assertTrue(all(x[0] == "persistent_notification" for x in calls))
        self.assertTrue(all("local_key" not in str(x) for x in calls))

    def test_no_first_sample_alarm(self):
        self.assertEqual(module.classify_service_state({"water_level": 0}, None, available=True), ())
