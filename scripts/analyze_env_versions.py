#!/usr/bin/env python3
"""Analyze environment packages against pyproject and uv.lock.

Usage:
  python scripts/analyze_env_versions.py
"""

from __future__ import annotations

import importlib.metadata as md
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
UV_LOCK = ROOT / "uv.lock"
REQ_RE = re.compile(r"^([A-Za-z0-9_.-]+)")


def parse_req_name(req: str) -> str:
    match = REQ_RE.match(req.strip())
    if not match:
        return req.strip().lower()
    return match.group(1).lower().replace("_", "-")


def load_pyproject_deps() -> tuple[list[str], list[str]]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = data.get("project", {})
    runtime = [parse_req_name(item) for item in project.get("dependencies", [])]
    dev = [parse_req_name(item) for item in project.get("optional-dependencies", {}).get("dev", [])]
    return runtime, dev


def load_lock_versions() -> dict[str, str]:
    if not UV_LOCK.exists():
        return {}
    data = tomllib.loads(UV_LOCK.read_text(encoding="utf-8"))
    packages = data.get("package", [])
    return {
        pkg["name"].lower().replace("_", "-"): pkg["version"]
        for pkg in packages
        if "name" in pkg and "version" in pkg
    }


def installed_version(name: str) -> str | None:
    try:
        return md.version(name)
    except md.PackageNotFoundError:
        return None


def render_section(title: str, names: list[str], lock: dict[str, str]) -> None:
    print(f"\n{title}") # noqa: T201
    print("-" * len(title)) # noqa: T201
    print(f"{'package':30} {'installed':15} {'uv.lock':15} {'status'}") # noqa: T201
    print("-" * 75) # noqa: T201
    for name in sorted(set(names)):
        installed = installed_version(name)
        locked = lock.get(name)
        if installed is None:
            status = "MISSING"
            installed_display = "-"
        elif locked and installed != locked:
            status = "DIFF_FROM_LOCK"
            installed_display = installed
        else:
            status = "OK"
            installed_display = installed
        print(f"{name:30} {installed_display:15} {(locked or '-'):15} {status}") # noqa: T201


def main() -> None:
    runtime, dev = load_pyproject_deps()
    lock = load_lock_versions()

    print(f"Project root: {ROOT}") # noqa: T201
    print(f"Python: {md.version('pip') if installed_version('pip') else 'unknown'} (pip)") # noqa: T201

    render_section("Runtime dependencies", runtime, lock)
    render_section("Dev dependencies", dev, lock)


if __name__ == "__main__":
    main()
