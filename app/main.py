from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.datastructures import FormData

from .auth import PlexAuth
from .config import Settings
from .db import Database
from .files import FileStore, UnsafePath
from .plex import PREFERENCE, PlexClient
from .scheduling import Resolver

BASE = Path(__file__).parent
settings = Settings.from_env()
settings.prepare()
db = Database(settings.data_root / "app.db")
db.initialize()
files = FileStore(settings.preroll_root, settings.trash_root, settings.data_root / "thumbnails", db, settings.trash_retention_days)
resolver = Resolver(db, files, settings.timezone, settings.plex_path_prefix)
plex = PlexClient(settings.plex_url, settings.plex_token)
auth = PlexAuth(os.getenv("PLEX_AUTH_CLIENT_ID", "plex-general-admission"), "Plex General Ad-mission", settings.public_url)
templates = Jinja2Templates(directory=BASE / "templates")


def session_secret() -> str:
    configured = os.getenv("SESSION_SECRET", "")
    if configured:
        return configured
    path = settings.data_root / "session_secret"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48))
        path.chmod(0o600)
    return path.read_text().strip()


def require_user(request: Request) -> str:
    if not settings.auth_enabled:
        return "local-admin"
    user = request.session.get("user")
    if not user:
        raise HTTPException(401, "Authentication required")
    return str(user)


def csrf(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


async def require_form(request: Request) -> tuple[str, FormData]:
    user = require_user(request)
    form = await request.form()
    if not secrets.compare_digest(str(form.get("csrf_token", "")), str(request.session.get("csrf", ""))):
        raise HTTPException(403, "Invalid CSRF token")
    return user, form


async def sync_once() -> dict:
    paths, active = resolver.effective(datetime.now(UTC))
    desired = ";".join(paths)
    if db.state("managed") != "true":
        return {"ok": True, "active": active, "paths": paths, "changed": False, "managed": False}
    if not settings.plex_token:
        db.set_state("sync_error", "Plex token is not configured")
        return {"ok": False, "active": active, "paths": paths, "error": "Plex token is not configured"}
    try:
        current = plex.preferences().get(PREFERENCE, "")
        if current != desired:
            plex.set_prerolls(paths)
        db.set_state("last_sync", datetime.now(UTC).isoformat())
        db.set_state("last_value", desired)
        db.set_state("sync_error", "")
        return {"ok": True, "active": active, "paths": paths, "changed": current != desired}
    except Exception as exc:
        db.set_state("sync_error", type(exc).__name__)
        return {"ok": False, "active": active, "paths": paths, "error": type(exc).__name__}


async def scheduler_loop() -> None:
    while True:
        await asyncio.to_thread(files.purge_expired)
        await sync_once()
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(scheduler_loop())
    yield
    task.cancel()


app = FastAPI(title="Plex General Ad-mission", version="0.4.0", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=session_secret(), https_only=settings.cookie_secure, same_site="lax")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.exception_handler(UnsafePath)
def unsafe_path_handler(_: Request, exc: UnsafePath):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(FileExistsError)
def conflict_handler(_: Request, exc: FileExistsError):
    return JSONResponse({"detail": "An item with that name already exists", "conflicts": [str(exc)]}, status_code=409)


@app.get("/healthz")
def healthz():
    database_ok = False
    try:
        with db.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        database_ok = True
    except Exception:
        pass
    payload = {"ok": database_ok, "database": database_ok, "scheduler_last_sync": db.state("last_sync") or None}
    return JSONResponse(payload, status_code=200 if database_ok else 503)


@app.get("/login", response_class=HTMLResponse)
def login(request: Request, error: str | None = None):
    return templates.TemplateResponse(request, "login.html", {"error": error})


@app.post("/auth/start")
def auth_start(request: Request):
    if not settings.auth_enabled:
        request.session["user"] = "local-admin"
        return RedirectResponse("/", 303)
    try:
        pin, state = auth.create_pin(), auth.state()
        request.session["plex_auth"] = {"pin_id": pin["id"], "state": state}
        return RedirectResponse(auth.authorization_url(pin, state), 303)
    except Exception:
        return RedirectResponse("/login?error=unavailable", 303)


@app.get("/auth/callback")
def auth_callback(request: Request, state: str):
    pending = request.session.pop("plex_auth", {})
    if not pending or not secrets.compare_digest(str(pending.get("state", "")), state):
        return RedirectResponse("/login?error=invalid", 303)
    try:
        token = auth.claim(int(pending["pin_id"]))
        identity = auth.user(token or "")
        username = str(identity.get("username") or identity.get("title") or "")
        if username.casefold() not in settings.allowed_plex_users:
            db.audit("login", username, "denied", username)
            return RedirectResponse("/login?error=denied", 303)
        request.session.clear()
        request.session["user"] = username
        db.audit("login", username, "allowed", username)
        return RedirectResponse("/", 303)
    except Exception:
        return RedirectResponse("/login?error=failed", 303)


@app.post("/logout")
async def logout(request: Request):
    await require_form(request)
    request.session.clear()
    return RedirectResponse("/login", 303)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, path: str = ""):
    try:
        user = require_user(request)
    except HTTPException:
        return RedirectResponse("/login", 303)
    items = files.list(path)
    with db.connect() as conn:
        collections = conn.execute("SELECT * FROM collections ORDER BY is_default DESC,name COLLATE NOCASE").fetchall()
        schedules = conn.execute("SELECT s.*,c.name collection_name FROM schedules s JOIN collections c ON c.id=s.collection_id ORDER BY starts_at").fetchall()
        trash = conn.execute("SELECT * FROM trash ORDER BY deleted_at DESC").fetchall()
        selections = conn.execute("SELECT s.*,c.name collection_name FROM selections s JOIN collections c ON c.id=s.collection_id ORDER BY c.name,s.relative_path").fetchall()
    effective, active = resolver.effective(datetime.now(UTC))
    return templates.TemplateResponse(request, "index.html", {
        "user": user, "csrf": csrf(request), "path": path, "items": items,
        "collections": collections, "schedules": schedules, "trash": trash, "selections": selections,
        "effective": effective, "active": active, "managed": db.state("managed") == "true",
        "sync_error": db.state("sync_error"), "plex_prefix": settings.plex_path_prefix,
    })


