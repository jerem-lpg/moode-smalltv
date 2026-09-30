import os
import unittest
from dataclasses import replace
from datetime import time
from pathlib import Path

from PIL import Image

from moode_smalltv import config, moode
from moode_smalltv.config import Config
from moode_smalltv.main import Display
from moode_smalltv.render import Fonts, render, to_jpeg

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
BASE = "http://localhost"


def fixture(name: str) -> moode.Song:
    return moode.read(str(FIXTURES / name))


def fonts() -> Fonts:
    cfg = Config()
    if os.name == "nt":
        return Fonts("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf")
    return Fonts(cfg.font_regular, cfg.font_bold)


class ParseTest(unittest.TestCase):
    def test_local(self):
        s = fixture("local.txt")
        self.assertEqual(
            (s.title, s.artist, s.album, s.state),
            ("Since I Lost My Baby", "The Temptations", "Vintage Gold", "play"),
        )
        self.assertFalse(s.is_radio)

    def test_radio(self):
        s = fixture("radio.txt")
        self.assertTrue(s.is_radio)
        self.assertEqual(s.album, "RCO Live")

    def test_renderer_minimal_file(self):
        s = fixture("bluetooth.txt")
        self.assertEqual((s.display_title, s.artist, s.state), ("Bluetooth", "", "play"))

    def test_spotify_without_state(self):
        s = fixture("spotify.txt")
        self.assertEqual((s.title, s.artist, s.state), ("Nothing Changes", "MGMT", "play"))
        self.assertTrue(moode.cover_url(s.coverurl, BASE).startswith("https://i.scdn.co/"))

    def test_spotify_pause_keeps_previous_song(self):
        playing = fixture("spotify.txt")
        paused = moode.carry_over(fixture("spotify_pause.txt"), playing)
        self.assertEqual(
            (paused.title, paused.coverurl, paused.state),
            (playing.title, playing.coverurl, "pause"),
        )
        # A second pause file in a row still keeps the track.
        self.assertEqual(moode.carry_over(fixture("spotify_pause.txt"), paused), paused)

    def test_spotify_pause_without_previous(self):
        s = moode.carry_over(fixture("spotify_pause.txt"), fixture("local.txt"))
        self.assertEqual((s.display_title, s.state), ("Spotify", "pause"))

    def test_radio_without_stream_title_shows_station(self):
        self.assertEqual(fixture("radio_notitle.txt").display_title, "FIP")

    def test_value_with_equal_sign_and_garbage(self):
        s = moode.parse("title=a=b\nnonsense\nstate=weird\n")
        self.assertEqual((s.title, s.state), ("a=b", "stop"))

    def test_key_changes_with_state(self):
        s = fixture("local.txt")
        self.assertNotEqual(s.key(), replace(s, state="pause").key())
        self.assertEqual(s.key(), fixture("local.txt").key())


class CoverUrlTest(unittest.TestCase):
    def test_coverart_php_kept_encoded(self):
        url = moode.cover_url(fixture("local.txt").coverurl, BASE)
        self.assertEqual(
            url,
            BASE + "/coverart.php/NAS%2FFlacs%2FThe%20Temptations%2FVintage%20Gold"
            "%2F04%20-%20Since%20I%20Lost%20My%20Baby.flac",
        )

    def test_relative_static_decoded(self):
        self.assertEqual(
            moode.cover_url("imagesw%2Fradio-logos%2FRCO%20Live.jpg", BASE),
            BASE + "/imagesw/radio-logos/RCO%20Live.jpg",
        )

    def test_relative_static_not_encoded(self):
        self.assertEqual(
            moode.cover_url("imagesw/radio-logos/RCO Live.jpg", BASE + "/"),
            BASE + "/imagesw/radio-logos/RCO%20Live.jpg",
        )

    def test_none(self):
        self.assertIsNone(moode.cover_url("", BASE))
        self.assertIsNone(moode.cover_url("images/default-album-cover.png", BASE))

    def test_absolute_http(self):
        self.assertEqual(moode.cover_url("http://x/y.jpg", BASE), "http://x/y.jpg")


class BrightnessTest(unittest.TestCase):
    def test_night_over_midnight(self):
        cfg = Config(brightness_day=80, brightness_night=20, night_start="22:00", night_end="07:00")
        self.assertEqual(cfg.brightness_at(time(23, 0)), 20)
        self.assertEqual(cfg.brightness_at(time(6, 59)), 20)
        self.assertEqual(cfg.brightness_at(time(7, 0)), 80)
        self.assertEqual(cfg.brightness_at(time(12, 0)), 80)


class ConfigTest(unittest.TestCase):
    def test_example_config_loads(self):
        cfg = config.load(str(ROOT / "config.example.toml"))
        self.assertEqual(cfg.stop_minutes, 5)

    def test_unknown_key_rejected(self):
        bad = FIXTURES / "bad.toml"
        bad.write_text('screen_hots = "1.2.3.4"\n', encoding="utf-8")
        try:
            with self.assertRaises(ValueError):
                config.load(str(bad))
        finally:
            bad.unlink()


class FakeTV:
    def __init__(self, theme):
        self.current = theme

    def theme(self):
        return self.current


class DisplayCheckTest(unittest.TestCase):
    def test_theme_change_forgets_state(self):
        tv = FakeTV(3)
        d = Display.__new__(Display)
        d.tv, d.shown, d.theme, d.brightness = tv, ("x",), 3, 80
        d.check()
        self.assertEqual(d.shown, ("x",))
        tv.current = 4  # screen restarted on its own theme
        d.check()
        self.assertIsNone(d.shown)
        self.assertIsNone(d.brightness)


class RenderTest(unittest.TestCase):
    def test_all_cases_240_jpeg(self):
        f = fonts()
        cover = Image.new("RGB", (500, 400), (250, 250, 250))
        long = moode.Song(title="T" * 200, artist="A" * 200, album="B" * 200, state="pause")
        cases = [
            (fixture("local.txt"), cover),
            (fixture("radio.txt"), cover),
            (fixture("bluetooth.txt"), None),
            (fixture("radio_notitle.txt"), None),
            (long, None),
            (long, cover),
            (moode.Song(), None),
        ]
        for song, c in cases:
            img = render(song, c, f)
            self.assertEqual(img.size, (240, 240))
            self.assertLess(len(to_jpeg(img)), 60_000)


if __name__ == "__main__":
    unittest.main()
