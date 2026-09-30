"""Watch moOde's metadata file and keep the SmallTV-Ultra in sync."""

import argparse
import logging
import os
import time
from datetime import datetime

from . import __version__, moode
from . import config as config_mod
from .render import Fonts, render, to_jpeg
from .smalltv import THEME_CLOCK, THEME_PHOTO, ScreenError, SmallTV

log = logging.getLogger("moode_smalltv")

POLL_S = 1
# Also catches a screen restart: it comes back on another theme.
HEALTH_S = 10
BACKOFF_MAX_S = 60
CLOCK = "clock"
# Two names in turn: the new image is shown before the old one is deleted.
NAMES = ("cover_a.jpg", "cover_b.jpg")


class Display:
    """What the screen shows. None means unknown, everything gets sent again."""

    def __init__(self, tv: SmallTV, cfg: config_mod.Config):
        self.tv = tv
        self.cfg = cfg
        self.fonts = Fonts(cfg.font_regular, cfg.font_bold)
        self.shown = None
        self.theme = None
        self.brightness = None
        self.slot = 0

    def forget(self) -> None:
        self.shown = self.theme = self.brightness = None

    def check(self) -> None:
        """Raise ScreenError if unreachable, forget the state if the theme changed."""
        theme = self.tv.theme()
        if self.theme is not None and theme != self.theme:
            log.info("Screen on theme %d instead of %d (restarted?), redrawing", theme, self.theme)
            self.forget()

    def _theme(self, theme: int) -> None:
        if self.theme != theme:
            self.tv.set_theme(theme)
            self.theme = theme

    def show_song(self, song: moode.Song) -> None:
        start = time.monotonic()
        cover = moode.fetch_cover(song, self.cfg.moode_url)
        cover_s = time.monotonic() - start
        jpeg = to_jpeg(render(song, cover, self.fonts))
        name, other = NAMES[self.slot], NAMES[1 - self.slot]
        self._theme(THEME_PHOTO)
        files = self.tv.upload(name, jpeg)
        self.tv.show(name)
        if other in files:
            self.tv.delete(other)
        self.slot = 1 - self.slot
        self.shown = song.key()
        log.info(
            "Showing %s / %s [%s] %d KB in %.1f s (cover %.1f s)",
            song.display_title,
            song.artist,
            song.state,
            len(jpeg) // 1024,
            time.monotonic() - start,
            cover_s,
        )

    def show_clock(self) -> None:
        self._theme(THEME_CLOCK)
        self.shown = CLOCK
        log.info("Clock")

    def set_brightness(self, value: int) -> None:
        if self.brightness != value:
            self.tv.set_brightness(value)
            self.brightness = value
            log.info("Brightness %d", value)


def run(cfg: config_mod.Config) -> None:
    display = Display(SmallTV(cfg.screen_host), cfg)
    song, mtime = None, None
    last_renderer_song = None  # last renderer track that had metadata
    state, state_since = None, 0.0
    retry_at, backoff = 0.0, 2.0
    health_at = 0.0

    while True:
        now = time.monotonic()
        try:
            m = os.stat(cfg.currentsong).st_mtime
            if m != mtime:
                song = moode.carry_over(moode.read(cfg.currentsong), last_renderer_song)
                mtime = m
                if song.is_renderer and song.title:
                    last_renderer_song = song
        except OSError as e:
            if mtime is not None:
                log.warning("Cannot read %s (%s)", cfg.currentsong, e)
            song, mtime = None, None

        current = song.state if song else "stop"
        if current != state:
            state, state_since = current, now
        idle_minutes = {"stop": cfg.stop_minutes, "pause": cfg.pause_minutes}.get(state)
        idle = idle_minutes is not None and now - state_since >= idle_minutes * 60
        # Stopped at startup: clock right away.
        if idle or (state == "stop" and display.shown is None):
            want = CLOCK
        elif state == "stop":
            want = display.shown
        else:
            want = song.key()

        if now >= retry_at:
            try:
                if now >= health_at:
                    health_at = now + HEALTH_S
                    display.check()
                display.set_brightness(cfg.brightness_at(datetime.now().time()))
                if want == CLOCK and display.shown != CLOCK:
                    display.show_clock()
                elif want != display.shown:
                    display.show_song(song)
                backoff = 2.0
            except ScreenError as e:
                log.warning("%s, retrying in %.0f s", e, backoff)
                display.forget()
                retry_at, health_at = now + backoff, 0.0
                backoff = min(backoff * 2, BACKOFF_MAX_S)

        time.sleep(POLL_S)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", default="/opt/moode-smalltv/config.toml")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    cfg = config_mod.load(args.config)
    log.info("moode-smalltv %s, screen %s, file %s", __version__, cfg.screen_host, cfg.currentsong)
    run(cfg)


if __name__ == "__main__":
    main()
