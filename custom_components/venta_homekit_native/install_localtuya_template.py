"""Safely make the bundled Venta AW730 template available to LocalTuya.

Run from Home Assistant's Python environment after both integrations are installed.
No network access, no credentials, no device commands.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
from datetime import datetime, timezone

FILENAME = "venta_aw730.yaml"


def install(config_dir: Path, replace: bool = False) -> str:
    source = Path(__file__).resolve().parent / "templates" / FILENAME
    if not source.is_file():
        raise RuntimeError("Bundled Venta template is missing. Reinstall Venta AW730.")
    destination_dir = config_dir / "custom_components" / "localtuya" / "templates"
    if not destination_dir.is_dir():
        raise RuntimeError("Install LocalTuya first; its templates directory was not found.")
    destination = destination_dir / FILENAME
    content = source.read_bytes()
    if destination.exists():
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
    fd, temp_name = tempfile.mkstemp(prefix=".venta-", suffix=".yaml", dir=destination_dir)
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
    if hashlib.sha256(destination.read_bytes()).digest() != hashlib.sha256(content).digest():
        raise RuntimeError("Template verification failed")
    return "installed"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install bundled Venta AW730 template into LocalTuya")
    parser.add_argument("--ha-config", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--replace", action="store_true", help="Back up and replace a different existing template")
    args = parser.parse_args()
    try:
        result = install(args.ha_config, replace=args.replace)
    except (OSError, RuntimeError) as exc:
        print("Venta AW730:", exc, file=sys.stderr)
        return 2
    print("Venta AW730 template:", result, "— select venta_aw730.yaml when adding the device in LocalTuya")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
