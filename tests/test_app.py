import importlib
import asyncio
import re
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
    monkeypatch.setattr(module, "resolver", Mock(effective=lambda now: ([], ["Default"])))
    for name in ("one.mp4", "two.mp4", "three.mp4"):
        (root / name).write_bytes(b"video")
    client = TestClient(module.app)
    client.post("/auth/start")
    page = client.get("/")
    assert 'data-view="details"' in page.text
    assert 'id="item-context-menu"' in page.text
    assert 'data-plex-prefix="/prerolls"' in page.text
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
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
