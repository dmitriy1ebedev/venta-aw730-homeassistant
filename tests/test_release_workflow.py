"""One-shot GitHub release contract: no PR-triggered publishing or tag rewrite."""
from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/publish-v1-2-0.yml"


class OneShotReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        cls.job = cls.workflow["jobs"]["publish"]
        cls.commands = "\n".join(
            step.get("run", "") for step in cls.job["steps"]
        )

    def test_only_successful_main_push_can_release(self) -> None:
        trigger = self.workflow.get("on", self.workflow.get(True))
        self.assertEqual(trigger["workflow_run"]["types"], ["completed"])
        self.assertEqual(trigger["workflow_run"]["branches"], ["main"])
        self.assertEqual(
            trigger["workflow_run"]["workflows"], ["Validate Venta AW730"]
        )
        guard = self.job["if"]
        for required in (
            "workflow_run.conclusion == 'success'",
            "workflow_run.event == 'push'",
            "workflow_run.head_branch == 'main'",
            "workflow_run.head_repository.full_name == github.repository",
        ):
            self.assertIn(required, guard)

    def test_credential_and_tag_permissions_are_bounded(self) -> None:
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        self.assertEqual(self.job["permissions"], {"contents": "write"})
        self.assertFalse(self.workflow["concurrency"]["cancel-in-progress"])
        self.assertIn("persist-credentials", str(self.job["steps"][0]["with"]))
        self.assertIs(self.job["steps"][0]["with"]["persist-credentials"], False)
        for required in (
            'test "$(git rev-parse HEAD)" = "$CI_SHA"',
            'test "$current_main" = "$CI_SHA"',
            "git/ref/tags/v1.2.0",
            "Tag exists at a different object; refusing retag",
            "--verify-tag",
            "gh release create v1.2.0",
        ):
            self.assertIn(required, self.commands)
        self.assertNotIn("git push --force", self.commands)
        self.assertNotIn("gh release delete", self.commands)

    def test_published_bytes_and_offline_install_are_verified(self) -> None:
        for required in (
            "scripts/check_publication_security.py",
            "--expected-tag v1.2.0",
            "SHA256SUMS.txt",
            "provenance.txt",
            "gh release download v1.2.0",
            "sha256sum --check",
            "scripts.stage_ha_runtime",
            "--network none",
            "ghcr.io/home-assistant/home-assistant:2026.11.2",
        ):
            with self.subTest(required=required):
                self.assertIn(required, self.commands)
        for forbidden in ("docker restart homeassistant", "/config/.storage", "local_key"):
            self.assertNotIn(forbidden, self.commands)

    def test_public_notes_describe_real_limits_and_rollback(self) -> None:
        notes = (ROOT / "docs/RELEASE_NOTES_1_2_0.md").read_text(encoding="utf-8")
        for required in ("AW730", "2026.11.1", "2026.11.2", "rollback",
                         "No automatic YAML-to-UI migration", "SHA-256"):
            self.assertIn(required, notes)


if __name__ == "__main__":
    unittest.main()
