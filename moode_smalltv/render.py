import io

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .moode import Song

SIZE = 240
PAD = 10
BAND_ALPHA = 175  # white text on this band stays above 6:1 contrast, even on a white cover
BG_EMPTY = (24, 24, 28)
WHITE = (255, 255, 255)
GREY = (200, 200, 205)


class Fonts:
    def __init__(self, regular: str, bold: str):
        self.title = ImageFont.truetype(bold, 18)
        self.text = ImageFont.truetype(regular, 16)
        self.big = ImageFont.truetype(bold, 20)


def truncate(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> str:
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int, max_lines: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [" ".join(lines[max_lines - 1 :])]
    return [truncate(draw, line, font, width) for line in lines]


def _band(img: Image.Image, fonts: Fonts, line1: str, line2: str, title_lines: int) -> Image.Image:
    width = SIZE - 2 * PAD
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    lines = [(t, fonts.title, WHITE) for t in wrap(draw, line1, fonts.title, width, title_lines)]
    if line2:
        lines.append((truncate(draw, line2, fonts.text, width), fonts.text, GREY))
    if not lines:
        return img
    line_h = 24
    top = SIZE - PAD - line_h * len(lines) - 4
    draw.rectangle((0, top - PAD + 4, SIZE, SIZE), fill=(0, 0, 0, BAND_ALPHA))
    for i, (text, font, color) in enumerate(lines):
        draw.text((PAD, top + i * line_h), text, font=font, fill=color)
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _empty(fonts: Fonts, title: str, artist: str, album: str) -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), BG_EMPTY)
    draw = ImageDraw.Draw(img)
    width = SIZE - 2 * PAD
    rows = [(line, fonts.big, WHITE, 26) for line in wrap(draw, title, fonts.big, width, 3)]
    rows += [
        (truncate(draw, t, fonts.text, width), fonts.text, GREY, 22) for t in (artist, album) if t
    ]
    y = (SIZE - sum(h for *_, h in rows)) // 2
    for text, font, color, h in rows:
        draw.text((SIZE // 2, y), text, font=font, fill=color, anchor="ma")
        y += h
    return img


def _pause_icon(img: Image.Image) -> Image.Image:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy, r = SIZE - 28, 28, 20
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(0, 0, 0, 190))
    draw.rectangle((cx - 8, cy - 10, cx - 3, cy + 10), fill=WHITE)
    draw.rectangle((cx + 3, cy - 10, cx + 8, cy + 10), fill=WHITE)
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def render(song: Song, cover: Image.Image | None, fonts: Fonts) -> Image.Image:
    if song.is_radio:
        # Station name is in "album", stream title in "title".
        subtitle = song.album if song.album != song.display_title else ""
        rows = (song.display_title, subtitle, "")
    else:
        rows = (song.display_title, song.artist, song.album)

    if cover is not None:
        # Radio: the stream title is the only useful info, give it 2 lines.
        img = ImageOps.fit(cover, (SIZE, SIZE), Image.LANCZOS)
        img = _band(img, fonts, rows[0], rows[1], title_lines=2 if song.is_radio else 1)
    else:
        img = _empty(fonts, *rows)
    if song.state == "pause":
        img = _pause_icon(img)
    return img


def to_jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()
