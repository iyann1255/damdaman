"""
renderer.py — Generate gambar papan dam-daman pakai PIL
Overlay pion di atas papan_kosong.jpg
"""
import io
import os
from typing import Optional
from PIL import Image, ImageDraw

from game import Game, WHITE, BLACK, slot_to_rc

BOARD_IMG = os.path.join(os.path.dirname(__file__), "papan_kosong.jpg")
_BASE_BOARD: Optional[Image.Image] = None

# Warna pion
COLOR_WHITE  = (255, 255, 255)
COLOR_BLACK  = (30,  30,  30)
COLOR_SEL    = (255, 215, 0)    # kuning — slot dipilih
COLOR_TARGET = (0,   200, 100)  # hijau  — slot tujuan valid

BORDER_W = 3
BORDER_B = 3


def _load_board() -> Image.Image:
    global _BASE_BOARD
    if _BASE_BOARD is None:
        _BASE_BOARD = Image.open(BOARD_IMG).convert("RGB")
    return _BASE_BOARD.copy()  # copy agar tidak termodifikasi


# Offset papan aktual (ada border di gambar)
BOARD_X1, BOARD_Y1 = 28, 31
BOARD_X2, BOARD_Y2 = 1252, 582


def _cell_bbox(row: int, col: int):
    """Bounding box (x1,y1,x2,y2) berdasarkan batas papan asli."""
    bw = BOARD_X2 - BOARD_X1
    bh = BOARD_Y2 - BOARD_Y1
    cw = bw / 8
    ch = bh / 4
    x1 = int(BOARD_X1 + col * cw)
    y1 = int(BOARD_Y1 + row * ch)
    x2 = int(BOARD_X1 + (col + 1) * cw)
    y2 = int(BOARD_Y1 + (row + 1) * ch)
    return x1, y1, x2, y2


def draw_board(game: Game, highlight_sources: list = None, highlight_targets: list = None) -> bytes:
    """
    Render papan + pion + highlight.
    highlight_sources: slot yang bisa dipilih (outline kuning)
    highlight_targets: slot tujuan valid (outline hijau)
    Return: bytes JPEG
    """
    img  = _load_board()
    draw = ImageDraw.Draw(img, "RGBA")
    W, H = img.size

    highlight_sources = set(highlight_sources or [])
    highlight_targets = set(highlight_targets or [])

    for slot in range(1, 33):
        row, col = slot_to_rc(slot)
        x1, y1, x2, y2 = _cell_bbox(row, col)
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        cw = x2 - x1
        ch = y2 - y1

        # Highlight cell
        if slot in highlight_targets:
            draw.rectangle([x1, y1, x2, y2], fill=(0, 200, 100, 80), outline=(0, 200, 100), width=4)
        elif slot in highlight_sources:
            draw.rectangle([x1, y1, x2, y2], fill=(255, 215, 0, 60), outline=(255, 215, 0), width=4)

        # Pion
        piece = game.board.get(slot)
        if piece:
            color, is_king = piece
            r = int(min(cw, ch) * 0.28)
            if color == WHITE:
                draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(240,240,240), outline=(80,80,80), width=BORDER_W)
                ri = int(r * 0.65)
                draw.ellipse([cx-ri, cy-ri, cx+ri, cy+ri], fill=None, outline=(160,160,160), width=2)
            else:
                draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(40,40,40), outline=(180,180,180), width=BORDER_B)
                ri = int(r * 0.65)
                draw.ellipse([cx-ri, cy-ri, cx+ri, cy+ri], fill=None, outline=(100,100,100), width=2)
            if is_king:
                kr = int(r * 0.35)
                draw.ellipse([cx-kr, cy-kr, cx+kr, cy+kr], fill=(255,200,0), outline=(160,120,0), width=2)



    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    buf.seek(0)
    return buf.read()
