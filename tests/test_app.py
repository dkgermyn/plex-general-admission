import importlib


def test_application_imports(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("PREROLL_ROOT", str(tmp_path / "prerolls"))
    monkeypatch.setenv("TRASH_ROOT", str(tmp_path / "trash"))
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    module = importlib.import_module("app.main")
    assert module.app.title == "Plex General Ad-mission"
