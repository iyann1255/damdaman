"""
game.py — Logika Dam-daman (Indonesian Draughts)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict

# Cell values
EMPTY   = 0
P1      = 1   # merah, jalan ke bawah (baris 0 → 7)
P2      = 2   # biru,  jalan ke atas  (baris 7 → 0)
P1_DAM  = 3
P2_DAM  = 4

Pos = Tuple[int, int]  # (row, col)


def owner(cell: int) -> Optional[int]:
    """Return 1 atau 2, atau None kalau kosong."""
    if cell in (P1, P1_DAM): return 1
    if cell in (P2, P2_DAM): return 2
    return None


def is_dam(cell: int) -> bool:
    return cell in (P1_DAM, P2_DAM)


def is_dark(r: int, c: int) -> bool:
    """Cell gelap = (r+c) ganjil — cell yang boleh dipakai."""
    return (r + c) % 2 == 1


@dataclass
class GameState:
    board: List[List[int]] = field(default_factory=lambda: [[EMPTY]*8 for _ in range(8)])
    turn: int = 2                          # 1 atau 2; P2 jalan duluan
    selected: Optional[Pos] = None
    chain_piece: Optional[Pos] = None     # posisi bidak di tengah chain capture
    player1_id: Optional[int] = None
    player2_id: Optional[int] = None
    move_count: int = 0                   # untuk deteksi seri
    winner: Optional[int] = None          # 1, 2, atau 0 (seri)
    draw_offered_by: Optional[int] = None

    @classmethod
    def new(cls, p1_id: int, p2_id: int) -> "GameState":
        g = cls(player1_id=p1_id, player2_id=p2_id)
        g._setup_board()
        return g

    def _setup_board(self):
        for r in range(8):
            for c in range(8):
                if not is_dark(r, c):
                    continue
                if r < 3:
                    self.board[r][c] = P1
                elif r > 4:
                    self.board[r][c] = P2

    # ── Query helpers ─────────────────────────────────────────────────

    def cell(self, r: int, c: int) -> int:
        return self.board[r][c]

    def pieces_of(self, player: int) -> List[Pos]:
        target = (P1, P1_DAM) if player == 1 else (P2, P2_DAM)
        return [(r, c) for r in range(8) for c in range(8) if self.board[r][c] in target]

    # ── Move generation ───────────────────────────────────────────────

    def _forward_dirs(self, player: int) -> List[Tuple[int, int]]:
        """Arah maju bidak biasa."""
        return [(1, -1), (1, 1)] if player == 1 else [(-1, -1), (-1, 1)]

    def _all_dirs(self) -> List[Tuple[int, int]]:
        return [(-1, -1), (-1, 1), (1, -1), (1, 1)]

    def simple_moves(self, r: int, c: int) -> List[Pos]:
        """Langkah biasa (tidak makan) untuk bidak di (r,c)."""
        cell = self.board[r][c]
        p = owner(cell)
        if p is None:
            return []
        dirs = self._all_dirs() if is_dam(cell) else self._forward_dirs(p)
        result = []
        for dr, dc in dirs:
            nr, nc = r + dr, c + dc
            if 0 <= nr < 8 and 0 <= nc < 8 and self.board[nr][nc] == EMPTY:
                result.append((nr, nc))
        return result

    def capture_moves(self, r: int, c: int, already_captured: Optional[List[Pos]] = None) -> List[Tuple[Pos, Pos]]:
        """
        Return list of (landing_pos, captured_pos) untuk makan dari (r,c).
        already_captured: posisi bidak yang sudah dimakan di chain ini (belum dihapus dari board).
        """
        cell = self.board[r][c]
        p = owner(cell)
        if p is None:
            return []
        already_captured = already_captured or []
        dirs = self._all_dirs()
        result = []
        for dr, dc in dirs:
            mr, mc = r + dr, c + dc        # middle (bidak musuh)
            lr, lc = r + 2*dr, c + 2*dc   # landing
            if not (0 <= mr < 8 and 0 <= mc < 8 and 0 <= lr < 8 and 0 <= lc < 8):
                continue
            mid_cell = self.board[mr][mc]
            if owner(mid_cell) == p or owner(mid_cell) is None:
                continue
            if (mr, mc) in already_captured:
                continue
            if self.board[lr][lc] != EMPTY:
                continue
            result.append(((lr, lc), (mr, mc)))
        return result

    def all_captures(self, player: int) -> Dict[Pos, List[Tuple[Pos, Pos]]]:
        """Semua kemungkinan makan untuk player."""
        out = {}
        for pos in self.pieces_of(player):
            caps = self.capture_moves(*pos)
            if caps:
                out[pos] = caps
        return out

    def all_simple_moves(self, player: int) -> Dict[Pos, List[Pos]]:
        out = {}
        for pos in self.pieces_of(player):
            moves = self.simple_moves(*pos)
            if moves:
                out[pos] = moves
        return out

    def must_capture(self) -> bool:
        return bool(self.all_captures(self.turn))

    # ── Highlights untuk UI ───────────────────────────────────────────

    def valid_sources(self) -> List[Pos]:
        """Bidak yang boleh dipilih giliran ini."""
        if self.chain_piece:
            return [self.chain_piece]
        if self.must_capture():
            return list(self.all_captures(self.turn).keys())
        return list(self.all_simple_moves(self.turn).keys())

    def valid_targets(self, r: int, c: int) -> List[Pos]:
        """
        Cell tujuan yang boleh diklik setelah memilih bidak (r,c).
        Return list landing positions.
        """
        if self.chain_piece and self.chain_piece != (r, c):
            return []
        caps = self.capture_moves(r, c)
        if caps:
            return [land for land, _ in caps]
        if self.must_capture():
            return []
        return self.simple_moves(r, c)

    # ── Execute move ──────────────────────────────────────────────────

    def move(self, fr: int, fc: int, tr: int, tc: int) -> bool:
        """
        Lakukan gerakan dari (fr,fc) → (tr,tc).
        Return True jika valid dan berhasil.
        """
        if self.winner is not None:
            return False

        cell = self.board[fr][fc]
        if owner(cell) != self.turn:
            return False

        # Cek apakah ini langkah capture
        caps = self.capture_moves(fr, fc)
        cap_map = {land: mid for land, mid in caps}

        if (tr, tc) in cap_map:
            # Eksekusi makan
            mr, mc = cap_map[(tr, tc)]
            self.board[tr][tc] = cell
            self.board[fr][fc] = EMPTY
            self.board[mr][mc] = EMPTY  # hapus bidak musuh langsung

            promoted = self._try_promote(tr, tc)

            # Cek chain capture
            if not promoted and self.capture_moves(tr, tc):
                self.chain_piece = (tr, tc)
                self.selected = None
            else:
                self.chain_piece = None
                self._end_turn()
        else:
            # Langkah biasa
            if self.must_capture():
                return False
            if (tr, tc) not in self.simple_moves(fr, fc):
                return False
            self.board[tr][tc] = cell
            self.board[fr][fc] = EMPTY
            self._try_promote(tr, tc)
            self.chain_piece = None
            self._end_turn()

        self.selected = None
        self._check_winner()
        return True

    def _try_promote(self, r: int, c: int) -> bool:
        """Promosi ke DAM jika sampai ujung. Return True jika promosi."""
        cell = self.board[r][c]
        if cell == P1 and r == 7:
            self.board[r][c] = P1_DAM
            return True
        if cell == P2 and r == 0:
            self.board[r][c] = P2_DAM
            return True
        return False

    def _end_turn(self):
        self.turn = 2 if self.turn == 1 else 1
        self.move_count += 1

    def _check_winner(self):
        p1 = self.pieces_of(1)
        p2 = self.pieces_of(2)
        if not p1:
            self.winner = 2
            return
        if not p2:
            self.winner = 1
            return

        # Cek tidak ada gerakan legal
        caps   = self.all_captures(self.turn)
        simples = self.all_simple_moves(self.turn)
        if not caps and not simples:
            self.winner = 2 if self.turn == 1 else 1
            return

        # Seri: kedua pihak hanya DAM, 40 giliran tanpa kemajuan
        only_dams = all(self.board[r][c] in (P1_DAM, P2_DAM) for r, c in p1 + p2)
        if only_dams and self.move_count >= 40:
            self.winner = 0

    def is_game_over(self) -> bool:
        return self.winner is not None
