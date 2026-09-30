import tomllib
from dataclasses import dataclass, fields
from datetime import time


@dataclass(frozen=True)
class Config:
    screen_host: str = "192.168.1.100"
    moode_url: str = "http://localhost"
    currentsong: str = "/var/local/www/currentsong.txt"
    stop_minutes: float = 5
    pause_minutes: float = 1
    brightness_day: int = 80
    brightness_night: int = 20
    night_start: str = "22:00"
    night_end: str = "07:00"
    font_regular: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font_bold: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    def brightness_at(self, now: time) -> int:
        start = time.fromisoformat(self.night_start)
        end = time.fromisoformat(self.night_end)
        if start <= end:
            night = start <= now < end
        else:
            night = now >= start or now < end
        return self.brightness_night if night else self.brightness_day


def load(path: str) -> Config:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    known = {f.name for f in fields(Config)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"Unknown keys in {path}: {', '.join(sorted(unknown))}")
    return Config(**data)
