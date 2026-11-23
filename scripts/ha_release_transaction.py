"""Venta 1.2.0 Home Assistant release transaction (root-only production phases).

No live YAML→UI migration, no LocalTuya writes, no Apple Home re-pairing.
The owner approves this exact script and release recipe through MCPshka.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time

try:
    from .build_release import component_files
    from .ha_private_restore_audit import audit, required_paths
except ImportError:  # Direct production script invocation.
    from build_release import component_files
    from ha_private_restore_audit import audit, required_paths

DOMAIN = "venta_homekit_native"
EXPECTED_OLD = "1.0.4"
NEW = "1.2.0"
DEFAULT_CONFIG = Path("/opt/homeassistant/config")
DEFAULT_LEDGER = Path("/var/lib/venta-aw730-releases")
DEFAULT_SCRATCH = Path("/dev/shm")
MAX_GUARD_FILE = 2 * 1024 * 1024


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_regular(path: Path, max_size: int = MAX_GUARD_FILE) -> bytes:
    if (
        path.is_symlink() or not path.is_file()
        or not stat.S_ISREG(path.stat().st_mode)
        or path.stat().st_size > max_size or path.stat().st_size < 1
    ):
        raise ValueError("missing_or_unsafe_release_input")
    return path.read_bytes()


def manifest_version(path: Path) -> str:
    value = json.loads(safe_regular(path, 32768))
    if value.get("domain") != DOMAIN or not isinstance(value.get("version"), str):
        raise ValueError("not_venta_component")
    return value["version"]


def source_version(source: Path) -> str:
    component = source / "custom_components" / DOMAIN
    if source.is_symlink() or component.is_symlink():
        raise ValueError("symlinked_release_source")
    version = manifest_version(component / "manifest.json")
    if version != NEW:
        raise ValueError("release_source_wrong_version")
    # Validate public packaging allowlist, symlinks, credentials and file caps.
    component_files(source)
    if (source / "VERSION").read_text(encoding="ascii").strip() != NEW:
        raise ValueError("VERSION_mismatch")
    return version


def select_bridge(root: Path) -> str:
    """Existing bridge that exports precisely one Venta-like humidifier."""
    store = json.loads(safe_regular(root / ".storage/core.config_entries"))
    candidates = []
    for entry in store.get("data", {}).get("entries", []):
        if entry.get("domain") != "homekit" or entry.get("disabled_by"):
            continue
        options = entry.get("options") or {}
        filters = options.get("filter") or {}
        include = filters.get("include_entities") or []
        excluded = filters.get("exclude_entities") or []
        hums = [x for x in include if isinstance(x, str) and x.startswith("humidifier.")]
        if len(hums) == 1 and hums[0] not in excluded:
            candidates.append((entry.get("entry_id"), hums[0]))
    if len(candidates) != 1:
        raise ValueError("cannot_disambiguate_existing_homekit_bridge")
    bridge, entity = candidates[0]
    if not isinstance(bridge, str) or not re.fullmatch(r"[A-Za-z0-9_-]{6,80}", bridge):
        raise ValueError("homekit_bridge_id_invalid")
    # The existing legacy YAML remains in place throughout this release.
    legacy = safe_regular(root / "configuration.yaml", 2 * 1024 * 1024)
    if (b"venta_homekit_native:" not in legacy
        or b"humidifier_entity:" not in legacy
        or entity.encode() not in legacy):
        raise ValueError("legacy_yaml_binding_not_present")
    return bridge


def healthy() -> bool:
    p = subprocess.run(
        ["/usr/bin/docker", "inspect", "--format", "{{.State.Health.Status}}", "homeassistant"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        timeout=12, check=False,
    )
    return p.returncode == 0 and p.stdout.strip() == "healthy"


def newest_backup(root: Path, *, max_age: int = 7200) -> Path:
    backups = root / "backups"
    if not backups.is_dir() or backups.is_symlink():
        raise ValueError("native_backup_directory_missing")
    options = [
        f for f in backups.glob("*.tar")
        if f.is_file() and not f.is_symlink()
        and f.name.startswith("Custom_backup_")
    ]
    if not options:
        raise ValueError("fresh_native_backup_missing")
    path = max(options, key=lambda f: f.stat().st_mtime)
    if time.time() - path.stat().st_mtime > max_age:
        raise ValueError("native_backup_stale")
    return path


def verify_baseline(source: Path, root: Path, scratch: Path) -> tuple[str, Path]:
    source_version(source)
    component = root / "custom_components" / DOMAIN
    if component.is_symlink() or not component.is_dir():
        raise ValueError("existing_venta_component_unavailable")
    if manifest_version(component / "manifest.json") != EXPECTED_OLD:
        raise ValueError("existing_version_mismatch")
    if not healthy():
        raise ValueError("running_homeassistant_not_healthy")
    bridge = select_bridge(root)
    backup = newest_backup(root)
    result = audit(backup, root, bridge, scratch_root=scratch)
    if result["status"] != "PASS" or result["restored_in_private_scratch"] != 6:
        raise ValueError("backup_restore_audit_failed")
    return bridge, backup


def safe_directory_tree(path: Path) -> None:
    if not path.is_dir() or path.is_symlink():
        raise ValueError("unsafe_component_directory")
    for f in path.rglob("*"):
        if f.is_symlink() or (not f.is_file() and not f.is_dir()):
            raise ValueError("unsafe_component_content")


def paths(root: Path, ledger: Path, version: str) -> dict[str, Path]:
    if version != NEW or root.is_symlink() or not root.is_dir():
        raise ValueError("invalid_release_target")
    parent = root / "custom_components"
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("invalid_components_directory")
    base = ledger / version
    return {
        "live": parent / DOMAIN,
        "staged": parent / (".venta-staged-" + version),
        "displaced": parent / (".venta-previous-" + version),
        "base": base,
        "previous": base / "previous",
        "guard": base / "guard",
        "meta": base / "receipt.json",
    }


def private_write(p: Path, contents: bytes) -> None:
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with p.open("xb") as stream:
        stream.write(contents)
        stream.flush()
        os.fsync(stream.fileno())
    p.chmod(0o600)


def receipt(p: Path) -> dict:
    if p.is_symlink() or not p.is_file():
        raise ValueError("release_receipt_missing")
    meta = json.loads(safe_regular(p, 16384))
    if meta.get("version") != NEW or meta.get("old_version") != EXPECTED_OLD:
        raise ValueError("invalid_release_receipt")
    return meta


def save_receipt(path: Path, meta: dict) -> None:
    if path.is_symlink():
        raise ValueError("release_receipt_symlink")
    tmp = path.with_name(path.name + ".next")
    if tmp.exists():
        raise ValueError("unresolved_receipt_update")
    private_write(tmp, (json.dumps(meta, sort_keys=True) + "\n").encode())
    os.replace(tmp, path)


def stage(source: Path, root: Path, ledger: Path, scratch: Path) -> dict:
    p = paths(root, ledger, NEW)
    if any(p[key].exists() for key in ("base", "staged", "displaced")):
        raise ValueError("existing_release_attempt_requires_reconciliation")
    bridge, backup = verify_baseline(source, root, scratch)
    safe_directory_tree(p["live"])
    ledger.mkdir(mode=0o700, parents=True, exist_ok=True)
    if ledger.is_symlink() or ledger.stat().st_mode & 0o077:
        raise ValueError("insecure_release_ledger_permissions")
    p["base"].mkdir(mode=0o700)
    p["guard"].mkdir(mode=0o700)
    try:
        shutil.copytree(p["live"], p["previous"], symlinks=False)
        p["staged"].mkdir(mode=0o755)
        for src, rel in component_files(source):
            # Source paths are public repo-relative, always component files.
            dest = root / rel
            new = p["staged"] / dest.relative_to(p["live"])
            new.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            new.write_bytes(src.read_bytes())
            new.chmod(0o644)
        if manifest_version(p["staged"] / "manifest.json") != NEW:
            raise ValueError("staged_component_version_mismatch")
        originals = {}
        for rel in required_paths(bridge):
            target = root / rel
            blob = safe_regular(target)
            originals[rel] = sha(blob)
            private_write(p["guard"] / rel, blob)
        meta = {
            "version": NEW, "old_version": EXPECTED_OLD,
            "status": "STAGED", "originals": originals,
            "existing_manifest": sha(safe_regular(p["live"] / "manifest.json")),
            "bridge_id": bridge, "native_backup_basename": backup.name,
        }
        private_write(p["meta"], (json.dumps(meta, sort_keys=True) + "\n").encode())
        return {"stage": "READY", "version": NEW}
    except BaseException:
        # Do not delete state on error: forensic recovery remains possible.
        raise


def install(root: Path, ledger: Path) -> dict:
    p = paths(root, ledger, NEW)
    meta = receipt(p["meta"])
    if (meta["status"] != "STAGED" or p["displaced"].exists()
        or manifest_version(p["live"] / "manifest.json") != EXPECTED_OLD
        or sha(safe_regular(p["live"] / "manifest.json")) != meta["existing_manifest"]
        or manifest_version(p["staged"] / "manifest.json") != NEW):
        raise ValueError("install_stage_changed_or_incomplete")
    os.replace(p["live"], p["displaced"])
    os.replace(p["staged"], p["live"])
    meta["status"] = "INSTALLED_NEEDS_RESTART"
    save_receipt(p["meta"], meta)
    return {"stage": "INSTALLED_NEEDS_RESTART", "version": NEW}


def verify(root: Path, ledger: Path, *, check_health: bool = True) -> dict:
    p = paths(root, ledger, NEW)
    meta = receipt(p["meta"])
    if (meta["status"] not in ("INSTALLED_NEEDS_RESTART", "VERIFIED")
        or manifest_version(p["live"] / "manifest.json") != NEW):
        raise ValueError("candidate_not_installed")
    for rel, original_sha in meta["originals"].items():
        # The integration manifest is deliberately upgraded to 1.2.0;
        # preserve the other five original HA/YAML/HomeKit files exactly.
        if rel == f"custom_components/{DOMAIN}/manifest.json":
            continue
        if sha(safe_regular(root / rel)) != original_sha:
            raise ValueError("IDENTITY_DRIFT_or_config_entry_changed")
    if check_health and not healthy():
        raise RuntimeError("HEALTH_PENDING")
    meta["status"] = "VERIFIED"
    save_receipt(p["meta"], meta)
    return {"status": "PRODUCTION_VERIFY_PASS", "version": NEW, "identity_stable": True}


def rollback(root: Path, ledger: Path, *, restore_storage: bool = True) -> dict:
    p = paths(root, ledger, NEW)
    meta = receipt(p["meta"])
    if not p["previous"].is_dir() or manifest_version(p["previous"] / "manifest.json") != EXPECTED_OLD:
        raise ValueError("previous_component_missing")
    candidate_active = (
        p["live"].is_dir()
        and manifest_version(p["live"] / "manifest.json") == NEW
    )
    affected = candidate_active or p["displaced"].is_dir()
    if affected and restore_storage:
        # Validate all snapshots BEFORE stopping the working HA process.
        # A corrupt private guard must not cause a service outage.
        for rel, checksum in meta["originals"].items():
            if sha(safe_regular(p["guard"] / rel)) != checksum:
                raise ValueError("private_rollback_snapshot_corrupt")
        # Only stop Home Assistant if the actual install touched the live
        # component. A failed pre-install must NOT stop HA or rewrite storage.
        inspected = subprocess.run(
            ["/usr/bin/docker", "inspect", "--format", "{{.State.Running}}", "homeassistant"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=12, check=False,
        )
        if inspected.returncode != 0 or inspected.stdout.strip() not in ("true", "false"):
            raise RuntimeError("could_not_verify_homeassistant_state")
        if inspected.stdout.strip() == "true":
            stopped = subprocess.run(
                ["/usr/bin/docker", "stop", "--time", "30", "homeassistant"],
                capture_output=True, timeout=60, check=False,
            )
            if stopped.returncode != 0:
                raise RuntimeError("could_not_stop_homeassistant_for_rollback")
    if candidate_active:
        # Quarantine the canary for diagnosis; no deletion.
        quarantined = p["base"] / "failed_candidate"
        if quarantined.exists():
            raise ValueError("canary_quarantine_already_exists")
        os.replace(p["live"], quarantined)
    if p["displaced"].is_dir():
        os.replace(p["displaced"], p["live"])
    elif not p["live"].exists():
        # Separate immutable copy serves as fallback after crash.
        shutil.copytree(p["previous"], p["live"], symlinks=False)
    if manifest_version(p["live"] / "manifest.json") != EXPECTED_OLD:
        raise ValueError("previous_component_restore_failed")
    if affected and restore_storage:
        for rel, checksum in meta["originals"].items():
            blob = safe_regular(p["guard"] / rel)
            if sha(blob) != checksum:
                raise ValueError("private_rollback_snapshot_corrupt")
            dest = root / rel
            temp = dest.with_name(dest.name + ".venta-restore")
            if temp.exists() or temp.is_symlink():
                raise ValueError("unresolved_rollback_temporary_file")
            private_write(temp, blob)
            os.replace(temp, dest)
    meta["status"] = "ROLLED_BACK"
    save_receipt(p["meta"], meta)
    return {"status": "ROLLBACK_FILES_RESTORED", "version": EXPECTED_OLD}


def ensure_started() -> dict:
    inspected = subprocess.run(
        ["/usr/bin/docker", "inspect", "--format", "{{.State.Running}}", "homeassistant"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        timeout=12, check=False,
    )
    if inspected.returncode != 0:
        raise RuntimeError("ha_container_missing")
    if inspected.stdout.strip() == "false":
        launched = subprocess.run(
            ["/usr/bin/docker", "start", "homeassistant"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=60, check=False,
        )
        if launched.returncode != 0:
            raise RuntimeError("rollback_homeassistant_start_failed")
    return {"status": "HOMEASSISTANT_STARTED_OR_ALREADY_RUNNING"}


def verify_rollback(root: Path, ledger: Path, *, check_health: bool = True) -> dict:
    p = paths(root, ledger, NEW)
    meta = receipt(p["meta"])
    if meta["status"] != "ROLLED_BACK" or manifest_version(p["live"] / "manifest.json") != EXPECTED_OLD:
        raise ValueError("rollback_component_not_restored")
    for rel, checksum in meta["originals"].items():
        if sha(safe_regular(root / rel)) != checksum:
            raise ValueError("rollback_snapshot_not_restored")
    if check_health and not healthy():
        raise RuntimeError("ROLLBACK_HEALTH_PENDING")
    return {"status": "ROLLBACK_VERIFIED", "version": EXPECTED_OLD}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=(
        "preflight", "stage", "install", "verify", "rollback", "ensure-start", "verify-rollback"
    ))
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    if args.version != NEW:
        raise SystemExit("wrong_release_version")
    if os.geteuid() != 0:
        raise SystemExit("release_transaction_requires_root")
    root, ledger, scratch = DEFAULT_CONFIG, DEFAULT_LEDGER, DEFAULT_SCRATCH
    try:
        if args.phase == "preflight":
            bridge, backup = verify_baseline(args.source, root, scratch)
            result = {"status": "PREFLIGHT_PASS", "version": NEW, "backup_verified": True}
        elif args.phase == "stage":
            result = stage(args.source, root, ledger, scratch)
        elif args.phase == "install":
            result = install(root, ledger)
        elif args.phase == "verify":
            result = verify(root, ledger)
        elif args.phase == "rollback":
            result = rollback(root, ledger)
        elif args.phase == "ensure-start":
            result = ensure_started()
        else:
            result = verify_rollback(root, ledger)
    except (ValueError, RuntimeError, OSError) as exc:
        # Only fixed class identifiers are printed; no secrets, entity IDs or paths.
        tag = str(exc)
        safe = tag if re.fullmatch(r"[A-Z_a-z0-9]+", tag) else "RELEASE_GATE_FAILED"
        print(json.dumps({"status": "FAILED", "reason": safe}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
