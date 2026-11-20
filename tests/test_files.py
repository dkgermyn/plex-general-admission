from datetime import UTC, datetime, timedelta

import pytest

from app.db import Database
from app.files import FileStore, UnsafePath


@pytest.fixture
def store(tmp_path):
    root, trash, thumbs = tmp_path / "prerolls", tmp_path / "trash", tmp_path / "thumbs"
    root.mkdir(); trash.mkdir(); thumbs.mkdir()
    db = Database(tmp_path / "app.db"); db.initialize()
    return FileStore(root, trash, thumbs, db, 30)


def test_confines_paths_and_ignores_symlinks(store, tmp_path):
    with pytest.raises(UnsafePath): store.resolve("../secret")
    (store.root / "escape").symlink_to(tmp_path)
    with pytest.raises(UnsafePath): store.resolve("escape/file")
    assert store.list() == []


def test_move_updates_nested_selection_paths(store):
    (store.root / "Holiday" / "Nested").mkdir(parents=True)
    with store.db.connect() as db:
        collection = db.execute("SELECT id FROM collections WHERE is_default=1").fetchone()["id"]
        db.execute("INSERT INTO selections(collection_id,relative_path,kind) VALUES(?,?,?)", (collection, "Holiday", "folder"))
        db.execute("INSERT INTO selections(collection_id,relative_path,kind) VALUES(?,?,?)", (collection, "Holiday/Nested/a.mp4", "file"))
    store.move("Holiday", "", "Christmas")
    with store.db.connect() as db:
        values = {r[0] for r in db.execute("SELECT relative_path FROM selections")}
    assert values == {"Christmas", "Christmas/Nested/a.mp4"}


def test_trash_restore_and_expiry(store):
    target = store.root / "a.mp4"; target.write_bytes(b"video")
    trash_id = store.delete("a.mp4")
    assert not target.exists()
    assert store.restore(trash_id) == "a.mp4"
    second = store.delete("a.mp4")
    assert store.purge_expired(datetime.now(UTC) + timedelta(days=31)) == 1
    with pytest.raises(FileNotFoundError): store.restore(second)


def test_recursive_video_resolution(store):
    (store.root / "Season" / "nested").mkdir(parents=True)
    (store.root / "Season" / "a.mp4").touch(); (store.root / "Season" / "nested" / "b.mkv").touch()
    (store.root / "Season" / "notes.txt").touch()
    assert {p.name for p in store.video_files("Season", True)} == {"a.mp4", "b.mkv"}
    assert {p.name for p in store.video_files("Season", False)} == {"a.mp4"}

