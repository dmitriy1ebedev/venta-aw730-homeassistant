"""Fail-closed export policy regression tests."""
import importlib.util
import pathlib
from types import SimpleNamespace
import unittest

path = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "venta_homekit_native" / "export_guard.py"
spec = importlib.util.spec_from_file_location("venta_export_guard_test", path)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class ExplicitFilterTests(unittest.TestCase):
    def setUp(self):
        rows = {
            "humidifier.original": SimpleNamespace(platform="localtuya"),
            "humidifier.venta": SimpleNamespace(platform=guard.DOMAIN),
        }
        self.registry = SimpleNamespace(async_get=rows.get)

    def test_existing_source_only(self):
        self.assertTrue(guard._explicit_filter(
            {"include_entities": ["humidifier.original"]}, self.registry))

    def test_broad_filter_rejected(self):
        for config in ({}, {"include_domains": ["humidifier"]},
                       {"include_entities": ["humidifier.original"],
                        "include_entity_globs": ["fan.*"]}):
            self.assertFalse(guard._explicit_filter(config, self.registry))

    def test_disjoint_domain_allowed_without_widening_venta_exports(self):
        self.assertTrue(guard._explicit_filter(
            {"include_entities": ["humidifier.original"], "include_domains": ["climate"]},
            self.registry))
        self.assertTrue(guard._explicit_filter({"include_domains": ["climate"]}, self.registry))
        for domain in guard.PROJECTION_DOMAINS:
            self.assertFalse(guard._explicit_filter(
                {"include_domains": ["climate", domain]}, self.registry))
        self.assertFalse(guard._explicit_filter(
            {"include_domains": ["climate"], "include_entities": ["switch.stale"]}, self.registry))

    def test_missing_and_native_entity_rejected(self):
        for entity in ("humidifier.venta", "humidifier.missing"):
            self.assertFalse(guard._explicit_filter(
                {"include_entities": [entity]}, self.registry))

    def test_unknown_filter_rejected(self):
        self.assertFalse(guard._explicit_filter(
            {"include_entities": ["humidifier.original"], "unknown": True},
            self.registry))

    def test_invalid_filter_types_rejected(self):
        for key, value in (("include_domains", False), ("exclude_entities", "sensor.test"),
                           ("exclude_entity_globs", [None]), ("exclude_domains", {})):
            with self.subTest(key=key):
                self.assertFalse(guard._explicit_filter(
                    {"include_entities": ["humidifier.original"], key: value}, self.registry))