@app.post("/folders")
async def create_folder(request: Request):
    user, form = await require_form(request)
    created = files.mkdir(str(form.get("parent", "")), str(form.get("name", "")))
    db.audit("mkdir", created, "ok", user)
    await sync_once()
    return RedirectResponse(f"/?path={quote(str(form.get('parent', '')))}", 303)


@app.post("/move")
async def move_item(request: Request):
    user, form = await require_form(request)
    result = files.move(str(form["source"]), str(form.get("destination", "")), str(form.get("name") or "") or None)
    db.audit("move", result, "ok", user)
    await sync_once()
    return RedirectResponse("/", 303)


@app.post("/delete")
async def delete_item(request: Request):
    user, form = await require_form(request)
    target = str(form["path"])
    files.delete(target)
    db.audit("trash", target, "ok", user)
    await sync_once()
    return RedirectResponse("/", 303)


@app.post("/bulk")
async def bulk_items(request: Request):
    user, form = await require_form(request)
    paths = list(dict.fromkeys(str(value) for value in form.getlist("paths") if str(value)))
    if not paths or len(paths) > 200:
        raise HTTPException(400, "Select between 1 and 200 items")
    action = str(form.get("action", ""))
    if action == "trash":
        for path in paths:
            files.delete(path)
            db.audit("trash", path, "ok", user, "bulk")
    elif action == "move":
        destination = str(form.get("destination", ""))
        dest_dir = files.resolve(destination, must_exist=True)
        conflicts = [path for path in paths if (dest_dir / files.resolve(path, must_exist=True).name).exists()]
        if conflicts:
            return JSONResponse({"detail": "Some items already exist in that folder", "conflicts": conflicts}, status_code=409)
        for path in paths:
            result = files.move(path, destination)
            db.audit("move", result, "ok", user, "bulk")
    elif action == "collection":
        try:
            collection_id = int(str(form.get("collection_id", "")))
        except ValueError as exc:
            raise HTTPException(400, "Collection is required") from exc
        with db.connect() as conn:
            if not conn.execute("SELECT 1 FROM collections WHERE id=?", (collection_id,)).fetchone():
                raise HTTPException(404, "Collection not found")
            for path in paths:
                target = files.resolve(path, must_exist=True)
                kind = "folder" if target.is_dir() else "file"
                conn.execute(
                    "INSERT OR IGNORE INTO selections(collection_id,relative_path,kind) VALUES(?,?,?)",
                    (collection_id, path, kind),
                )
        for path in paths:
            db.audit("selection-add", path, "ok", user, "bulk")
    else:
        raise HTTPException(400, "Unsupported bulk action")
    await sync_once()
    return RedirectResponse("/", 303)


