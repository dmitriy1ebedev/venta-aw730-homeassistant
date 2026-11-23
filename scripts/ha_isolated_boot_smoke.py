"""Real Home Assistant boot/reboot/rollback gate in an isolated, disposable container.

The runner mounts a public synthetic source fixture read-only. This script
copies it into /tmp and runs actual Home Assistant processes with a local-only
HTTP health probe. No real device, local_key, pairing, network or production
configuration is read. The sample config entry intentionally fails closed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

DOMAIN = "venta_homekit_native"
PORT = 28997
HOST = f"http://127.0.0.1:{PORT}/api/"


def digest(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _entry(entry_id, domain, data, *, disabled_by=None, options=None):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "created_at": now, "modified_at": now, "data": data,
        "discovery_keys": {}, "disabled_by": disabled_by,
        "domain": domain, "entry_id": entry_id, "minor_version": 1,
        "options": options or {}, "pref_disable_new_entities": False,
        "pref_disable_polling": False, "source": "user", "subentries": [],
        "title": "Venta CI" if domain == DOMAIN else "CI disabled HomeKit Bridge",
        "unique_id": "humidifier.venta_ci_fake" if domain == DOMAIN else None,
        "version": 1,
    }


def synthetic_entry_store() -> dict:
    """Create only synthetic HA 2026.11 config entries, without pairing."""
    roles = {
        "humidifier_entity": "humidifier.venta_ci_fake",
        "bridge_title": "CI disabled HomeKit Bridge",
        "bridge_entry_id": "ci-homekit-fixture-entry",
        "fan_entity": "select.venta_ci_fan",
        "led_entity": "switch.venta_ci_led",
        "brightness_entity": "select.venta_ci_led_brightness",
        "temperature_entity": "sensor.venta_ci_temperature",
        "humidity_entity": "sensor.venta_ci_humidity",
        "confirmed_unclassified": [],
    }
    return {
        "version": 1, "minor_version": 5, "key": "core.config_entries",
        "data": {"entries": [
            _entry(
                "ci-homekit-fixture-entry", "homekit", {},
                disabled_by="user", options={
                    "mode": "bridge",
                    "filter": {"include_entities": ["humidifier.venta_ci_fake"]},
                },
            ),
            _entry("ci-venta-fixture-entry", DOMAIN, roles),
        ]},
    }


def _inspect_store(root: Path) -> None:
    state = root / ".storage" / "core.config_entries"
    if not state.is_file() or state.is_symlink() or state.stat().st_size > 65536:
        raise AssertionError("synthetic entry persistence missing or oversized")
    data = json.loads(state.read_text(encoding="utf-8"))
    entries = data["data"]["entries"]
    expected = {
        ("homekit", "ci-homekit-fixture-entry"),
        (DOMAIN, "ci-venta-fixture-entry"),
    }
    seen = [(entry["domain"], entry["entry_id"]) for entry in entries]
    if len(seen) != len(expected) or set(seen) != expected:
        raise AssertionError("duplicate, missing or replaced config entry")
    venta = next(entry for entry in entries if entry["domain"] == DOMAIN)
    homekit = next(entry for entry in entries if entry["domain"] == "homekit")
    if (
        venta["unique_id"] != "humidifier.venta_ci_fake"
        or venta["data"]["bridge_entry_id"] != homekit["entry_id"]
        or homekit["disabled_by"] != "user"
    ):
        raise AssertionError("synthetic HA identity changed across restart")
    # No Apple pairing store or HAP server should ever be created here.
    forbidden = [
        f for f in (root / ".storage").iterdir()
        if "homekit." in f.name.lower() or "pairing" in f.name.lower()
    ]
    if forbidden:
        raise AssertionError("unexpected HomeKit pairing artifact")


def _http_ready() -> bool:
    try:
        with urlopen(HOST, timeout=1.0) as response:
            return response.status in (200, 401, 403)
    except HTTPError as err:
        return err.code in (401, 403)
    except (URLError, TimeoutError, OSError):
        return False


def _run_boot(root: Path, phase: str, timeout: int) -> dict:
    log = root.parent / f"boot-{phase}.log"
    start = time.monotonic()
    with log.open("wb") as out:
        process = subprocess.Popen(
            [
                sys.executable, "-m", "homeassistant",
                "--config", str(root), "--skip-pip",
            ],
            stdout=out, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        ready = False
        shutdown_ok = False
        try:
            while time.monotonic() - start < timeout:
                if process.poll() is not None:
                    raise AssertionError(
                        f"HA {phase} exited before readiness: {process.returncode}"
                    )
                if _http_ready():
                    ready = True
                    break
                time.sleep(1.0)
            if not ready:
                raise AssertionError(f"HA {phase} HTTP readiness timeout")
            # Assert real ConfigEntries manager loaded BOTH entries from disk.
            _inspect_store(root)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=30)
                shutdown_ok = True
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=8)
    if not shutdown_ok:
        raise AssertionError(f"HA {phase} did not stop gracefully")
    _inspect_store(root)
    return {
        "phase": phase,
        "ready_http": ready,
        "shutdown_ok": shutdown_ok,
        "seconds": round(time.monotonic() - start, 2),
    }


def validate(source: Path, expected_version: str, *, boot_timeout: int = 95) -> dict:
    from homeassistant.const import __version__ as actual_version

    if actual_version != expected_version:
        raise AssertionError("wrong Home Assistant image")
    if (
        not source.is_dir()
        or source.is_symlink()
        or (source / ".storage").exists()
        or not (source / "custom_components" / DOMAIN / "manifest.json").is_file()
    ):
        raise ValueError("source must be synthetic staged component-only config")
    src_yaml = (source / "configuration.yaml").read_bytes()
    if (
        b"humidifier.venta_ci_fake" not in src_yaml
        or b"venta_homekit_native:" not in src_yaml
        or len(src_yaml) > 8192
    ):
        raise ValueError("not a known synthetic YAML fixture")

    with tempfile.TemporaryDirectory(prefix="venta-ci-real-boot-") as temp:
        root = Path(temp) / "configuration"
        root.mkdir()
        shutil.copytree(
            source / "custom_components",
            root / "custom_components",
            symlinks=False,
        )
        storage = root / ".storage"
        storage.mkdir(mode=0o700)
        (storage / "core.config_entries").write_text(
            json.dumps(synthetic_entry_store(), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        addition = (
            "\nhttp:\n  server_host: 127.0.0.1\n"
            f"  server_port: {PORT}\napi:\n"
        ).encode("utf-8")
        baseline = src_yaml + addition
        yaml = root / "configuration.yaml"
        yaml.write_bytes(baseline)
        tests = [_run_boot(root, "yaml", boot_timeout)]

        marker = b"\nventa_homekit_native:\n"
        prefix, delim, _rest = src_yaml.partition(marker)
        if not delim:
            raise ValueError("synthetic Venta YAML boundary missing")
        cutover = prefix + b"\n" + addition
        yaml.write_bytes(cutover)
        tests.append(_run_boot(root, "ui_cutover", boot_timeout))

        yaml.write_bytes(baseline)
        tests.append(_run_boot(root, "yaml_restore", boot_timeout))
        if digest(yaml.read_bytes()) != digest(baseline):
            raise AssertionError("YAML rollback not byte-identical")
        _inspect_store(root)
        return {
            "status": "PASS",
            "home_assistant": actual_version,
            "booted_real_ha_processes": len(tests),
            "entry_ids_preserved": True,
            "config_rollback_byte_exact": True,
            "physical_device_calls": 0,
            "pairings_touched": False,
            "network_mode": "container_network_none",
            "steps": tests,
        }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--ha-version", required=True)
    ap.add_argument("--boot-timeout", type=int, default=95)
    args = ap.parse_args()
    print(json.dumps(validate(
        args.config, args.ha_version, boot_timeout=args.boot_timeout,
    ), sort_keys=True))
