"""Create a deterministic, offline Venta integration archive for release QA.

This is a *manual install-layout artifact*. It does not publish a tag, deploy
to Home Assistant, access credentials, or alter a running device.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = Path("custom_components") / "venta_homekit_native"
EXCLUDED_DIRS = {"__pycache__", ".storage", ".git"}
EXCLUDED_FILES = {".DS_Store", "Thumbs.db"}
SENSITIVE_STEMS = {"secrets", "credentials", "local_key", "token", "access_token",
                   "refresh_token", "client_secret", "private_key", "pairing",
                   "config_entries", "entity_registry", "device_registry"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".pem", ".key", ".p12", ".pfx", ".bak"}
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_INPUT_BYTES = 32 * 1024 * 1024


class ReleaseValidationError(ValueError):
    """A candidate release is structurally unsafe or inconsistent."""


def release_version(root: Path = ROOT, expected_tag: str | None = None) -> str:
    """Require exact manifest/CHANGELOG version agreement before any archive."""
    manifest = json.loads((root / COMPONENT / "manifest.json").read_text(encoding="utf-8"))
    version = manifest.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ReleaseValidationError("manifest.json must contain a semantic version")
    heading = f"## {version} ("
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if not any(line.startswith(heading) for line in changelog.splitlines()):
        raise ReleaseValidationError(f"CHANGELOG.md does not describe {version}")
    if expected_tag is not None and expected_tag != "v" + version:
        raise ReleaseValidationError(
            f"release tag {expected_tag!r} does not match manifest v{version}"
        )
    return version


def component_files(root: Path = ROOT) -> list[tuple[Path, str]]:
    """Allow only the shipped component; reject symlinks and credential files."""
    component = root / COMPONENT
    required = {"__init__.py", "manifest.json", "services.yaml",
                "install_localtuya_template.py", "templates/venta_aw730.yaml"}
    for name in required:
        if not (component / name).is_file():
            raise ReleaseValidationError(f"missing component file: {name}")
    result: list[tuple[Path, str]] = []
    total = 0
    if component.is_symlink():
        raise ReleaseValidationError("component directory cannot be a symlink")
    for entry in sorted(component.rglob("*"), key=lambda p: p.as_posix()):
        rel = entry.relative_to(root)
        if entry.is_symlink():
            raise ReleaseValidationError(f"symlink is not allowed: {rel}")
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if entry.is_dir():
            continue
        if not entry.is_file():
            raise ReleaseValidationError(f"non-regular file: {rel}")
        if entry.name in EXCLUDED_FILES or entry.suffix in {".pyc", ".pyo"}:
            continue
        if (entry.suffix in FORBIDDEN_SUFFIXES or entry.name.startswith(".")
                or entry.stem.lower() in SENSITIVE_STEMS):
            raise ReleaseValidationError(f"unexpected or sensitive file: {rel}")
        size = entry.stat().st_size
        if size > MAX_FILE_BYTES:
            raise ReleaseValidationError(f"oversized component file: {rel}")
        total += size
        if total > MAX_ARCHIVE_INPUT_BYTES:
            raise ReleaseValidationError("component files exceed the size budget")
        result.append((entry, rel.as_posix()))
    if not result:
        raise ReleaseValidationError("empty component archive")
    return result


def build_archive(output: Path, root: Path = ROOT, expected_tag: str | None = None) -> dict:
    """Create an immutable zip path; never overwrite a previous candidate."""
    version = release_version(root, expected_tag)
    files = component_files(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with output.open("xb") as handle:
            created = True
            with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for source, name in files:
                    info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.create_system = 3
                    info.external_attr = 0o644 << 16
                    archive.writestr(
                        info, source.read_bytes(),
                        compress_type=zipfile.ZIP_DEFLATED, compresslevel=9,
                    )
    except BaseException:
        # Remove only a failed artifact created by this invocation.
        # Never delete an existing archive rejected by exclusive open.
        if created:
            output.unlink(missing_ok=True)
        raise
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return {"version": version, "archive": str(output), "sha256": digest, "files": len(files)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline release-layout archive for Venta AW730")
    parser.add_argument("--output", type=Path, help="new zip path; existing files are never overwritten")
    parser.add_argument("--expected-tag", help="optional immutable release tag, such as v1.0.5")
    args = parser.parse_args()
    version = release_version(expected_tag=args.expected_tag)
    output = args.output or ROOT / "dist" / f"venta-aw730-v{version}-manual.zip"
    print(json.dumps(build_archive(output, expected_tag=args.expected_tag), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
