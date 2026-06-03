"""
game.py — Logika Dam-daman 4x8
Papan 32 slot, kiri-kanan atas-bawah:
 1  2  3  4  5  6  7  8
 9 10 11 12 13 14 15 16
17 18 19 20 21 22 23 24
25 26 27 28 29 30 31 32
"""
from typing import Optional

COLS = 8
ROWS = 4

WHITE = "W"   # putih, mulai kiri
BLACK = "B"   # hitam, mulai kanan

WHITE_START  = {1, 2, 9, 10, 17, 18, 25, 26}
BLACK_START  = {7, 8, 15, 16, 23, 24, 31, 32}
WHITE_TARGET = BLACK_START   # putih harus isi slot kanan
BLACK_TARGET = WHITE_START   # hitam harus isi slot kiri


def slot_to_rc(slot: int):
    """slot 1-32 → (row 0-3, col 0-7)"""
    s = slot - 1
    return s // COLS, s % COLS


def rc_to_slot(row: int, col: int) -> int:
    return row * COLS + col + 1


def valid(row: int, col: int) -> bool:
    return 0 <= row < ROWS and 0 <= col < COLS


class Game:
    def __init__(self, p1_id: int, p2_id: int, p1_name: str, p2_name: str):
        # P1 = putih, P2 = hitam (ditentukan random di bot)
        self.p1_id   = p1_id
        self.p2_id   = p2_id
        self.p1_name = p1_name
        self.p2_name = p2_name

        # board: slot → "W" | "B" | None
        self.board: dict[int, Optional[str]] = {i: None for i in range(1, 33)}
        for s in WHITE_START:
            self.board[s] = WHITE
        for s in BLACK_START:
            self.board[s] = BLACK

        self.turn: str = WHITE          # siapa giliran sekarang
        self.winner: Optional[str] = None
        self.selected: Optional[int] = None   # slot yang sedang dipilih

    def current_player_id(self) -> int:
        return self.p1_id if self.turn == WHITE else self.p2_id

    def color_of(self, player_id: int) -> str:
        return WHITE if player_id == self.p1_id else BLACK

    def valid_moves(self, slot: int) -> list[int]:
        """Daftar slot tujuan valid dari slot ini."""
        color = self.board.get(slot)
        if not color:
            return []
        row, col = slot_to_rc(slot)
        normal, jumps = [], []

        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = row + dr, col + dc
            if not valid(nr, nc):
                continue
            nb = rc_to_slot(nr, nc)
            if self.board[nb] is None:
                normal.append(nb)
            elif self.board[nb] != color:
                # Cek lompatan: 1 langkah lagi searah
                lr, lc = nr + dr, nc + dc
                if valid(lr, lc):
                    lb = rc_to_slot(lr, lc)
                    if self.board[lb] is None:
                        jumps.append(lb)

        # Wajib lompat jika ada kesempatan
        return jumps if jumps else normal

    def all_valid_sources(self) -> list[int]:
        """Semua slot milik pemain giliran ini yang punya gerakan valid."""
        sources = []
        for s in range(1, 33):
            if self.board[s] == self.turn and self.valid_moves(s):
                sources.append(s)
        return sources

    def move(self, frm: int, to: int) -> bool:
        """Lakukan gerakan. Return True jika valid."""
        if self.winner:
            return False
        if self.board.get(frm) != self.turn:
            return False
        if to not in self.valid_moves(frm):
            return False

        self.board[to] = self.board[frm]
        self.board[frm] = None

        # Cek menang
        color = self.board[to]
        target = WHITE_TARGET if color == WHITE else BLACK_TARGET
        if all(self.board[s] == color for s in target):
            self.winner = color
            return True

        # Ganti giliran
        self.turn = BLACK if self.turn == WHITE else WHITE
        self.selected = None
        return True

    def is_over(self) -> bool:
        return self.winner is not None

    def winner_name(self) -> str:
        if self.winner == WHITE:
            return self.p1_name
        if self.winner == BLACK:
            return self.p2_name
        return ""
