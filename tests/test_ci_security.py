"""CI security contract: prevent silent loss of release protections."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class CISecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.safe_load((ROOT / ".github/workflows/validate.yml").read_text())

    def test_read_only_action_token_and_credential_free_checkout(self):
        workflow = self.workflow
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        checkout_steps = []
        for job in workflow["jobs"].values():
            for step in job["steps"]:
                uses = step.get("uses")
                if uses:
                    self.assertRegex(uses, r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*@[0-9a-f]{40}$")
                    if uses.startswith("actions/checkout@"):
                        checkout_steps.append(step)
        self.assertGreaterEqual(len(checkout_steps), 4)
        for checkout in checkout_steps:
            self.assertIs(checkout["with"]["persist-credentials"], False)

    def test_all_expected_gates_are_present(self):
        jobs = self.workflow["jobs"]
        self.assertTrue({"tests", "hacs", "hassfest", "ha_runtime_smoke"}.issubset(jobs))
        scripts = "\n".join(step.get("run", "") for step in jobs["tests"]["steps"])
        for required in (
            "compileall", "unittest discover", "scripts/check_repository.py",
            "scripts/check_publication_security.py",
            "venta-airwasher-card.js", "venta-more-info.js",
        ):
            self.assertIn(required, scripts)
        for gate in ("hacs", "hassfest", "ha_runtime_smoke"):
            self.assertIn("dmitriy1ebedev/venta-aw730-homeassistant", jobs[gate]["if"])
        smoke = "\\n".join(s.get("run", "") for s in jobs["ha_runtime_smoke"]["steps"])
        for required in ("scripts/build_release.py", "scripts.stage_ha_runtime", "scripts/ha_native_homekit_smoke.py", "scripts/ha_homekit_identity_smoke.py", "scripts/ha_entity_registry_smoke.py", "ghcr.io/home-assistant/home-assistant:2026.11.1", "--network none", "check_config --config /config", "--ha-version 2026.11.1"):
            self.assertIn(required, smoke)

    def test_current_stable_and_beta_smoke_are_mandatory_and_isolated(self):
        job = self.workflow["jobs"]["ha_current_channel_smoke"]
        self.assertFalse(job["strategy"]["fail-fast"])
        self.assertNotIn("continue-on-error", job)
        self.assertEqual(job["strategy"]["matrix"]["include"], [
            {"ha_version": "2026.11.3", "image": "ghcr.io/home-assistant/home-assistant:2026.11.3"},
            {"ha_version": "2026.12.0b0", "image": "ghcr.io/home-assistant/generic-x86-64-homeassistant:2026.12.0b0"},
        ])
        commands = [step["run"] for step in job["steps"] if "run" in step]
        for command in commands:
            if "docker run" in command:
                for guard in ("--network none", "--cap-drop ALL", "--security-opt no-new-privileges", '"$HA_IMAGE"'):
                    self.assertIn(guard, command)
                self.assertNotIn("--privileged", command)
        upstream = next(step for step in job["steps"] if step.get("with", {}).get("repository") == "xZetsubou/hass-localtuya")
        self.assertEqual(upstream["with"]["ref"], "7f3be1999f581863ffa984e86ed359857f8bcab1")
        self.assertIs(upstream["with"]["persist-credentials"], False)
        real = next(command for command in commands if "real imports and synthetic DP selectors" in command)
        for required in ("--network none", "ci-localtuya-upstream:/upstream:ro", "manifest", "2026.10.0", "importlib.import_module", "flow.col_to_select", "issubclass"):
            self.assertIn(required, real)
        smoke = "\n".join(commands)
        for required in ("check_config", "ha_native_homekit_smoke.py", "ha_homekit_identity_smoke.py", "ha_config_flow_smoke.py", "ha_config_entry_setup_smoke.py", "ha_entity_registry_smoke.py", "ha_isolated_boot_smoke.py", "--phase restore"):
            self.assertIn(required, smoke)

    def test_topic_exception_is_explicit_and_documented(self):
        hacs = self.workflow["jobs"]["hacs"]
        validations = [step for step in hacs["steps"] if step.get("uses", "").startswith("hacs/action@")]
        self.assertEqual(len(validations), 1)
        self.assertEqual(validations[0]["with"].get("ignore"), "topics")
        review = (ROOT / "docs/CI_SECURITY.md").read_text()
        self.assertIn("ignore: topics", review)
        self.assertIn("GitVerse", review)
        self.assertIn("not compliance", review)

    def test_security_policy_and_attribution(self):
        self.assertIn("MIT", (ROOT / "LICENSE").read_text())
        notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text()
        self.assertIn("Shinz2711", notice)
        self.assertIn("MIT", notice)
        ignore = (ROOT / ".gitignore").read_text()
        for forbidden in (".storage/", "secrets.yaml", ".env", "*.pem", "*.key"):
            self.assertIn(forbidden, ignore)
        self.assertIn("sync_managed_template", (ROOT / "AGENTS.md").read_text())


if __name__ == "__main__":
    unittest.main()
