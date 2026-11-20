from unittest.mock import Mock, patch

from app.plex import PlexClient


def test_serializes_random_choice_list():
    response = Mock(); response.raise_for_status.return_value = None
    with patch("app.plex.httpx.put", return_value=response) as put:
        value = PlexClient("http://plex", "secret").set_prerolls(["/prerolls/a.mp4", "/prerolls/b.mp4"])
    assert value == "/prerolls/a.mp4;/prerolls/b.mp4"
    assert put.call_args.kwargs["params"] == {"CinemaTrailersPrerollID": value}

