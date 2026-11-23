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
        form = yaml.safe_load((ROOT / ".github/ISSUE_TEMPLATE/bug_report.yml").read_text())
        ids = {field.get("id"): field for field in form["body"] if field.get("id")}
        for required in ("ha_version", "localtuya_version", "venta_version", "venta_model", "affected", "steps", "expected", "actual", "safety"):
            self.assertIn(required, ids)
        self.assertTrue(ids["venta_model"]["validations"]["required"])
        self.assertTrue(ids["steps"]["validations"]["required"])
        self.assertIn("no destructive resets", ids["steps"]["attributes"]["label"])
        self.assertIn("redacted", ids["actual"]["attributes"]["label"].lower())
        self.assertIn("IP/MAC", ids["safety"]["attributes"]["options"][0]["label"])

if __name__ == "__main__":
    unittest.main()
