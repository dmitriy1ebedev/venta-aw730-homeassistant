"""Document contract regression tests: public release history and local links."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DocumentationContractTests(unittest.TestCase):
    def test_changelog_covers_installed_manifest(self):
        manifest = json.loads(
            (ROOT / "custom_components/venta_homekit_native/manifest.json").read_text()
        )
        changelog = (ROOT / "CHANGELOG.md").read_text()
        version = manifest["version"]
        self.assertRegex(changelog, rf"(?m)^## {re.escape(version)} \(\d{{4}}-\d{{2}}-\d{{2}}\)$")
        for historical in ("1.0.0", "1.0.1", "1.0.2", "1.0.3", "1.0.4"):
            self.assertIn("## " + historical + " (", changelog)
        self.assertEqual((ROOT / "VERSION").read_text().strip(), version)
        for name, label in (("README.md", "Version"), ("README.ru.md", "Версия")):
            with self.subTest(readme=name):
                readme = (ROOT / name).read_text()
                badges = re.findall(
                    r"img\.shields\.io/badge/version-([0-9]+\.[0-9]+\.[0-9]+)-",
                    readme,
                )
                self.assertEqual(badges, [version], "README badge must match manifest")
                self.assertIn(f"[![{label} {version}]", readme)

    def test_installer_documentation_matches_managed_sync(self):
        architecture = (ROOT / "docs/architecture.md").read_text()
        maintaining = (ROOT / "docs/MAINTAINING.md").read_text()
        for document in (architecture, maintaining):
            self.assertIn("sync_managed_template", document)
            self.assertIn("install_localtuya_template.py", document)
            self.assertIn("--replace", document)
            self.assertIn("backup", document.lower())
        self.assertNotIn("only on explicit invocation", architecture)
        self.assertNotIn("intentionally not overwritten", maintaining)

    def test_readme_internal_links_are_present(self):
        for name in ("README.md", "README.ru.md"):
            readme = (ROOT / name).read_text()
            self.assertIn("](ROADMAP.md)", readme)
            self.assertIn("](CHANGELOG.md)", readme)
            for link in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", readme):
                target = link.split("#", 1)[0].split("?", 1)[0]
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                with self.subTest(readme=name, link=link):
                    self.assertTrue((ROOT / target).is_file(), link)


    def test_compatibility_matrix_and_reproducible_issue_form(self):
        import yaml
        matrix = (ROOT / "docs/compatibility.md").read_text()
        for value in ("AW730", "2026.11.1", "2026.10.0", "3.4", "Unverified", "sync_managed_template"):
            self.assertIn(value, matrix)
        self.assertIn("not independently verified", matrix)
        self.assertIn("**2026.11.2**", matrix)
        self.assertIn("**TESTED IN ISOLATION**", matrix)
        for version in ("2026.11.3", "2026.12.0b0"):
            row = next(line for line in matrix.splitlines() if line.startswith(f"| **{version}**"))
            self.assertIn("**TESTED IN ISOLATION**", row)
            self.assertIn("45759800364", row)
        self.assertIn("synthetic registry/configuration contract", matrix)
        self.assertIn("7c03516ebd37a9d03ed567429739faa683d8cfbd", matrix)
        self.assertIn("**1.2.0**", matrix)
        self.assertIn("45137841054", matrix)
        self.assertIn("never modify the working existing bridge", matrix.lower())
        form = yaml.safe_load((ROOT / ".github/ISSUE_TEMPLATE/bug_report.yml").read_text())
        ids = {field.get("id"): field for field in form["body"] if field.get("id")}
        for required in ("ha_version", "localtuya_version", "venta_version", "venta_model", "affected", "steps", "expected", "actual", "safety"):
            self.assertIn(required, ids)
        self.assertTrue(ids["venta_model"]["validations"]["required"])
        self.assertTrue(ids["steps"]["validations"]["required"])
        self.assertIn("no destructive resets", ids["steps"]["attributes"]["label"])
        self.assertIn("redacted", ids["actual"]["attributes"]["label"].lower())
        self.assertIn("IP/MAC", ids["safety"]["attributes"]["options"][0]["label"])

    def test_public_catalog_and_support_claims(self):
        matrix = (ROOT / "docs/MARKETPLACE.md").read_text()
        self.assertIn("NOT SUBMITTED", matrix)
        self.assertIn("ignore: topics", matrix)
        self.assertIn("HomeKit", matrix)
        self.assertIn("45760621426", (ROOT / "docs/compatibility.md").read_text())
        for name in ("README.md", "README.ru.md"):
            doc = (ROOT / name).read_text()
            for link in ("docs/MARKETPLACE.md", "docs/YAML_MIGRATION.md", "extras/dashboard/README.md", ".github/ISSUE_TEMPLATE/bug_report.yml"):
                self.assertIn(link, doc)
            self.assertIn("2026.12.0b0", doc)
        import yaml
        form = yaml.safe_load((ROOT / ".github/ISSUE_TEMPLATE/bug_report.yml").read_text())
        diagnostic = next(field for field in form["body"] if field.get("id") == "diagnostic_report")
        self.assertFalse(diagnostic["validations"]["required"])
        self.assertIn("log_diagnostics", diagnostic["attributes"]["description"])

    def test_ui_localizations_cover_every_wizard_and_repair_label(self):
        """Both built-in locales must cover every actual Home Assistant UI key."""
        component = ROOT / "custom_components/venta_homekit_native"
        english_source = json.loads((component / "strings.json").read_text())
        english = json.loads((component / "translations/en.json").read_text())
        russian = json.loads((component / "translations/ru.json").read_text())

        def flatten(values, prefix=""):
            labels = {}
            for key, value in values.items():
                path = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    labels.update(flatten(value, path))
                else:
                    self.assertIsInstance(value, str, path)
                    self.assertTrue(value.strip(), path)
                    labels[path] = value
            return labels

        source_labels = flatten(english_source)
        english_labels = flatten(english)
        russian_labels = flatten(russian)
        self.assertEqual(english_labels, source_labels)
        self.assertEqual(set(russian_labels), set(source_labels))
        self.assertGreaterEqual(len(source_labels), 70)
        for section in ("config", "options", "issues"):
            self.assertIn(section, russian)
        self.assertIn("config.step.user.title", russian_labels)
        self.assertIn("config.step.migrate_yaml.title", russian_labels)

    def test_release_document_does_not_confuse_canary_and_formal_install(self):
        release = (ROOT / "docs/RELEASE_1_2_0.md").read_text()
        self.assertIn("GitHub PR #19 was merged", release)
        self.assertIn("project_release_status=NOT_STARTED", release)
        self.assertIn("Do not replay", release)
        self.assertIn("Face ID", release)
        self.assertIn("CI `45132027560`", release)
        compatibility = (ROOT / "docs/compatibility.md").read_text()
        self.assertIn("installed Venta **1.2.0**", compatibility)
        self.assertIn("archived **1.0.4**", compatibility)


if __name__ == "__main__":
    unittest.main()
