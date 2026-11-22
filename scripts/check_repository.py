"""Offline, secret-free repository structure and release-readiness checks."""

from __future__ import annotations

import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "venta_homekit_native"


def validate() -> list[str]:
    problems: list[str] = []
    required = (
        "README.md",
        "README.ru.md",
        "AGENTS.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
        "THIRD_PARTY_NOTICES.md",
        "LICENSE",
        "docs/RELEASING.md",
        "docs/CI_SECURITY.md",
        "docs/DIAGNOSTICS.md",
        "custom_components/venta_homekit_native/diagnostics.py",
        "custom_components/venta_homekit_native/entity_discovery.py",
        "scripts/ha_entity_registry_smoke.py",
        "scripts/ha_config_flow_smoke.py",
        "scripts/ha_config_entry_setup_smoke.py",
        "docs/ENTITY_DISCOVERY.md",
        "scripts/build_release.py",
        "scripts/stage_ha_runtime.py",
        "scripts/ha_native_homekit_smoke.py",
        "scripts/ha_homekit_identity_smoke.py",
        "hacs.json",
        ".github/CODEOWNERS",
        ".github/workflows/validate.yml",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/PULL_REQUEST_TEMPLATE.md",
        "custom_components/venta_homekit_native/__init__.py",
        "custom_components/venta_homekit_native/manifest.json",
        "custom_components/venta_homekit_native/services.yaml",
        "custom_components/venta_homekit_native/brand/icon.png",
        "custom_components/venta_homekit_native/brand/icon@2x.png",
        "assets/venta-aw730-banner.svg",
        "assets/venta-aw730-logo.svg",
        "custom_components/venta_homekit_native/templates/venta_aw730.yaml",
        "custom_components/venta_homekit_native/install_localtuya_template.py",
    )
    for rel in required:
        if not (ROOT / rel).is_file():
            problems.append("Missing: " + rel)

    if (ROOT / "llms.txt").exists():
        problems.append("Stale llms.txt must not be published")
    if (ROOT / "docs/publish.md").exists():
        problems.append("Stale publication checklist must not be published")

    try:
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        metadata = json.loads((ROOT / "hacs.json").read_text())
        if manifest.get("domain") != INTEGRATION.name:
            problems.append("Manifest domain does not match directory")
        if manifest.get("name") != "Venta AW730" or metadata.get("name") != "Venta AW730":
            problems.append("Inconsistent Marketplace name")
        if manifest.get("codeowners") != ["@dmitriy1ebedev"]:
            problems.append("Missing repository owner in manifest")
        if manifest.get("categories") != ["sensors.air_quality", "sensors.temperature_humidity"]:
            problems.append("Unexpected integration categories")
        if not re.fullmatch(r"\d+\.\d+\.\d+", manifest.get("version", "")):
            problems.append("Manifest version is not semantic")
        if not manifest.get("issue_tracker", "").startswith("https://github.com/"):
            problems.append("Missing public issue tracker")
    except (OSError, ValueError, TypeError) as exc:
        problems.append("Invalid manifest or hacs.json: " + str(exc))

    for name, expected in (("icon.png", 256), ("icon@2x.png", 512)):
        try:
            raw = (INTEGRATION / "brand" / name).read_bytes()
            if not raw.startswith(b"\x89PNG\r\n\x1a\n") or struct.unpack(">II", raw[16:24]) != (
                expected,
                expected,
            ):
                problems.append("Incorrect icon dimensions: " + name)
        except (OSError, ValueError, struct.error) as exc:
            problems.append("Invalid icon " + name + ": " + str(exc))

    try:
        import yaml

        template = yaml.safe_load((INTEGRATION / "templates/venta_aw730.yaml").read_text())
        if not isinstance(template, list) or len(template) != 18:
            problems.append("Bundled LocalTuya template has unexpected structure")
    except (OSError, ValueError, ImportError) as exc:
        problems.append("Invalid LocalTuya YAML: " + str(exc))

    for name in ("README.md", "README.ru.md"):
        try:
            readme = (ROOT / name).read_text()
            if "assets/venta-aw730-banner.svg" not in readme:
                problems.append("README missing high-resolution banner: " + name)
            if "ha-marketplace:exclude-start" not in readme:
                problems.append("README missing Marketplace-aware install link: " + name)
        except OSError as exc:
            problems.append("Cannot read README " + name + ": " + str(exc))

    # Explicit credential assignments are blocked; public documentation examples
    # discussing key names are not credentials and are allowed.
    assignment = re.compile(
        r"(?im)^\s*(?:local_key|access_token|refresh_token|password|client_secret)\s*[:=]\s*['\"]?[A-Za-z0-9+/_=-]{9,}"
    )
    for p in ROOT.rglob("*"):
        if not p.is_file() or {".git", "__pycache__"} & set(p.parts):
            continue
        if p.suffix.lower() in {".png", ".pyc", ".zip"}:
            continue
        try:
            content = p.read_text()
        except UnicodeDecodeError:
            problems.append("Unexpected binary file: " + str(p.relative_to(ROOT)))
            continue
        if assignment.search(content):
            problems.append("Potential credential in " + str(p.relative_to(ROOT)))

    return problems


def main() -> int:
    errors = validate()
    for problem in errors:
        print("ERROR:", problem)
    if errors:
        return 1
    print("Repository checks: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
