"""HTTP client for the GeekMagic SmallTV-Ultra stock firmware.

The ESP8266 is single-threaded: one request at a time, 200 ms between calls.
See docs/internals.md for the endpoints and firmware quirks.
"""

import logging
import re
import time

import requests

log = logging.getLogger(__name__)

THEME_PHOTO = 3
THEME_CLOCK = 4
IMAGE_DIR = "/image/"
_FILE_RE = re.compile(r"href='/image/([^']+)'")


class ScreenError(Exception):
    pass


class SmallTV:
    def __init__(self, host: str, timeout: float = 30, gap: float = 0.2):
        self.base = f"http://{host}"
        self.timeout = timeout
        self.gap = gap
        self._last = 0.0

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        wait = self._last + self.gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            kwargs.setdefault("timeout", self.timeout)
            r = requests.request(method, self.base + path, **kwargs)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            raise ScreenError(f"{method} {path}: {e}") from e
        finally:
            self._last = time.monotonic()

    def _set(self, **params) -> None:
        self._request("GET", "/set", params=params)

    def theme(self) -> int:
        """Current theme. Also serves as health check."""
        try:
            return int(self._request("GET", "/app.json", timeout=5).json()["theme"])
        except (ValueError, KeyError, TypeError) as e:
            raise ScreenError(f"unexpected /app.json response: {e}") from e

    def set_theme(self, theme: int) -> None:
        self._set(theme=theme)

    def set_brightness(self, value: int) -> None:
        self._set(brt=max(0, min(100, value)))

    def list_files(self) -> list[str]:
        return _FILE_RE.findall(self._request("GET", "/filelist", params={"dir": IMAGE_DIR}).text)

    def upload(self, name: str, jpeg: bytes) -> list[str]:
        """Upload the image and return the files present afterwards.

        The firmware sends a duplicated Content-Length header. requests 2.x
        accepts it, but a stricter client may fail although the upload worked,
        so /filelist has the final word.
        """
        files = {"file": (name, jpeg, "image/jpeg")}
        try:
            response = self._request("POST", "/doUpload", params={"dir": IMAGE_DIR}, files=files)
            listing = _FILE_RE.findall(response.text)
        except ScreenError as e:
            log.warning("Unreadable upload response, checking /filelist (%s)", e)
            listing = []
        if name not in listing:
            listing = self.list_files()
        if name not in listing:
            raise ScreenError(f"{name} missing on the screen after upload")
        return listing

    def show(self, name: str) -> None:
        # The double slash is part of the firmware protocol.
        self._set(img=f"{IMAGE_DIR}/{name}")

    def delete(self, name: str) -> None:
        self._request("GET", "/delete", params={"file": f"{IMAGE_DIR}/{name}"})
