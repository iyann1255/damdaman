"""
game.py — Dam-daman 4x8
Papan:
 1  2  3  4  5  6  7  8
 9 10 11 12 13 14 15 16
17 18 19 20 21 22 23 24
25 26 27 28 29 30 31 32

Putih (W): start col 0-1, maju ke kanan (col+), target col 6-7.
Hitam (B): start col 6-7, maju ke kiri  (col-), target col 0-1.

Gerak biasa: maju lurus + menyamping (atas/bawah), 1 langkah.
Lompat    : diagonal ke depan, melewati bidak apapun, mendarat di slot kosong.
             Bidak yang dilompati TIDAK dihapus.
Menang    : semua 8 slot target terisi pion sendiri.
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

FORWARD_DC = {WHITE: 1, BLACK: -1}

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

        self.board: dict[int, Optional[tuple[str, bool]]] = {i: None for i in range(1, 33)}
        for s in WHITE_START:
            self.board[s] = (WHITE, False)
        for s in BLACK_START:
            self.board[s] = (BLACK, False)

        self.turn: str = WHITE
        self.winner: Optional[str] = None
        self.selected: Optional[int] = None

    def current_player_id(self) -> int:
        return self.p1_id if self.turn == WHITE else self.p2_id

    # ── Gerakan ───────────────────────────────────────────────────────────────

    def _jump_moves(self, slot: int) -> list[int]:
        """Lompat diagonal ke depan (melewati bidak apapun)."""
        piece = self.board[slot]
        if not piece:
            return []
        color, _ = piece
        row, col = slot_to_rc(slot)
        fdc = FORWARD_DC[color]
        result = []
        for dr, dc in DIRS_8:
            if dc * fdc <= 0:
                continue
            mr, mc = row + dr, col + dc
            lr, lc = row + 2*dr, col + 2*dc
            if not (valid(mr, mc) and valid(lr, lc)):
                continue
            mid  = rc_to_slot(mr, mc)
            land = rc_to_slot(lr, lc)
            if self.board[mid] and self.board[land] is None:
                result.append(land)
        return result

    def _normal_moves(self, slot: int) -> list[int]:
        """Gerak 1 langkah: maju lurus + menyamping (atas/bawah)."""
        piece = self.board[slot]
        if not piece:
            return []
        color, _ = piece
        row, col = slot_to_rc(slot)
        fdc = FORWARD_DC[color]
        result = []
        for dr, dc in DIRS_8:
            if dc == fdc and dr == 0:
                pass  # maju lurus
            elif dc == 0:
                pass  # menyamping
            else:
                continue
            nr, nc = row + dr, col + dc
            if valid(nr, nc):
                nb = rc_to_slot(nr, nc)
                if self.board[nb] is None:
                    result.append(nb)
        return result

    def valid_moves(self, slot: int) -> list[int]:
        return self._normal_moves(slot) + self._jump_moves(slot)

    def find_path(self, frm: int, target: int) -> list[int]:
        """Cari path dari frm ke target via chain gerak biasa + lompat (BFS)."""
        if frm == target:
            return []
        piece = self.board[frm]
        if not piece:
            return []
        color = piece[0]
        fdc = FORWARD_DC[color]

        def get_moves(cur, board_snap):
            """Return semua slot reachable 1 langkah (biasa + lompat) dari cur."""
            row, col = slot_to_rc(cur)
            moves = []
            # Normal: maju lurus + menyamping
            for dr, dc in DIRS_8:
                if (dc == fdc and dr == 0) or dc == 0:
                    nr, nc = row + dr, col + dc
                    if 0 <= nr < ROWS and 0 <= nc < COLS:
                        nb = rc_to_slot(nr, nc)
                        if board_snap.get(nb) is None:
                            moves.append(nb)
            # Jump: diagonal ke depan
            for dr, dc in DIRS_8:
                if dc * fdc <= 0:
                    continue
                mr, mc = row + dr, col + dc
                lr, lc = row + 2*dr, col + 2*dc
                if not (0 <= mr < ROWS and 0 <= mc < COLS and 0 <= lr < ROWS and 0 <= lc < COLS):
                    continue
                mid = rc_to_slot(mr, mc)
                land = rc_to_slot(lr, lc)
                if board_snap.get(mid) and board_snap.get(land) is None:
                    moves.append(land)
            return moves

        # BFS
        from collections import deque
        board_snap = dict(self.board)
        queue = deque([(frm, [frm])])
        visited = {frm}
        while queue:
            cur, path = queue.popleft()
            # Simulasi board: bidak di posisi cur
            sim_board = dict(board_snap)
            sim_board[frm] = None
            sim_board[cur] = (color, False)
            for nxt in get_moves(cur, sim_board):
                if nxt in visited:
                    continue
                if nxt == target:
                    return path[1:] + [nxt]  # exclude frm, include all steps
                visited.add(nxt)
                queue.append((nxt, path + [nxt]))
        return []

    def all_valid_sources(self) -> list[int]:
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

        color = piece[0]
        self.board[to]  = (color, False)
        self.board[frm] = None

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
