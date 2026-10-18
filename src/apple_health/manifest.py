"""Run ids, raw-file inventories, JSON helpers and atomic publishing of warehouse layers."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apple_health import __version__

log = logging.getLogger(__name__)

STAGING = "staging"
CURATED = "curated"
DERIVED = "derived"
MARTS = "marts"
META = "_meta"


def new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def sha256_file(path: Path, bufsize: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(bufsize):
            h.update(chunk)
    return h.hexdigest()


def raw_inventory(raw_dir: Path, hash_files: bool) -> list[dict[str, Any]]:
    """Every file below ``raw_dir`` with size, mtime and (optionally) SHA-256."""
    out = []
    for p in sorted(raw_dir.rglob("*")):
        if not p.is_file():
            continue
        st = p.stat()
        out.append(
            {
                "path": p.relative_to(raw_dir).as_posix(),
                "size_bytes": st.st_size,
                "mtime_utc": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(),
                "sha256": sha256_file(p) if hash_files else None,
            }
        )
    return out


def code_version() -> str:
    """Package version plus the git commit, when available."""
    try:
        rev = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        rev, dirty = "", ""
    return f"{__version__}+{rev}{'.dirty' if dirty else ''}" if rev else __version__


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, default=str, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


@dataclass
class Workspace:
    """Outputs of one run are written below ``<warehouse>/.tmp/<run_id>/`` and published at the end.

    Publishing a layer renames the finished directory into place, so a failed run never leaves a
    half-written layer behind; the previously published layer stays intact until then.
    """

    warehouse_dir: Path
    run_id: str

    @property
    def root(self) -> Path:
        return self.warehouse_dir / ".tmp" / self.run_id

    def layer(self, name: str) -> Path:
        p = self.root / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    def published(self, name: str) -> Path:
        return self.warehouse_dir / name

    def publish(self, name: str) -> Path:
        src = self.root / name
        dst = self.published(name)
        if not src.is_dir():
            raise FileNotFoundError(f"nothing to publish for layer {name!r}: {src}")
        trash = self.warehouse_dir / ".trash" / f"{self.run_id}-{name}"
        if dst.exists():
            trash.parent.mkdir(parents=True, exist_ok=True)
            os.replace(dst, trash)
        os.replace(src, dst)
        shutil.rmtree(trash, ignore_errors=True)
        log.info("published %s -> %s", name, dst)
        return dst

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
        for d in (self.warehouse_dir / ".tmp", self.warehouse_dir / ".trash"):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
