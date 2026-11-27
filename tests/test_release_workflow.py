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
            "workflow_run.head_sha == '49d0c64e4a20421c16729b393fb82cb62de1490f'",
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
        self.assertIn('if ref_sha="$(gh api', self.commands)
        self.assertNotIn('2>/dev/null || true', self.commands)
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

class V130ReleaseWorkflowTests(unittest.TestCase):
    def test_release_requires_all_seven_successful_main_jobs_and_fixed_version(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/publish-v1-3-0.yml").read_text())
        job = workflow["jobs"]["publish"]
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(job["permissions"], {"contents": "write", "actions": "read"})
        self.assertNotIn("GH_TOKEN", job["env"])
        self.assertIs(job["steps"][0]["with"]["persist-credentials"], False)
        for required in ("workflow_run.conclusion == 'success'", "workflow_run.event == 'push'",
                         "workflow_run.head_branch == 'main'", "workflow_run.head_repository.full_name == github.repository",
                         "github.repository == 'dmitriy1ebedev/venta-aw730-homeassistant'"):
            self.assertIn(required, job["if"])
        commands = "\n".join(step.get("run", "") for step in job["steps"])
        for required in ("actions/runs/$CI_RUN/jobs", "jobs['total_count']", "j['conclusion'] == 'success'",
                         "run['head_sha'] == os.environ['CI_SHA']", "assert version == \"1.3.0\"",
                         "gh release create v1.3.0", "gh release download v1.3.0", "sha256sum --check",
                         "--network none", "Tag exists at a different object; refusing retag"):
            self.assertIn(required, commands)
        self.assertNotIn("git push --force", commands)
        self.assertNotIn("gh release delete", commands)
        self.assertIn("rollback", (ROOT / "docs/RELEASE_NOTES_1_3_0.md").read_text())

if __name__ == "__main__":
    unittest.main()
