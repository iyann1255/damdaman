"""db.py — SQLite logging untuk dam-daman"""
import sqlite3
import json
from datetime import datetime

DB_PATH = "damdaman.db"

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA journal_mode=WAL")
    return c

def init_db():
    c = _conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room TEXT NOT NULL,
        chat_id INTEGER NOT NULL,
        p1_id INTEGER, p1_name TEXT,
        p2_id INTEGER, p2_name TEXT,
        p1_color TEXT,
        winner TEXT,
        started_at TEXT,
        ended_at TEXT
    );
    CREATE TABLE IF NOT EXISTS moves (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER NOT NULL,
        move_num INTEGER NOT NULL,
        player TEXT NOT NULL,
        frm INTEGER NOT NULL,
        dest INTEGER NOT NULL,
        board_state TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        FOREIGN KEY(game_id) REFERENCES games(id)
    );
    """)
    c.close()

def log_new_game(chat_id: int, p1_id, p1_name, p2_id, p2_name, p1_color, board: dict) -> int:
    c = _conn()
    room = f"#rm{chat_id}"
    cur = c.execute(
        "INSERT INTO games (room, chat_id, p1_id, p1_name, p2_id, p2_name, p1_color, started_at) VALUES (?,?,?,?,?,?,?,?)",
        (room, chat_id, p1_id, p1_name, p2_id, p2_name, p1_color, datetime.now().isoformat())
    )
    game_id = cur.lastrowid
    # Log initial board as move 0
    c.execute(
        "INSERT INTO moves (game_id, move_num, player, frm, dest, board_state, timestamp) VALUES (?,?,?,?,?,?,?)",
        (game_id, 0, "START", 0, 0, _board_json(board), datetime.now().isoformat())
    )
    c.commit()
    c.close()
    return game_id

def log_move(game_id: int, move_num: int, player: str, frm: int, dest: int, board: dict):
    c = _conn()
    c.execute(
        "INSERT INTO moves (game_id, move_num, player, frm, dest, board_state, timestamp) VALUES (?,?,?,?,?,?,?)",
        (game_id, move_num, player, frm, dest, _board_json(board), datetime.now().isoformat())
    )
    c.commit()
    c.close()

def log_game_end(game_id: int, winner: str):
    c = _conn()
    c.execute("UPDATE games SET winner=?, ended_at=? WHERE id=?",
              (winner, datetime.now().isoformat(), game_id))
    c.commit()
    c.close()

def _board_json(board: dict) -> str:
    # Simpan hanya slot yang terisi: {slot: "W"/"B"}
    compact = {str(k): v[0] for k, v in board.items() if v is not None}
    return json.dumps(compact, separators=(',', ':'))
