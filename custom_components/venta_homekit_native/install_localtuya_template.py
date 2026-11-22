"""Install and safely synchronize the bundled Venta AW730 LocalTuya template.

The template is an installation aid: LocalTuya stores an independent copy of
each configured device's entities. Synchronizing this file does not rewrite an
already-configured LocalTuya device, its credentials or its entity IDs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone

FILENAME = "venta_aw730.yaml"
MARKER = "venta_homekit_native.template.json"
_ALLOWED_LEGACY_FIELDS = {
    "PM2.5": {"unit_of_measurement"},
    "Filter": {"unit_of_measurement"},
    "Cleaning": {"unit_of_measurement"},
    "Service": {"unit_of_measurement"},
    "Water Level": {"device_class"},
}


def _source_and_destination(config_dir: Path) -> tuple[Path, Path]:
    source = Path(__file__).resolve().parent / "templates" / FILENAME
    if not source.is_file():
        raise RuntimeError("Bundled Venta template is missing. Reinstall Venta AW730.")
    destination_dir = config_dir / "custom_components" / "localtuya" / "templates"
    if not destination_dir.is_dir():
        raise RuntimeError("Install LocalTuya first; its templates directory was not found.")
    return source, destination_dir / FILENAME


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _marker_path(config_dir: Path) -> Path:
    return config_dir / ".storage" / MARKER


def _managed_digest(config_dir: Path) -> str | None:
    marker = _marker_path(config_dir)
    if marker.is_symlink() or not marker.is_file():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    digest = data.get("destination_sha256") if isinstance(data, dict) else None
    return digest if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) else None


def _save_managed_digest(config_dir: Path, content: bytes) -> None:
    marker = _marker_path(config_dir)
    if marker.is_symlink():
        raise RuntimeError("Refusing symlink for template tracking marker")
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({
        "version": 1,
        "destination_sha256": _digest(content),
    }, sort_keys=True).encode("utf-8") + b"\n"
    fd, temp_name = tempfile.mkstemp(prefix=".venta-marker-", dir=marker.parent)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, marker)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _only_known_legacy_differences(old: bytes, new: bytes) -> bool:
    """Accept older official templates only if known units/class changed.

    Never overwrite unknown DP mappings, user-defined entity names or settings.
    YAML comments are immaterial. This also handles the pre-1.0.3 original
    LocalTuya template without relying on any user's device credentials.
    """
    try:
        import yaml
    except ImportError:
        return False
    try:
        before, after = yaml.safe_load(old), yaml.safe_load(new)
    except (yaml.YAMLError, UnicodeDecodeError, ValueError):
        return False
    if not isinstance(before, list) or not isinstance(after, list) or len(before) != len(after):
        return False
    changed = False
    for prior, current in zip(before, after):
        if not isinstance(prior, dict) or not isinstance(current, dict) or prior.keys() != current.keys():
            return False
        for kind, expected in current.items():
            existing = prior[kind]
            if not isinstance(existing, dict) or not isinstance(expected, dict):
                return False
            name = expected.get("friendly_name")
            if existing.get("friendly_name") != name or existing.get("id") != expected.get("id"):
                return False
            permitted = _ALLOWED_LEGACY_FIELDS.get(name, set())
            for key in set(existing) | set(expected):
                if existing.get(key) != expected.get(key) or (key in existing) != (key in expected):
                    if key not in permitted:
                        return False
                    changed = True
                    if key in expected:
                        existing[key] = expected[key]
                    else:
                        existing.pop(key, None)
    return changed and before == after


def install(config_dir: Path, replace: bool = False) -> str:
    """Manual installer; never replaces a different template without --replace."""
    source, destination = _source_and_destination(config_dir)
    content = source.read_bytes()
    if destination.exists() or destination.is_symlink():
        if not destination.is_file() or destination.is_symlink():
            raise RuntimeError("Refusing unsafe template destination.")
        if destination.read_bytes() == content:
            return "already installed"
        if not replace:
            raise RuntimeError(
                "A different template is already present. No changes made. "
                "Use --replace to back it up and install the new template."
            )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = destination.with_name(FILENAME + "." + stamp + ".bak")
        if backup.exists():
            raise RuntimeError("Backup already exists; try again later.")
        shutil.copy2(destination, backup)
    fd, temp_name = tempfile.mkstemp(prefix=".venta-", suffix=".yaml", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        os.chmod(temp_name, 0o644)
        os.replace(temp_name, destination)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    if _digest(destination.read_bytes()) != _digest(content):
        raise RuntimeError("Template verification failed")
    return "installed"


def sync_managed_template(config_dir: Path) -> str:
    """Synchronize on HA startup after a Marketplace integration update.

    Automatically updates an unchanged previously-managed copy, or the
    recognizable older official template. Unknown/custom templates stay intact.
    Existing LocalTuya config entries are deliberately never rewritten.
    """
    try:
        source, destination = _source_and_destination(config_dir)
    except RuntimeError as exc:
        if "Install LocalTuya first" in str(exc):
            return "skipped: LocalTuya is not installed"
        raise

    fresh = source.read_bytes()
    if destination.is_symlink():
        return "skipped: template is a symlink"
    if not destination.exists():
        result = install(config_dir)
        _save_managed_digest(config_dir, fresh)
        return result

    previous = destination.read_bytes()
    if previous == fresh:
        _save_managed_digest(config_dir, fresh)
        return "already current"

    managed_sha = _managed_digest(config_dir)
    if managed_sha == _digest(previous) or _only_known_legacy_differences(previous, fresh):
        result = install(config_dir, replace=True)
        _save_managed_digest(config_dir, fresh)
        return "updated (previous copy backed up)"
    return "skipped: locally modified template preserved"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install bundled Venta AW730 template into LocalTuya")
    parser.add_argument("--ha-config", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--replace", action="store_true", help="Back up and replace a different existing template")
    args = parser.parse_args()
    try:
        result = install(args.ha_config, replace=args.replace)
        if result == "installed" or result == "already installed":
            _save_managed_digest(args.ha_config, (Path(__file__).resolve().parent / "templates" / FILENAME).read_bytes())
    except (OSError, RuntimeError) as exc:
        print("Venta AW730:", exc, file=sys.stderr)
        return 2
    print("Venta AW730 template:", result, "— select venta_aw730.yaml when adding the device in LocalTuya")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
