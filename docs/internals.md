# Internals

Notes for maintainers. Read this before touching `moode.py` or `smalltv.py`.

## Code layout

| File | Role |
|---|---|
| `moode_smalltv/config.py` | Loads `config.toml`, rejects unknown keys, night brightness |
| `moode_smalltv/moode.py` | Parses `currentsong.txt`, builds and fetches the cover URL |
| `moode_smalltv/render.py` | Draws the 240x240 picture with Pillow |
| `moode_smalltv/smalltv.py` | HTTP client for the screen |
| `moode_smalltv/main.py` | Main loop, decides what to show, retries |

The main loop runs every second. It works out what the screen should show (a track key or the clock), compares it with what it last sent, and only talks to the screen when they differ. Any screen error resets that memory, so everything is sent again once the screen answers.

## What this relies on in moOde

Checked against moOde 10.2.0, `/var/www/daemon/worker.php` function `updExtMetaFile()` and `/var/www/inc/mpd.php`. A moOde update that changes one of these points will need a code change and a new test fixture.

| Behaviour | Where it is handled |
|---|---|
| The file is `/var/local/www/currentsong.txt`, `key=value` lines, written only when "Metadata file" is on | `config.currentsong` |
| moOde rewrites the file about every 3 s, only when something changed, through a temp file and `rename` | mtime polling in `main.run` |
| MPD playback writes `state=play`, `pause` or `stop` | `moode.parse` |
| Renderers write `file=<Name> Active` and **no** `state` line. `<Name>` is AirPlay, Spotify, Deezer, Squeezelite, Roonbridge, Bluetooth or `<input> Input` | `RENDERER_SUFFIX` |
| Only AirPlay and Spotify Connect add artist, album, title and `coverurl` | `Song.display_title` falls back to the renderer name |
| A paused renderer is rewritten as `file=<Name> Active` and `outrate=Not playing`, all metadata gone | `RENDERER_IDLE`, `moode.carry_over` keeps the last track |
| Web radio uses `artist=Radio station`, the station in `album`, the stream title in `title` | `DEFAULT_STATION_NAME` |
| A stream without title yet gets `title=Radio station` | `Song.display_title` shows the station |
| `coverurl` is `/coverart.php/<rawurlencoded path>`, a relative `imagesw%2F...` logo path, or a full `https://` URL for renderers | `moode.cover_url` |
| `coverart.php` answers `302` to `/images/default-album-cover.jpg` when there is no cover | `DEFAULT_COVER_MARKER` |

The service never writes anything in moOde's folders or settings.

## SmallTV-Ultra HTTP API

Stock firmware, plain HTTP on port 80, no authentication. Checked on `Ultra-V9.0.54`. Source: [geekmagic-stats device protocol](https://docs.rs/crate/geekmagic-stats/latest/source/device-protocol.md), plus our own tests.

| Call | Use |
|---|---|
| `GET /v.json` | Model and firmware, `{"m":"SmallTV-Ultra","v":"Ultra-V9.0.54"}` |
| `GET /app.json` | Current theme, `{"theme":3}`. Used as health check |
| `GET /set?theme=3` | Photo album theme. `4` is the clock |
| `POST /doUpload?dir=/image/` | Multipart upload, field `file`. The answer is the file list |
| `GET /set?img=/image//<name>` | Show a picture. The double slash is required |
| `GET /delete?file=/image//<name>` | Delete a picture |
| `GET /filelist?dir=/image/` | HTML list of pictures |
| `GET /set?brt=<0-100>` | Brightness. `GET /brt.json` reads it back |
| `GET /space.json` | Storage, `{"total":3121152,"free":1236492}` |

Firmware quirks and limits.

- **No resizing.** A picture larger than 240x240 is cropped from the top left corner. `render.py` always outputs exactly 240x240.
- **About 1.2 MB of free storage.** Two names are used in turn (`cover_a.jpg`, `cover_b.jpg`), the old one is deleted after the new one is shown. Other pictures on the screen are never touched.
- **Duplicated `Content-Length`** on the upload answer (`Content-Length: 3579, 3579`). `requests` 2.32 and 2.34 accept it (the only versions tried). If a future version refuses it, `SmallTV.upload` still checks `/filelist` before calling it a failure.
- **Single-threaded ESP8266.** One request at a time, 200 ms between calls, 30 s timeout. Another app polling the screen will slow both down.
- Covers weigh 3 to 30 KB at JPEG quality 85. Measured 1.5 to 3 s per change, cover download and upload included.
- `/app.json` does not say which picture is displayed, and `/album.json` does not change when `/set?img` is used.

## Known limits

- A screen restart is detected when the screen comes back on another theme than the one the service set, or when it is unreachable during a health check (every 10 s). A very short restart that brings the screen back on the photo theme may show a stale picture until the next track change.
- Detection latency is moOde's own update loop (about 3 s) plus up to 1 s of polling, plus the upload.
- The Pi has no real-time clock. Right after boot, before NTP sync, the time is wrong and so is the night brightness, for a few seconds.

## Release checklist

1. `python -m unittest -v`, `ruff check .`, `ruff format --check .`
2. Deploy on a real Pi and screen, check the logs for play, pause, next track, radio, stop.
3. Bump `__version__` in `moode_smalltv/__init__.py` and add a `CHANGELOG.md` entry.
