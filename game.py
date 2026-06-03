"""
game.py — Dam-daman 4x8 (aturan checkers klasik)
Papan:
 1  2  3  4  5  6  7  8
 9 10 11 12 13 14 15 16
17 18 19 20 21 22 23 24
25 26 27 28 29 30 31 32

Putih (W): start col 0-1, maju ke kanan (col+), target col 6-7.
Hitam (B): start col 6-7, maju ke kiri  (col-), target col 0-1.

Pion biasa : gerak maju (depan + diagonal depan), tidak boleh mundur.
Raja (K)   : gerak bebas semua arah, jarak tak terbatas.
Lompat     : ada musuh di tengah, mendarat di slot kosong di baliknya.
Wajib lompat jika ada kesempatan.
"""
from typing import Optional

COLS = 8
ROWS = 4

WHITE = "W"
BLACK = "B"

WHITE_START  = {1, 2, 9, 10, 17, 18, 25, 26}
BLACK_START  = {7, 8, 15, 16, 23, 24, 31, 32}
WHITE_TARGET = BLACK_START
BLACK_TARGET = WHITE_START

# Arah col "maju" per warna
FORWARD_DC = {WHITE: 1, BLACK: -1}

# 8 arah untuk raja
DIRS_8 = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]


def slot_to_rc(slot: int):
    s = slot - 1
    return s // COLS, s % COLS


def rc_to_slot(row: int, col: int) -> int:
    return row * COLS + col + 1


def valid(row: int, col: int) -> bool:
    return 0 <= row < ROWS and 0 <= col < COLS


class Game:
    def __init__(self, p1_id: int, p2_id: int, p1_name: str, p2_name: str):
        self.p1_id, self.p2_id     = p1_id, p2_id
        self.p1_name, self.p2_name = p1_name, p2_name

        # board: slot → (color, is_king) | None
        self.board: dict[int, Optional[tuple[str, bool]]] = {i: None for i in range(1, 33)}
        for s in WHITE_START:
            self.board[s] = (WHITE, False)
        for s in BLACK_START:
            self.board[s] = (BLACK, False)

        self.turn: str = WHITE
        self.winner: Optional[str] = None
        self.selected: Optional[int] = None
        self.jumping: Optional[int] = None       # slot yang sedang multi-jump
        self.captured_this_turn: set[int] = set()

    def current_player_id(self) -> int:
        return self.p1_id if self.turn == WHITE else self.p2_id

    def color_of(self, player_id: int) -> str:
        return WHITE if player_id == self.p1_id else BLACK

    # ── Lompatan ──────────────────────────────────────────────────────────────

    def _jump_moves(self, slot: int) -> list[tuple[int,int]]:
        """Return (landing_slot, captured_slot)."""
        piece = self.board[slot]
        if not piece:
            return []
        color, is_king = piece
        row, col = slot_to_rc(slot)
        result = []

        if is_king:
            for dr, dc in DIRS_8:
                r, c = row + dr, col + dc
                enemy_slot = None
                while valid(r, c):
                    s = rc_to_slot(r, c)
                    p = self.board[s]
                    if p is None:
                        if enemy_slot and enemy_slot not in self.captured_this_turn:
                            result.append((s, enemy_slot))
                    elif p[0] != color and s not in self.captured_this_turn:
                        if enemy_slot:
                            break
                        enemy_slot = s
                    else:
                        break
                    r, c = r + dr, c + dc
        else:
            fdc = FORWARD_DC[color]
            for dr, dc in DIRS_8:
                mr, mc = row + dr, col + dc
                lr, lc = row + 2*dr, col + 2*dc
                if not (valid(mr, mc) and valid(lr, lc)):
                    continue
                mid  = rc_to_slot(mr, mc)
                land = rc_to_slot(lr, lc)
                mp = self.board[mid]
                if mp and mid not in self.captured_this_turn and self.board[land] is None:
                    is_enemy = mp[0] != color
                    # Lompat kawan hanya boleh ke arah maju (dc searah forward)
                    if not is_enemy and (dc * fdc) <= 0:
                        continue
                    result.append((land, mid if is_enemy else None))
        return result

    def _normal_moves(self, slot: int) -> list[int]:
        piece = self.board[slot]
        if not piece:
            return []
        color, is_king = piece
        row, col = slot_to_rc(slot)
        result = []
        if is_king:
            for dr, dc in DIRS_8:
                r, c = row + dr, col + dc
                while valid(r, c):
                    s = rc_to_slot(r, c)
                    if self.board[s] is None:
                        result.append(s)
                    else:
                        break
                    r, c = r + dr, c + dc
        else:
            for dr, dc in DIRS_8:
                nr, nc = row + dr, col + dc
                if valid(nr, nc):
                    nb = rc_to_slot(nr, nc)
                    if self.board[nb] is None:
                        result.append(nb)
        return result

    # ── Publik ────────────────────────────────────────────────────────────────

    def valid_moves(self, slot: int) -> list[int]:
        piece = self.board[slot]
        if not piece:
            return []
        if self.jumping is not None:
            if slot != self.jumping:
                return []
            return [land for land, _ in self._jump_moves(slot)]
        jumps = self._jump_moves(slot)
        if jumps:
            return [land for land, _ in jumps]
        return self._normal_moves(slot)

    def all_valid_sources(self) -> list[int]:
        if self.jumping is not None:
            return [self.jumping]
        # Wajib lompat hanya jika ada capture musuh
        jumpers = [s for s in range(1, 33)
                   if self.board[s] and self.board[s][0] == self.turn
                   and any(cap for _, cap in self._jump_moves(s))]
        if jumpers:
            return jumpers
        return [s for s in range(1, 33)
                if self.board[s] and self.board[s][0] == self.turn and self.valid_moves(s)]

    def move(self, frm: int, to: int) -> bool:
        if self.winner:
            return False
        piece = self.board.get(frm)
        if not piece or piece[0] != self.turn:
            return False
        if to not in self.valid_moves(frm):
            return False

        jump_map = {land: cap for land, cap in self._jump_moves(frm)}
        is_jump  = to in jump_map
        color    = piece[0]

        # Cek promosi
        _, to_col = slot_to_rc(to)
        promote = (color == WHITE and to_col >= 6) or (color == BLACK and to_col <= 1)
        self.board[to]  = (color, piece[1] or promote)
        self.board[frm] = None

        if is_jump:
            cap = jump_map[to]
            if cap is not None:
                self.captured_this_turn.add(cap)
                self.board[cap] = None

            if self._jump_moves(to):
                self.jumping  = to
                self.selected = to
                return True

            self.captured_this_turn.clear()
            self.jumping = None

        # Cek menang
        target = WHITE_TARGET if color == WHITE else BLACK_TARGET
        if all(self.board[s] and self.board[s][0] == color for s in target):
            self.winner = color
            return True

        self.turn     = BLACK if self.turn == WHITE else WHITE
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
