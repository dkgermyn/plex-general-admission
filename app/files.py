from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

from .db import Database

VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mkv", ".mov", ".avi", ".webm", ".mpg", ".mpeg", ".ts"}
SAFE_NAME = re.compile(r"^[^/\\\x00]{1,255}$")


class UnsafePath(ValueError):
    pass


class FileStore:
    def __init__(self, root: Path, trash: Path, thumbnails: Path, db: Database, retention_days: int = 30):
        self.root = root.resolve()
        self.trash = trash.resolve()
        self.thumbnails = thumbnails.resolve()
        self.db = db
        self.retention_days = retention_days

    def resolve(self, relative: str = "", *, must_exist: bool = False) -> Path:
        rel = PurePosixPath(relative or ".")
        if rel.is_absolute() or ".." in rel.parts:
            raise UnsafePath("Path must stay inside the preroll root")
        candidate = (self.root / Path(*rel.parts)).resolve(strict=must_exist)
        if candidate != self.root and self.root not in candidate.parents:
            raise UnsafePath("Path escapes the preroll root")
        return candidate

    def validate_name(self, name: str) -> str:
        name = name.strip()
        if not SAFE_NAME.fullmatch(name) or name in {".", ".."}:
            raise UnsafePath("Invalid file or folder name")
        return name

    def list(self, relative: str = "") -> list[dict]:
        directory = self.resolve(relative, must_exist=True)
        if not directory.is_dir():
            raise NotADirectoryError(relative)
        items = []
        for item in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold())):
            if item.is_symlink():
                continue
            stat = item.stat()
            rel = item.relative_to(self.root).as_posix()
            items.append({
                "name": item.name, "path": rel, "is_folder": item.is_dir(),
                "size": stat.st_size if item.is_file() else None,
                "modified": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                "is_video": item.is_file() and item.suffix.casefold() in VIDEO_EXTENSIONS,
            })
        return items

    def mkdir(self, parent: str, name: str) -> str:
        target = self.resolve(parent) / self.validate_name(name)
        target.mkdir(exist_ok=False)
        return target.relative_to(self.root).as_posix()

    def move(self, source: str, destination_folder: str, new_name: str | None = None) -> str:
        src = self.resolve(source, must_exist=True)
        dest_dir = self.resolve(destination_folder, must_exist=True)
        if not dest_dir.is_dir():
            raise NotADirectoryError(destination_folder)
        name = self.validate_name(new_name) if new_name else src.name
        dest = (dest_dir / name).resolve()
        if dest.exists():
            raise FileExistsError(name)
        if src.is_dir() and (dest == src or src in dest.parents):
            raise UnsafePath("A folder cannot be moved inside itself")
        old = src.relative_to(self.root).as_posix()
        src.rename(dest)
        new = dest.relative_to(self.root).as_posix()
        with self.db.connect() as db:
            rows = db.execute("SELECT id,relative_path FROM selections").fetchall()
            for row in rows:
                path = row["relative_path"]
                if path == old or path.startswith(old + "/"):
                    db.execute("UPDATE selections SET relative_path=? WHERE id=?", (new + path[len(old):], row["id"]))
        return new

    def delete(self, relative: str) -> int:
        src = self.resolve(relative, must_exist=True)
        if src == self.root:
            raise UnsafePath("The preroll root cannot be deleted")
        now = datetime.now(UTC)
        trash_name = f"{now:%Y%m%dT%H%M%S}-{uuid.uuid4().hex}-{src.name}"
        target = self.trash / trash_name
        src.rename(target)
        with self.db.connect() as db:
            cur = db.execute(
                "INSERT INTO trash(trash_name,original_path,deleted_at,purge_after,is_folder) VALUES(?,?,?,?,?)",
                (trash_name, relative, now.isoformat(), (now + timedelta(days=self.retention_days)).isoformat(), int(target.is_dir())),
            )
            return int(cur.lastrowid)

    def restore(self, trash_id: int) -> str:
        with self.db.connect() as db:
            row = db.execute("SELECT * FROM trash WHERE id=?", (trash_id,)).fetchone()
            if not row:
                raise FileNotFoundError(trash_id)
            src = self.trash / row["trash_name"]
            dest = self.resolve(row["original_path"])
            if dest.exists():
                raise FileExistsError(row["original_path"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dest)
            db.execute("DELETE FROM trash WHERE id=?", (trash_id,))
            return row["original_path"]

    def purge_expired(self, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        count = 0
        with self.db.connect() as db:
            rows = db.execute("SELECT * FROM trash WHERE purge_after<=?", (now.isoformat(),)).fetchall()
            for row in rows:
                path = self.trash / row["trash_name"]
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
                db.execute("DELETE FROM trash WHERE id=?", (row["id"],))
                count += 1
        return count

    def video_files(self, relative: str, recursive: bool) -> list[Path]:
        base = self.resolve(relative, must_exist=True)
        if base.is_file():
            return [base] if base.suffix.casefold() in VIDEO_EXTENSIONS else []
        iterator = base.rglob("*") if recursive else base.glob("*")
        return [p for p in iterator if p.is_file() and not p.is_symlink() and p.suffix.casefold() in VIDEO_EXTENSIONS]

    def thumbnail(self, relative: str) -> Path:
        source = self.resolve(relative, must_exist=True)
        key = hashlib.sha256(f"{relative}:{source.stat().st_mtime_ns}:{source.stat().st_size}".encode()).hexdigest()
        output = self.thumbnails / f"{key}.jpg"
        if not output.exists():
            subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", "1", "-i", str(source), "-frames:v", "1", "-vf", "scale=480:-2", "-y", str(output)],
                check=True, timeout=60,
            )
        return output

