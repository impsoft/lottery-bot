"""
Discord 첨부용 번호 이미지. embed 텍스트는 글자 크기를 키울 수 없어서 공 모양 이미지로 크게 보여준다.
이미지에는 한글 폰트가 없으므로 숫자/알파벳만 그린다. 한글 설명은 embed 텍스트에 둔다.
"""
import io
from typing import List, Optional, Sequence, Set

from PIL import Image, ImageDraw, ImageFont

_SCALE = 2  # 고해상도로 그려서 축소 표시될 때도 선명하게

BALL = 76
GAP = 12
LABEL_W = 56
PAD = 24
ROW_GAP = 14
BONUS_GAP = 30

BG = (32, 34, 37)
SEPARATOR = (70, 73, 80)
LABEL = (185, 187, 190)
DIM_BALL = (58, 61, 68)
DIM_TEXT = (120, 123, 130)
WHITE = (255, 255, 255)

# 동행복권 공 색상
_LOTTO_COLORS = [(10, (251, 196, 0)), (20, (105, 200, 242)), (30, (255, 114, 114)), (40, (140, 143, 150)), (45, (176, 216, 64))]
# 연금복권 자리별 색상 (조, 십만 ~ 일)
_WIN720_COLORS = [(90, 94, 102), (255, 114, 114), (255, 169, 77), (251, 196, 0), (105, 200, 242), (151, 117, 250), (170, 170, 170)]


def _font(size: int):
    return ImageFont.load_default(size=size * _SCALE)


def _lotto_color(n: int):
    return next(c for limit, c in _LOTTO_COLORS if n <= limit)


class _Canvas:
    def __init__(self, width: int, height: int):
        self.img = Image.new("RGB", (width * _SCALE, height * _SCALE), BG)
        self.draw = ImageDraw.Draw(self.img)

    def ball(self, x, y, fill, text, text_fill=WHITE, square=False):
        s = _SCALE
        box = (x * s, y * s, (x + BALL) * s, (y + BALL) * s)
        if square:
            self.draw.rounded_rectangle(box, radius=14 * s, fill=fill)
        else:
            self.draw.ellipse(box, fill=fill)
        cx, cy = (x + BALL / 2) * s, (y + BALL / 2) * s
        self.draw.text((cx, cy), text, font=_font(36), fill=text_fill, anchor="mm",
                       stroke_width=1 * s, stroke_fill=text_fill)

    def text(self, x, y, text, size=30, fill=LABEL):
        self.draw.text((x * _SCALE, y * _SCALE), text, font=_font(size), fill=fill, anchor="mm",
                       stroke_width=1 * _SCALE if size >= 30 else 0, stroke_fill=fill)

    def line(self, y, width):
        self.draw.line((PAD * _SCALE, y * _SCALE, (width - PAD) * _SCALE, y * _SCALE), fill=SEPARATOR, width=2 * _SCALE)

    def png(self) -> bytes:
        buf = io.BytesIO()
        self.img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()


def _width(balls: int) -> int:
    return PAD * 2 + LABEL_W + balls * BALL + (balls - 1) * GAP


def lotto(rows: Sequence[tuple], draw: Optional[Sequence[int]] = None, bonus: Optional[int] = None) -> bytes:
    """
    rows: [(label, numbers)]
    draw 가 있으면 맨 위에 당첨번호(+보너스)를 그리고, 각 줄은 맞은 번호만 색칠한다.
    """
    win: Set[int] = set(draw or [])
    width = _width(7 if draw else 6) + (BONUS_GAP if draw else 0)
    header = (BALL + ROW_GAP * 2 + 2) if draw else 0
    height = PAD * 2 + header + len(rows) * BALL + (len(rows) - 1) * ROW_GAP
    c = _Canvas(width, height)

    y = PAD
    if draw:
        x = PAD + LABEL_W
        for n in draw:
            c.ball(x, y, _lotto_color(n), str(n))
            x += BALL + GAP
        if bonus:
            c.text(x - GAP + BONUS_GAP / 2, y + BALL / 2, "+", size=34)
            c.ball(x + BONUS_GAP, y, _lotto_color(bonus), str(bonus))
        y += BALL + ROW_GAP
        c.line(y, width)
        y += ROW_GAP + 2

    for label, numbers in rows:
        c.text(PAD + LABEL_W / 2 - 6, y + BALL / 2, label, size=34)
        x = PAD + LABEL_W
        for n in numbers:
            if not draw or n in win:
                c.ball(x, y, _lotto_color(n), str(n))
            elif n == bonus:
                c.ball(x, y, DIM_BALL, str(n), text_fill=_lotto_color(n))
            else:
                c.ball(x, y, DIM_BALL, str(n), text_fill=DIM_TEXT)
            x += BALL + GAP
        y += BALL + ROW_GAP

    return c.png()


def win720(rows: Sequence[tuple], draw_group: Optional[str] = None, draw_number: Optional[str] = None) -> bytes:
    """
    rows: [(group, number)]  (group 은 '1'~'5' 또는 '1-5', number 는 6자리 문자열)
    draw_number 가 있으면 맨 위에 1등 번호를 그리고, 각 줄은 맞은 뒷자리만 색칠한다.
    """
    width = _width(7)
    header = (BALL + ROW_GAP * 2 + 2) if draw_number else 0
    height = PAD * 2 + header + len(rows) * BALL + (len(rows) - 1) * ROW_GAP
    c = _Canvas(width, height)

    def row(y, group, number, matched):
        x = PAD + LABEL_W
        c.ball(x, y, _WIN720_COLORS[0], group, square=True)
        for i, d in enumerate(number):
            x += BALL + GAP
            if i >= len(number) - matched:
                c.ball(x, y, _WIN720_COLORS[i + 1], d)
            else:
                c.ball(x, y, DIM_BALL, d, text_fill=DIM_TEXT)

    y = PAD
    if draw_number:
        c.text(PAD + LABEL_W / 2 - 6, y + BALL / 2, "1st", size=24)
        row(y, draw_group or "?", draw_number, len(draw_number))
        y += BALL + ROW_GAP
        c.line(y, width)
        y += ROW_GAP + 2

    for group, number in rows:
        matched = len(number)
        if draw_number:
            matched = 0
            for mine, drawn in zip(reversed(number), reversed(draw_number)):
                if mine != drawn:
                    break
                matched += 1
        row(y, group, number, matched)
        y += BALL + ROW_GAP

    return c.png()
