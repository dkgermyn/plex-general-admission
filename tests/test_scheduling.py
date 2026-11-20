from datetime import UTC, datetime

from app.db import Database
from app.files import FileStore
from app.scheduling import Resolver, schedule_active


def setup(tmp_path):
    root, trash, thumbs = tmp_path / "p", tmp_path / "t", tmp_path / "h"
    root.mkdir(); trash.mkdir(); thumbs.mkdir(); db = Database(tmp_path / "db"); db.initialize()
    return db, FileStore(root, trash, thumbs, db)


def test_one_off_and_annual_recurrence():
    one = {"enabled": 1, "starts_at": "2026-12-01T00:00", "ends_at": "2026-12-26T00:00", "rrule": None, "exdates": "[]"}
    recurring = one | {"rrule": "FREQ=YEARLY"}
    assert schedule_active(one, datetime(2026, 12, 10, tzinfo=UTC), "UTC")
    assert not schedule_active(one, datetime(2027, 12, 10, tzinfo=UTC), "UTC")
    assert schedule_active(recurring, datetime(2027, 12, 10, tzinfo=UTC), "UTC")


def test_overlap_union_and_default_fallback(tmp_path):
    db, files = setup(tmp_path)
    (files.root / "default.mp4").touch(); (files.root / "A").mkdir(); (files.root / "A" / "a.mp4").touch(); (files.root / "B").mkdir(); (files.root / "B" / "b.mkv").touch()
    now = datetime(2026, 12, 10, tzinfo=UTC)
    with db.connect() as conn:
        default = conn.execute("SELECT id FROM collections WHERE is_default=1").fetchone()[0]
        conn.execute("INSERT INTO selections(collection_id,relative_path,kind) VALUES(?,?,?)", (default, "default.mp4", "file"))
        ids = []
        for name, folder in (("A", "A"), ("B", "B")):
            cid = conn.execute("INSERT INTO collections(name,created_at) VALUES(?,?)", (name, now.isoformat())).lastrowid; ids.append(cid)
            conn.execute("INSERT INTO selections(collection_id,relative_path,kind) VALUES(?,?,?)", (cid, folder, "folder"))
            conn.execute("INSERT INTO schedules(name,collection_id,starts_at,ends_at,enabled,created_at,updated_at) VALUES(?,?,?,?,1,?,?)", (name, cid, "2026-12-01T00:00", "2026-12-26T00:00", now.isoformat(), now.isoformat()))
    resolver = Resolver(db, files, "UTC", "/prerolls")
    assert resolver.effective(now) == (["/prerolls/A/a.mp4", "/prerolls/B/b.mkv"], ["A", "B"])
    assert resolver.effective(datetime(2026, 11, 1, tzinfo=UTC))[0] == ["/prerolls/default.mp4"]

