"""Fail closed on obvious public-repository secrets and private artifacts.

Scans the tracked Git tree, never reads HA runtime files or external systems.
Only path names are shown in errors; matching content is never printed.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_NAMES = {
    "secrets.yaml", "id_rsa", "id_ed25519", "credentials.json",
    "home-assistant_v2.db", "auth.json",
}
FORBIDDEN_SUFFIXES = (
    ".pem", ".p12", ".pfx", ".key", ".sqlite", ".sqlite3", ".db",
    ".zip", ".7z", ".tar", ".tar.gz", ".tgz",
)
CONTENT_SIGNATURES = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
    re.compile(rb"\bghp_[A-Za-z0-9]{30,}\b"),
    re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    re.compile(rb"\bsk-proj-[A-Za-z0-9_-]{32,}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9]{32,}\b"),
    re.compile(
        rb"(?im)^\s*(?:local_key|access_token|refresh_token|client_secret|password)"
        rb"\s*[:=]\s*[\"']?[A-Za-z0-9+/_=-]{20,}"
    ),
)
TEXT_SUFFIXES = {
    ".md", ".txt", ".py", ".js", ".ts", ".json", ".yaml", ".yml",
    ".toml", ".sh", ".xml", ".svg", ".ini", ".cfg", ".html", ".go", ".mod", ".sum",
}


def scan_paths(root: Path, relative_files: list[str]) -> list[str]:
    problems: list[str] = []
    for rel in relative_files:
        path = root / rel
        parts = Path(rel).parts
        if not parts or Path(rel).is_absolute() or ".." in parts:
            problems.append("Unsafe tracked path: " + rel)
            continue
        if (
            ".storage" in parts
            or ".git" in parts
            or path.name.lower() in FORBIDDEN_NAMES
            or path.name.lower().startswith(".env")
            or path.name.lower().endswith(FORBIDDEN_SUFFIXES)
        ):
            problems.append("Private file tracked: " + rel)
            continue
        if path.is_symlink():
            problems.append("Tracked symlink requires manual review: " + rel)
            continue
        if not path.is_file():
            problems.append("Missing tracked file: " + rel)
            continue
        if path.stat().st_size > 8_000_000:
            problems.append("Oversized tracked file: " + rel)
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        data = path.read_bytes()
        if any(pattern.search(data) for pattern in CONTENT_SIGNATURES):
            problems.append("Credential-like content in tracked file: " + rel)
    return problems


def tracked_files(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=10, check=True,
    )
    return sorted(
        item.decode("utf-8", "surrogateescape")
        for item in completed.stdout.split(b"\0") if item
    )


def main() -> int:
    try:
        errors = scan_paths(ROOT, tracked_files(ROOT))
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print("Security scan could not be completed:", type(exc).__name__)
        return 1
    for error in errors:
        print("SECURITY:", error)
    if errors:
        return 1
    print("Publication security scan: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
