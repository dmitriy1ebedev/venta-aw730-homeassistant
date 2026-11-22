"""Stage a self-built Venta component archive for disposable Home Assistant CI.

Never reads a real Home Assistant config, local keys or bridge pairing data.
The generated YAML contains deliberately nonexistent device/entity identifiers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from scripts.build_release import COMPONENT, ReleaseValidationError


FAKE_HA_CONFIG = """homeassistant:
  name: Venta CI disposable
  latitude: 0
  longitude: 0
  elevation: 0
  unit_system: metric
  time_zone: UTC

venta_homekit_native:
  humidifier_entity: humidifier.venta_ci_fake
  bridge_title: "Venta CI nonexistent bridge"
  fan_entity: select.venta_ci_fan
  led_entity: switch.venta_ci_led
  brightness_entity: select.venta_ci_led_brightness
  temperature_entity: sensor.venta_ci_temperature
  humidity_entity: sensor.venta_ci_humidity
"""


def stage(archive_path: Path, target: Path) -> dict:
    """Extract only a trusted component-layout archive into a new isolated dir."""
    if target.exists():
        raise ReleaseValidationError("refuse to overwrite existing HA configuration")
    # Reject extra names and path traversal even if the package is self-built.
    with ZipFile(archive_path) as package:
        names = package.namelist()
        if not names:
            raise ReleaseValidationError("empty integration archive")
        for name in names:
            p = PurePosixPath(name)
            if (
                p.is_absolute()
                or ".." in p.parts
                or not name.startswith(COMPONENT.as_posix() + "/")
                or any(part in ("", ".storage") for part in p.parts)
                or package.getinfo(name).is_dir()
            ):
                raise ReleaseValidationError(f"unsafe archive member: {name}")
        if (COMPONENT / "manifest.json").as_posix() not in names:
            raise ReleaseValidationError("missing component manifest")
        target.mkdir(parents=True, exist_ok=False)
        package.extractall(target)

    (target / "configuration.yaml").write_text(FAKE_HA_CONFIG, encoding="utf-8")
    manifest = json.loads((target / COMPONENT / "manifest.json").read_text())
    if manifest.get("domain") != COMPONENT.name:
        raise ReleaseValidationError("staged component domain mismatch")
    return {
        "ha_config": str(target),
        "component_version": manifest["version"],
        "archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "files": len(names),
        "no_device_credentials": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(stage(args.archive, args.config), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
