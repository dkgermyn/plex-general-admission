from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr

from .db import Database
from .files import FileStore


def parse_local(value: str, timezone: str) -> datetime:
    result = datetime.fromisoformat(value)
    return result.replace(tzinfo=ZoneInfo(timezone)) if result.tzinfo is None else result.astimezone(ZoneInfo(timezone))


def schedule_active(row, now: datetime, timezone: str) -> bool:
    if not row["enabled"]:
        return False
    start = parse_local(row["starts_at"], timezone)
    end = parse_local(row["ends_at"], timezone)
    now = now.astimezone(ZoneInfo(timezone))
    if not row["rrule"]:
        return start <= now < end
    duration = end - start
    rule = rrulestr(row["rrule"], dtstart=start)
    occurrence = rule.before(now, inc=True)
    if occurrence is None or not occurrence <= now < occurrence + duration:
        return False
    exdates = {parse_local(x, timezone) for x in Database.decode_exdates(row["exdates"])}
    return occurrence not in exdates


def schedule_overlaps(row, window_start: datetime, window_end: datetime, timezone: str) -> bool:
    if not row["enabled"]:
        return False
    start = parse_local(row["starts_at"], timezone)
    end = parse_local(row["ends_at"], timezone)
    window_start = window_start.astimezone(ZoneInfo(timezone))
    window_end = window_end.astimezone(ZoneInfo(timezone))
    if not row["rrule"]:
        return start < window_end and end > window_start
    duration = end - start
    occurrence = rrulestr(row["rrule"], dtstart=start).before(window_end, inc=False)
    if occurrence is None or occurrence < start or occurrence + duration <= window_start:
        return False
    exdates = {parse_local(x, timezone) for x in Database.decode_exdates(row["exdates"])}
    return occurrence not in exdates


class Resolver:
    def __init__(self, db: Database, files: FileStore, timezone: str, plex_prefix: str):
        self.db, self.files, self.timezone, self.plex_prefix = db, files, timezone, plex_prefix

    def effective(self, now: datetime) -> tuple[list[str], list[str]]:
        with self.db.connect() as db:
            schedules = db.execute("SELECT * FROM schedules WHERE enabled=1 ORDER BY id").fetchall()
            active = [row for row in schedules if schedule_active(row, now, self.timezone)]
            if active:
                collection_ids = {row["collection_id"] for row in active}
                names = [row["name"] for row in active]
            else:
                default = db.execute("SELECT id FROM collections WHERE is_default=1").fetchone()
                collection_ids = {default["id"]} if default else set()
                names = ["Default"] if default else []
            resolved: set[str] = set()
            for collection_id in collection_ids:
                rows = db.execute("SELECT relative_path,kind FROM selections WHERE collection_id=?", (collection_id,)).fetchall()
                for selection in rows:
                    try:
                        paths = self.files.video_files(selection["relative_path"], recursive=selection["kind"] == "folder")
                    except (FileNotFoundError, NotADirectoryError):
                        continue
                    resolved.update(path.relative_to(self.files.root).as_posix() for path in paths)
        plex_paths = [f"{self.plex_prefix}/{relative}" for relative in sorted(resolved, key=str.casefold)]
        return plex_paths, names
