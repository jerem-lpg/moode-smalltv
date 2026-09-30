"""Read moOde's metadata file and fetch cover art.

Everything here depends on how moOde writes /var/local/www/currentsong.txt
(worker.php, updExtMetaFile). See docs/internals.md before changing it.
"""

import io
import logging
from dataclasses import dataclass, replace
from urllib.parse import quote, unquote

import requests
from PIL import Image

log = logging.getLogger(__name__)

# Generic cover moOde redirects to when it has none.
DEFAULT_COVER_MARKER = "default-album-cover"
# Values written by moOde (constants.php and worker.php).
DEFAULT_STATION_NAME = "Radio station"
RENDERER_SUFFIX = " Active"
RENDERER_IDLE = "Not playing"


@dataclass(frozen=True)
class Song:
    title: str = ""
    artist: str = ""
    album: str = ""
    state: str = "stop"
    coverurl: str = ""
    file: str = ""

    @property
    def is_radio(self) -> bool:
        return self.artist == DEFAULT_STATION_NAME

    @property
    def is_renderer(self) -> bool:
        return self.file.endswith(RENDERER_SUFFIX)

    @property
    def display_title(self) -> str:
        if self.is_radio and self.title == DEFAULT_STATION_NAME:
            # Stream without a title (yet): moOde writes a placeholder, show the station.
            return self.album
        # Renderers (Bluetooth, AirPlay...) often only fill "file".
        return self.title or self.file.removesuffix(RENDERER_SUFFIX)

    def key(self) -> tuple:
        """Everything that changes the image. Same key, no new upload."""
        return (self.display_title, self.artist, self.album, self.state, self.coverurl)


def parse(text: str) -> Song:
    values = {}
    for line in text.splitlines():
        k, sep, v = line.partition("=")
        if sep:
            values[k.strip()] = v.strip()
    # Renderers (Spotify Connect, Bluetooth...) write no "state" but "file=<Name> Active".
    # When paused, moOde only writes "file" and "outrate=Not playing".
    if values.get("file", "").endswith(RENDERER_SUFFIX):
        default_state = "pause" if values.get("outrate") == RENDERER_IDLE else "play"
    else:
        default_state = "stop"
    state = values.get("state", default_state)
    if state not in ("play", "pause", "stop"):
        state = "stop"
    return Song(
        title=values.get("title", ""),
        artist=values.get("artist", ""),
        album=values.get("album", ""),
        state=state,
        coverurl=values.get("coverurl", ""),
        file=values.get("file", ""),
    )


def carry_over(new: Song, previous: Song | None) -> Song:
    """A paused renderer loses its metadata, so keep the previous track of that renderer."""
    if (
        new.is_renderer
        and new.state == "pause"
        and not new.title
        and previous is not None
        and previous.file == new.file
    ):
        return replace(previous, state="pause")
    return new


def read(path: str) -> Song:
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse(f.read())


def cover_url(coverurl: str, base: str) -> str | None:
    if not coverurl or DEFAULT_COVER_MARKER in coverurl:
        return None
    if coverurl.startswith(("http://", "https://")):
        return coverurl
    path = coverurl.lstrip("/")
    if not path.startswith("coverart.php"):
        # Static file (radio logos): moOde encodes all of it, "/" included.
        path = quote(unquote(path), safe="/")
    # coverart.php expects its argument encoded exactly as moOde provides it.
    return f"{base.rstrip('/')}/{path}"


def fetch_cover(song: Song, base: str) -> Image.Image | None:
    url = cover_url(song.coverurl, base)
    if url is None:
        return None
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        # coverart.php redirects to the generic cover when it finds none.
        if DEFAULT_COVER_MARKER in r.url:
            return None
        img = Image.open(io.BytesIO(r.content))
        img.load()
        return img.convert("RGB")
    except (requests.RequestException, OSError) as e:
        log.warning("No cover from %s (%s)", url, e)
        return None