@app.post("/trash/{trash_id}/restore")
async def restore_item(trash_id: int, request: Request):
    user, _ = await require_form(request)
    restored = files.restore(trash_id)
    db.audit("restore", restored, "ok", user)
    await sync_once()
    return RedirectResponse("/", 303)


@app.post("/upload")
async def upload(
    request: Request,
    upload: list[UploadFile] = File(...),
    destination: str = Form(""),
    csrf_token: str = Form(...),
    conflict: str = Form("error"),
):
    user = require_user(request)
    if not secrets.compare_digest(csrf_token, str(request.session.get("csrf", ""))):
        raise HTTPException(403, "Invalid CSRF token")
    dest = files.resolve(destination, must_exist=True)
    names = [files.validate_name(item.filename or "upload") for item in upload]
    unsupported = [name for name in names if Path(name).suffix.casefold() not in {".mp4", ".m4v", ".mkv", ".mov", ".avi", ".webm", ".mpg", ".mpeg", ".ts"}]
    if unsupported:
        return JSONResponse({"detail": "Only supported video files can be uploaded", "conflicts": unsupported}, status_code=415)
    seen: set[str] = set()
    existing = []
    for name in names:
        if (dest / name).exists() or name in seen:
            existing.append(name)
        seen.add(name)
    if existing and conflict == "error":
        return JSONResponse({"detail": "Some files already exist", "conflicts": existing}, status_code=409)
    if conflict not in {"error", "skip", "keep_both"}:
        raise HTTPException(400, "Unsupported conflict choice")
    uploaded, skipped, reserved = [], [], {item.name for item in dest.iterdir()}
    for item in upload:
        name = files.validate_name(item.filename or "upload")
        if name in reserved:
            if conflict == "skip":
                skipped.append(name)
                continue
            if conflict == "keep_both":
                original = Path(name)
                number = 2
                while True:
                    candidate = f"{original.stem} ({number}){original.suffix}"
                    if candidate not in reserved:
                        name = candidate
                        break
                    number += 1
        target, partial = dest / name, dest / f".{name}.{secrets.token_hex(6)}.part"
        total = 0
        try:
            with partial.open("xb") as output:
                while chunk := await item.read(1024 * 1024):
                    total += len(chunk)
                    if total > settings.max_upload_bytes:
                        raise HTTPException(413, f"{name} exceeds the upload limit")
                    output.write(chunk)
            partial.rename(target)
            reserved.add(name)
            uploaded.append(name)
            db.audit("upload", target.relative_to(files.root).as_posix(), "ok", user)
        finally:
            partial.unlink(missing_ok=True)
    await sync_once()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JSONResponse({"ok": True, "uploaded": uploaded, "skipped": skipped, "destination": destination})
    return RedirectResponse(f"/?path={quote(destination)}", 303)


@app.get("/media")
def media(request: Request, path: str):
    require_user(request)
    target = files.resolve(path, must_exist=True)
    return FileResponse(target)


@app.get("/thumbnail")
def thumbnail(request: Request, path: str):
    require_user(request)
    try:
        return FileResponse(files.thumbnail(path), media_type="image/jpeg")
    except Exception:
        raise HTTPException(404, "Thumbnail unavailable")


