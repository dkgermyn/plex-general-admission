from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_root: Path
    preroll_root: Path
    trash_root: Path
    plex_url: str
    plex_token: str
    plex_path_prefix: str
    timezone: str
    public_url: str
    allowed_plex_users: tuple[str, ...]
    auth_enabled: bool
    cookie_secure: bool
    trash_retention_days: int
    max_upload_bytes: int

    @classmethod
    def from_env(cls) -> "Settings":
        users = tuple(x.strip().casefold() for x in os.getenv("ALLOWED_PLEX_USERS", "").split(",") if x.strip())
        return cls(
            data_root=Path(os.getenv("DATA_ROOT", "/app/data")),
            preroll_root=Path(os.getenv("PREROLL_ROOT", "/prerolls")),
            trash_root=Path(os.getenv("TRASH_ROOT", "/trash")),
            plex_url=os.getenv("PLEX_URL", "http://host.docker.internal:32400").rstrip("/"),
            plex_token=os.getenv("PLEX_TOKEN", ""),
            plex_path_prefix=os.getenv("PLEX_PATH_PREFIX", "/prerolls").rstrip("/"),
            timezone=os.getenv("TZ", "UTC"),
            public_url=os.getenv("PUBLIC_URL", "http://localhost:8080").rstrip("/"),
            allowed_plex_users=users,
            auth_enabled=_bool("AUTH_ENABLED", True),
            cookie_secure=_bool("SESSION_COOKIE_SECURE", True),
            trash_retention_days=max(1, int(os.getenv("TRASH_RETENTION_DAYS", "30"))),
            max_upload_bytes=max(1, int(os.getenv("MAX_UPLOAD_BYTES", str(4 * 1024**3)))),
        )

    def prepare(self) -> None:
        for path in (self.data_root, self.preroll_root, self.trash_root, self.data_root / "thumbnails"):
            path.mkdir(parents=True, exist_ok=True)

