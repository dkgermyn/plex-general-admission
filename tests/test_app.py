import importlib
import asyncio
from unittest.mock import Mock


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
