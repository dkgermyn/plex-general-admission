from __future__ import annotations

import httpx

PREFERENCE = "CinemaTrailersPrerollID"


class PlexClient:
    def __init__(self, base_url: str, token: str, timeout: float = 10):
        self.base_url, self.token, self.timeout = base_url, token, timeout

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Plex-Token": self.token, "Accept": "application/json"}

    def identity(self) -> dict:
        response = httpx.get(f"{self.base_url}/identity", headers=self.headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def preferences(self) -> dict:
        response = httpx.get(f"{self.base_url}/:/prefs", headers=self.headers, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        settings = data.get("MediaContainer", {}).get("Setting", [])
        return {item.get("id"): item.get("value", "") for item in settings}

    def set_prerolls(self, paths: list[str]) -> str:
        value = ";".join(paths)
        response = httpx.put(
            f"{self.base_url}/:/prefs", headers=self.headers,
            params={PREFERENCE: value}, timeout=self.timeout,
        )
        response.raise_for_status()
        return value

