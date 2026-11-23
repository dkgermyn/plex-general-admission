import importlib
import asyncio
import re
from pathlib import Path
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.db import Database
from app.files import FileStore


def test_application_imports(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("PREROLL_ROOT", str(tmp_path / "prerolls"))
    monkeypatch.setenv("TRASH_ROOT", str(tmp_path / "trash"))
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    module = importlib.import_module("app.main")
    assert module.app.title == "Plex General Ad-mission"


def test_preview_cleanup_covers_mobile_exit_paths():
    script = (Path(__file__).parents[1] / "app" / "static" / "app.js").read_text()
    assert "video.pause()" in script
    assert "video.removeAttribute('src')" in script
    assert "videoDialog.addEventListener('close', stopPreview)" in script
    assert "window.addEventListener('pagehide', stopPreview)" in script
    assert "visibilitychange" in script


def test_v04_library_controls_cover_touch_filter_drag_and_uploads():
    script = (Path(__file__).parents[1] / "app" / "static" / "app.js").read_text()
    template = (Path(__file__).parents[1] / "app" / "templates" / "index.html").read_text()
    assert "enterSelection(item)" in script
    assert "data-library-search" in template
    assert "preferenceKey('view')" in script
    assert "addEventListener('drop'" in script
    assert "request.upload.addEventListener('progress'" in script
    assert "data-conflict-choice=\"keep_both\"" in template


def test_v06_management_ui_timezone_colors_and_recurrence_are_present():
    script = (Path(__file__).parents[1] / "app" / "static" / "app.js").read_text()
    template = (Path(__file__).parents[1] / "app" / "templates" / "index.html").read_text()
    assert "activateTab(new URLSearchParams(location.search).get('tab')" in script
    assert "fetch(`/api/calendar?year=${year}&month=${month + 1}`)" in script
    assert "custom.hidden = !isCustom" in script
    assert "rrule.value = recurrence.value" in script
    assert "A custom rule must begin with FREQ=" in script
    assert "data-edit-collection" in template
    assert "data-add-members" in template
    assert "data-edit-schedule" in template
    assert "data-collection-filter" in template
    assert "Unassigned" in template
    assert 'data-tab="settings"' in template
    assert 'action="/settings/timezone"' in template
    assert "data-color-control" in template


def test_v07_schedule_intelligence_ui_is_present():
    script = (Path(__file__).parents[1] / "app" / "static" / "app.js").read_text()
    template = (Path(__file__).parents[1] / "app" / "templates" / "index.html").read_text()
    assert "data-play-inspector" in template
    assert "data-new-schedule" in template
    assert 'name="overlap_policy"' in template
    assert 'name="priority"' in template
    assert "createFromSelection" in script
    assert "calendar-event-span" in script
    assert "laneCounts" in script
    assert "/bounds" in script
    assert "openScheduleEditor(schedule)" in script


def test_existing_database_migrates_collection_colors(tmp_path):
    import sqlite3

    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE collections (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT NOT NULL DEFAULT '', is_default INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)")
    connection.execute("CREATE TABLE schedules (id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '#7c3aed', collection_id INTEGER NOT NULL, starts_at TEXT NOT NULL, ends_at TEXT NOT NULL, rrule TEXT, exdates TEXT NOT NULL DEFAULT '[]', enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
    connection.execute("INSERT INTO collections(name,is_default,created_at) VALUES('Default',1,'2026-01-01')")
    connection.commit()
    connection.close()
    database = Database(path)
    database.initialize()
    with database.connect() as migrated:
        row = migrated.execute("SELECT name,color FROM collections").fetchone()
        assert dict(row) == {"name": "Default", "color": "#64748b"}
        schedule_columns = {column["name"] for column in migrated.execute("PRAGMA table_info(schedules)")}
        assert {"priority", "overlap_policy"} <= schedule_columns


def test_sync_does_not_touch_plex_before_takeover(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("PREROLL_ROOT", str(tmp_path / "prerolls"))
    monkeypatch.setenv("TRASH_ROOT", str(tmp_path / "trash"))
    module = importlib.import_module("app.main")
    module.db.set_state("managed", "false")
    monkeypatch.setattr(module.resolver, "effective", lambda now: (["/prerolls/a.mp4"], ["Default"]))
    preferences = Mock()
    monkeypatch.setattr(module.plex, "preferences", preferences)
    result = asyncio.run(module.sync_once())
    assert result["managed"] is False
    preferences.assert_not_called()


def test_bulk_move_collection_and_trash(monkeypatch, tmp_path):
    module = importlib.import_module("app.main")
    root, trash, thumbs = tmp_path / "prerolls", tmp_path / "trash", tmp_path / "thumbs"
    root.mkdir(); trash.mkdir(); thumbs.mkdir(); (root / "Moved").mkdir()
    database = Database(tmp_path / "app.db"); database.initialize()
    store = FileStore(root, trash, thumbs, database)
    monkeypatch.setattr(module, "db", database)
    monkeypatch.setattr(module, "files", store)
    monkeypatch.setattr(module, "resolver", Mock(
        effective=lambda now: ([], ["Default"]),
        inspect=lambda now: {"explanation": "Fallback", "paths": [], "schedules": [], "empty_collections": []},
        collection_paths=lambda connection, collection_id: [],
    ))
    for name in ("one.mp4", "two.mp4", "three.mp4"):
        (root / name).write_bytes(b"video")
    client = TestClient(module.app)
    client.post("/auth/start")
    page = client.get("/")
    assert 'data-view="details"' in page.text
    assert 'id="item-context-menu"' in page.text
    assert 'data-plex-prefix="/prerolls"' in page.text
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    (root / "Moved" / "one.mp4").write_bytes(b"conflict")
    response = client.post("/bulk", data={
        "csrf_token": csrf, "action": "move", "destination": "Moved",
        "paths": ["one.mp4", "two.mp4"],
    })
    assert response.status_code == 409
    assert (root / "one.mp4").exists() and (root / "two.mp4").exists()
    (root / "Moved" / "one.mp4").unlink()
    response = client.post("/bulk", data={
        "csrf_token": csrf, "action": "move", "destination": "Moved",
        "paths": ["one.mp4", "two.mp4"],
    })
    assert response.status_code == 200
    assert (root / "Moved" / "one.mp4").exists()
    with database.connect() as connection:
        default_id = connection.execute("SELECT id FROM collections WHERE is_default=1").fetchone()[0]
    response = client.post("/bulk", data={
        "csrf_token": csrf, "action": "collection",
        "collection_id": str(default_id), "paths": ["three.mp4"],
    })
    assert response.status_code == 200
    with database.connect() as connection:
        assert connection.execute("SELECT relative_path FROM selections").fetchone()[0] == "three.mp4"
    response = client.post("/bulk", data={
        "csrf_token": csrf, "action": "trash",
        "paths": ["Moved/one.mp4", "Moved/two.mp4"],
    })
    assert response.status_code == 200
    assert not (root / "Moved" / "one.mp4").exists()

    (root / "upload.mp4").write_bytes(b"old")
    response = client.post(
        "/upload",
        data={"csrf_token": csrf, "destination": "", "conflict": "error"},
        files={"upload": ("upload.mp4", b"new", "video/mp4")},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code == 409
    assert (root / "upload.mp4").read_bytes() == b"old"
    response = client.post(
        "/upload",
        data={"csrf_token": csrf, "destination": "", "conflict": "keep_both"},
        files={"upload": ("upload.mp4", b"new", "video/mp4")},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code == 200
    assert response.json()["uploaded"] == ["upload (2).mp4"]
    assert (root / "upload (2).mp4").read_bytes() == b"new"
