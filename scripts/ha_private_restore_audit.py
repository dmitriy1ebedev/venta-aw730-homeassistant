"""Restore and verify *selected real* Home Assistant backup files in RAM only.

No API or cloud uploads. Never writes to live HA. Any output is structural
evidence only; device credentials, pairing keys, entity names and hashes are
never logged. Full HA boot/pairing migration is a separate, gated operation.
"""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import re
import stat
import tarfile
import tempfile


BRIDGE_RE = re.compile(r"[A-Za-z0-9_-]{6,80}\Z")
MAX_MEMBER = 2 * 1024 * 1024
MAX_ARCHIVE = 1024 * 1024 * 1024


def required_paths(bridge_id: str) -> tuple[str, ...]:
    if not BRIDGE_RE.fullmatch(bridge_id):
        raise ValueError("invalid_homekit_bridge_id")
    return (
        "configuration.yaml",
        ".storage/core.config_entries",
        f".storage/homekit.{bridge_id}.aids",
        f".storage/homekit.{bridge_id}.iids",
        f".storage/homekit.{bridge_id}.state",
        "custom_components/venta_homekit_native/manifest.json",
    )


def _regular_file(path: Path, limit: int) -> bytes:
    if (
        path.is_symlink() or not path.is_file()
        or not stat.S_ISREG(path.stat().st_mode)
        or path.stat().st_size > limit
    ):
        raise ValueError("regular_file_missing_or_unsafe")
    return path.read_bytes()


def _source_parts_clean(base: Path, file: Path) -> None:
    if not base.is_dir() or base.is_symlink() or not file.is_relative_to(base):
        raise ValueError("unsafe_live_config_root")
    current = file.parent
    while current != base:
        if current.is_symlink() or not current.is_dir():
            raise ValueError("unsafe_live_config_directory")
        current = current.parent


def _read_members(archive: Path, required: tuple[str, ...]) -> dict[str, bytes]:
    if archive.is_symlink() or not archive.is_file() or not (0 < archive.stat().st_size <= MAX_ARCHIVE):
        raise ValueError("unsafe_backup_archive")
    wanted = set(required)
    result: dict[str, bytes] = {}
    with tarfile.open(archive, "r:") as outer:
        info = outer.extractfile("./backup.json")
        if info is None:
            raise ValueError("missing_native_backup_manifest")
        manifest_bytes = info.read(16385)
        if len(manifest_bytes) > 16384:
            raise ValueError("backup_manifest_oversized")
        manifest = json.loads(manifest_bytes)
        if (
            not isinstance(manifest, dict)
            or not isinstance(manifest.get("homeassistant"), dict)
            or not manifest["homeassistant"].get("version")
        ):
            raise ValueError("invalid_native_backup_manifest")
        inner = outer.extractfile("homeassistant.tar.gz")
        if inner is None:
            raise ValueError("missing_native_backup_payload")
        with tarfile.open(fileobj=inner, mode="r|gz") as contents:
            for member in contents:
                # No general-purpose extraction. Member paths never influence
                # output paths: only an exact six-file allowlist is restored.
                name = member.name.removeprefix("./").removeprefix("data/")
                if name not in wanted:
                    continue
                if (
                    name in result or not member.isfile()
                    or member.size > MAX_MEMBER
                    or member.size < 1
                ):
                    raise ValueError("invalid_or_duplicate_backup_member")
                fileobj = contents.extractfile(member)
                if fileobj is None:
                    raise ValueError("backup_member_unreadable")
                blob = fileobj.read(MAX_MEMBER + 1)
                if len(blob) != member.size:
                    raise ValueError("backup_member_size_changed")
                result[name] = blob
    if set(result) != wanted:
        raise ValueError("required_homekit_recovery_files_missing")
    return result


def audit(
    archive: Path,
    live_root: Path,
    bridge_id: str,
    *,
    scratch_root: Path,
) -> dict:
    names = required_paths(bridge_id)
    if (
        scratch_root.is_symlink()
        or not scratch_root.is_dir()
        or scratch_root.resolve().is_relative_to(live_root.resolve())
        or live_root.resolve().is_relative_to(scratch_root.resolve())
    ):
        raise ValueError("unsafe_private_restore_scratch")
    files = _read_members(archive, names)
    state_name = f".storage/homekit.{bridge_id}.state"
    pairing_state = json.loads(files[state_name])
    if (
        not isinstance(pairing_state, dict)
        or not pairing_state.get("private_key")
        or not pairing_state.get("public_key")
        or not isinstance(pairing_state.get("paired_clients"), dict)
        or not pairing_state["paired_clients"]
    ):
        raise ValueError("backup_does_not_preserve_homekit_pairing")
    entries = json.loads(files[".storage/core.config_entries"])
    if not isinstance(entries.get("data", {}).get("entries"), list):
        raise ValueError("invalid_backup_config_entries")
    component = json.loads(files["custom_components/venta_homekit_native/manifest.json"])
    if component.get("domain") != "venta_homekit_native":
        raise ValueError("not_venta_integration_backup")

    # Root audit caller uses tmpfs: /dev/shm, not persisted backup secrets.
    # Fresh directory/files are mode 0700/0600; deleted at scope exit.
    original_umask = os.umask(0o077)
    try:
        with tempfile.TemporaryDirectory(
            prefix="venta-homekit-restore-", dir=scratch_root
        ) as dirname:
            destination = Path(dirname)
            for name in names:
                live = live_root / name
                _source_parts_clean(live_root, live)
                current = _regular_file(live, MAX_MEMBER)
                relative = Path(name)
                new = destination / relative
                new.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with new.open("xb") as file:
                    file.write(files[name])
                new.chmod(0o600)
                restored = _regular_file(new, MAX_MEMBER)
                if restored != files[name] or restored != current:
                    raise AssertionError("backup_snapshot_differs_from_live_state")
    finally:
        os.umask(original_umask)
    return {
        "status": "PASS",
        "restored_in_private_scratch": len(names),
        "byte_identical_to_live": True,
        "homekit_pairing_material_present": True,
        "homekit_paired_client_count": len(pairing_state["paired_clients"]),
        "config_entries_count": len(entries["data"]["entries"]),
        "no_live_writes": True,
        "scratch_destroyed": True,
        "actual_ha_restart_tested": False,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--backup", type=Path, required=True)
    p.add_argument("--live-root", type=Path, required=True)
    p.add_argument("--bridge-entry-id", required=True)
    p.add_argument("--scratch-root", type=Path, default=Path("/dev/shm"))
    args = p.parse_args()
    print(json.dumps(audit(
        args.backup, args.live_root, args.bridge_entry_id,
        scratch_root=args.scratch_root,
    ), sort_keys=True))


if __name__ == "__main__":
    main()