@app.post("/collections")
async def create_collection(request: Request):
    user, form = await require_form(request)
    name = str(form.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "Collection name is required")
    with db.connect() as conn:
        conn.execute("INSERT INTO collections(name,description,is_default,created_at) VALUES(?,?,0,?)", (name, str(form.get("description", "")), datetime.now(UTC).isoformat()))
    db.audit("collection-create", name, "ok", user)
    return RedirectResponse("/", 303)


@app.post("/collections/{collection_id}/selections")
async def add_selection(collection_id: int, request: Request):
    user, form = await require_form(request)
    relative = str(form["path"])
    target = files.resolve(relative, must_exist=True)
    kind = "folder" if target.is_dir() else "file"
    with db.connect() as conn:
        conn.execute("INSERT OR IGNORE INTO selections(collection_id,relative_path,kind) VALUES(?,?,?)", (collection_id, relative, kind))
    db.audit("selection-add", relative, "ok", user)
    await sync_once()
    return RedirectResponse("/", 303)


@app.post("/selections/{selection_id}/delete")
async def remove_selection(selection_id: int, request: Request):
    user, _ = await require_form(request)
    with db.connect() as conn:
        row = conn.execute("SELECT relative_path FROM selections WHERE id=?", (selection_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Selection not found")
        conn.execute("DELETE FROM selections WHERE id=?", (selection_id,))
    db.audit("selection-remove", row["relative_path"], "ok", user)
    await sync_once()
    return RedirectResponse("/", 303)


@app.post("/schedules")
async def create_schedule(request: Request):
    user, form = await require_form(request)
    now = datetime.now(UTC).isoformat()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO schedules(name,description,color,collection_id,starts_at,ends_at,rrule,exdates,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,1,?,?)",
            (str(form["name"]), str(form.get("description", "")), str(form.get("color", "#7c3aed")), int(form["collection_id"]),
             str(form["starts_at"]), str(form["ends_at"]), str(form.get("rrule") or "") or None, "[]", now, now),
        )
    db.audit("schedule-create", str(form["name"]), "ok", user)
    await sync_once()
    return RedirectResponse("/", 303)


@app.post("/schedules/{schedule_id}/delete")
async def delete_schedule(schedule_id: int, request: Request):
    user, _ = await require_form(request)
    with db.connect() as conn:
        row = conn.execute("SELECT name FROM schedules WHERE id=?", (schedule_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Schedule not found")
        conn.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
    db.audit("schedule-delete", row["name"], "ok", user)
    await sync_once()
    return RedirectResponse("/", 303)


@app.post("/sync")
async def manual_sync(request: Request):
    user, _ = await require_form(request)
    result = await sync_once()
    db.audit("plex-sync", ",".join(result["active"]), "ok" if result["ok"] else "failed", user)
    return RedirectResponse("/", 303)


@app.post("/setup/import")
async def import_existing(request: Request):
    user, _ = await require_form(request)
    if db.state("managed") == "true":
        raise HTTPException(409, "Plex preference is already managed")
    if not settings.plex_token:
        raise HTTPException(400, "Plex token is not configured")
    current = plex.preferences().get(PREFERENCE, "")
    paths = [value.strip() for value in current.split(";") if value.strip()]
    imported = 0
    with db.connect() as conn:
        default = conn.execute("SELECT id FROM collections WHERE is_default=1").fetchone()
        for plex_path in paths:
            prefix = settings.plex_path_prefix + "/"
            if not plex_path.startswith(prefix):
                continue
            relative = plex_path[len(prefix):]
            try:
                target = files.resolve(relative, must_exist=True)
            except (UnsafePath, FileNotFoundError):
                continue
            if target.is_file():
                conn.execute("INSERT OR IGNORE INTO selections(collection_id,relative_path,kind) VALUES(?,?,?)", (default["id"], relative, "file"))
                imported += 1
    db.set_state("managed", "true")
    db.audit("takeover", "Plex preroll preference", "ok", user, f"imported={imported}")
    await sync_once()
    return RedirectResponse("/", 303)


@app.get("/api/calendar")
def calendar(request: Request):
    require_user(request)
    with db.connect() as conn:
        rows = conn.execute("SELECT id,name,color,starts_at,ends_at,rrule,enabled FROM schedules ORDER BY starts_at").fetchall()
    return [dict(row) for row in rows]
