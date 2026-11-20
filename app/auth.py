from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx


class PlexAuth:
    API = "https://plex.tv/api/v2"
    AUTH = "https://app.plex.tv/auth"

    def __init__(self, client_id: str, product: str, public_url: str):
        self.client_id, self.product, self.public_url = client_id, product, public_url

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json", "X-Plex-Client-Identifier": self.client_id,
            "X-Plex-Product": self.product, "X-Plex-Version": "1.0", "X-Plex-Platform": "Web",
        }

    def create_pin(self) -> dict:
        response = httpx.post(f"{self.API}/pins", headers=self.headers, params={"strong": "true"}, timeout=15)
        response.raise_for_status()
        return response.json()

    def authorization_url(self, pin: dict, state: str) -> str:
        callback = f"{self.public_url}/auth/callback?{urlencode({'state': state})}"
        query = urlencode({
            "clientID": self.client_id, "code": pin["code"], "forwardUrl": callback,
            "context[device][product]": self.product,
        })
        return f"{self.AUTH}#?{query}"

    def claim(self, pin_id: int) -> str | None:
        response = httpx.get(f"{self.API}/pins/{pin_id}", headers=self.headers, timeout=15)
        response.raise_for_status()
        return response.json().get("authToken")

    def user(self, token: str) -> dict:
        response = httpx.get(f"{self.API}/user", headers=self.headers | {"X-Plex-Token": token}, timeout=15)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def state() -> str:
        return secrets.token_urlsafe(32)

