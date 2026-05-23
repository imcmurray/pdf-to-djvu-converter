"""Filesystem-backed share-link storage with TTL purge.

Each stored conversion lives under `<STORAGE_DIR>/<token>/output.djvu` plus a sibling
`meta.json`. A background task sweeps expired entries.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class StoredConversion:
    token: str
    djvu_path: Path
    filename: str
    created_at: float


class ShareStore:
    def __init__(self, base_dir: Path, ttl_seconds: int):
        self.base_dir = base_dir
        self.ttl_seconds = ttl_seconds
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._sweeper_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def put(
        self,
        djvu_path: Path,
        original_name: str,
        *,
        ocr_text_pages: list[str] | None = None,
    ) -> StoredConversion:
        token = secrets.token_urlsafe(16)
        target_dir = self.base_dir / token
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / "output.djvu"
        shutil.copyfile(djvu_path, target_file)
        meta = {
            "filename": original_name,
            "created_at": time.time(),
        }
        (target_dir / "meta.json").write_text(json.dumps(meta))
        if ocr_text_pages:
            (target_dir / "ocr_text.json").write_text(
                json.dumps({"pages": ocr_text_pages})
            )
        return StoredConversion(
            token=token,
            djvu_path=target_file,
            filename=original_name,
            created_at=meta["created_at"],
        )

    # --- OCR text helpers ---------------------------------------------------
    def has_ocr_text(self, token: str) -> bool:
        return (self.base_dir / token / "ocr_text.json").exists()

    def get_ocr_text_page(self, token: str, page: int) -> str | None:
        path = self.base_dir / token / "ocr_text.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        pages = data.get("pages", [])
        if 1 <= page <= len(pages):
            return pages[page - 1]
        return None

    def get(self, token: str) -> Optional[StoredConversion]:
        target_dir = self.base_dir / token
        meta_path = target_dir / "meta.json"
        djvu_path = target_dir / "output.djvu"
        if not (meta_path.exists() and djvu_path.exists()):
            return None
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        if time.time() - meta["created_at"] > self.ttl_seconds:
            self._remove(target_dir)
            return None
        return StoredConversion(
            token=token,
            djvu_path=djvu_path,
            filename=meta.get("filename", "converted.djvu"),
            created_at=meta["created_at"],
        )

    # ------------------------------------------------------------------ #
    # Sweeper
    # ------------------------------------------------------------------ #
    async def start_sweeper(self, interval: int = 300) -> None:
        async def _loop() -> None:
            while True:
                try:
                    self._sweep_once()
                except Exception:  # pragma: no cover - defensive
                    logger.exception("share-store sweep failed")
                await asyncio.sleep(interval)

        self._sweeper_task = asyncio.create_task(_loop(), name="share-store-sweeper")

    async def stop_sweeper(self) -> None:
        if self._sweeper_task is not None:
            self._sweeper_task.cancel()
            try:
                await self._sweeper_task
            except (asyncio.CancelledError, Exception):
                pass

    def _sweep_once(self) -> None:
        now = time.time()
        for child in self.base_dir.iterdir():
            if not child.is_dir():
                continue
            # In-flight conversion working directories created by
            # tempfile.TemporaryDirectory(prefix="pdf2djvu-") live (or used to
            # live) under the same parent. Never touch them — they're owned by
            # the request that created them and cleaned up via its `with` block.
            if child.name.startswith("pdf2djvu-") or child.name.startswith("tmp"):
                continue
            meta_path = child / "meta.json"
            if not meta_path.exists():
                # Orphan share-token dir without metadata — remove.
                self._remove(child)
                continue
            try:
                meta = json.loads(meta_path.read_text())
            except (OSError, json.JSONDecodeError):
                self._remove(child)
                continue
            if now - meta.get("created_at", 0) > self.ttl_seconds:
                self._remove(child)

    def _remove(self, path: Path) -> None:
        try:
            shutil.rmtree(path)
        except FileNotFoundError:
            pass
