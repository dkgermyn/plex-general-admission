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

    @staticmethod
    def value(row, key: str, default=None):
        return row[key] if key in row.keys() else default

    def collection_paths(self, connection, collection_id: int) -> list[str]:
        resolved: set[str] = set()
        rows = connection.execute("SELECT relative_path,kind FROM selections WHERE collection_id=?", (collection_id,)).fetchall()
        for selection in rows:
            try:
                paths = self.files.video_files(selection["relative_path"], recursive=selection["kind"] == "folder")
            except (FileNotFoundError, NotADirectoryError):
                continue
            resolved.update(path.relative_to(self.files.root).as_posix() for path in paths)
        return sorted(resolved, key=str.casefold)

    def inspect(self, now: datetime) -> dict:
        with self.db.connect() as db:
            schedules = db.execute(
                "SELECT s.*,c.name collection_name FROM schedules s JOIN collections c ON c.id=s.collection_id WHERE s.enabled=1 ORDER BY s.priority DESC,s.id"
            ).fetchall()
            candidates = [row for row in schedules if schedule_active(row, now, self.timezone)]
            exclusive = [row for row in candidates if self.value(row, "overlap_policy", "combine") == "exclusive"]
            cutoff = max((self.value(row, "priority", 0) for row in exclusive), default=None)
            selected = [row for row in candidates if cutoff is None or self.value(row, "priority", 0) >= cutoff]
            fallback = not candidates
            if fallback:
                default = db.execute("SELECT id,name FROM collections WHERE is_default=1").fetchone()
                selected_collections = [(default["id"], default["name"])] if default else []
            else:
                selected_collections = list(dict.fromkeys((row["collection_id"], row["collection_name"]) for row in selected))
            collection_cache = {collection_id: self.collection_paths(db, collection_id) for collection_id, _ in selected_collections}
            resolved = sorted({path for paths in collection_cache.values() for path in paths}, key=str.casefold)
            candidate_details = []
            selected_ids = {row["id"] for row in selected}
            for row in candidates:
                paths = self.collection_paths(db, row["collection_id"])
                is_selected = row["id"] in selected_ids
                candidate_details.append({
                    "id": row["id"], "name": row["name"], "collection_id": row["collection_id"],
                    "collection_name": row["collection_name"], "priority": self.value(row, "priority", 0),
                    "overlap_policy": self.value(row, "overlap_policy", "combine"), "selected": is_selected,
                    "video_count": len(paths),
                    "reason": "Included" if is_selected else f"Suppressed below exclusive priority {cutoff}",
                })
        if fallback:
            explanation = "No schedule is active, so the Default collection is used."
        elif cutoff is not None:
            explanation = f"Exclusive priority {cutoff} suppresses lower-priority schedules; equal and higher priorities remain eligible."
        elif len(candidates) > 1:
            explanation = "All active schedules use Combine, so their collections are merged and duplicates are removed."
        else:
            explanation = "One schedule is active."
        return {
            "timezone": self.timezone, "at": now.astimezone(ZoneInfo(self.timezone)).isoformat(),
            "fallback": fallback, "conflict": len(candidates) > 1, "exclusive_cutoff": cutoff,
            "explanation": explanation, "schedules": candidate_details,
            "collections": [{"id": collection_id, "name": name, "video_count": len(collection_cache.get(collection_id, []))} for collection_id, name in selected_collections],
            "paths": [f"{self.plex_prefix}/{relative}" for relative in resolved],
            "empty_collections": [name for collection_id, name in selected_collections if not collection_cache.get(collection_id)],
        }

    def effective(self, now: datetime) -> tuple[list[str], list[str]]:
        result = self.inspect(now)
        names = [row["name"] for row in result["schedules"] if row["selected"]]
        if result["fallback"]:
            names = [row["name"] for row in result["collections"]]
        return result["paths"], names
