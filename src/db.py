import sqlite3
from datetime import datetime


DB_NAME = "db.sqlite3"

def connect():
    return sqlite3.connect(DB_NAME)

def init_db():
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            username TEXT,
            rating INTEGER DEFAULT 1500
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player1_id INTEGER,
            player2_id INTEGER,
            score1 INTEGER,
            score2 INTEGER,
            winner_id INTEGER,
            confirmed BOOLEAN DEFAULT 0,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(player1_id) REFERENCES players(id),
            FOREIGN KEY(player2_id) REFERENCES players(id),
            FOREIGN KEY(winner_id) REFERENCES players(id)
        );
        """)
        conn.commit()

def register_player(telegram_id, username):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT OR IGNORE INTO players (telegram_id, username)
        VALUES (?, ?)
        """, (telegram_id, username))
        conn.commit()

def get_player_by_username(username):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM players WHERE username = ?", (username,))
        return cur.fetchone()

def get_player_by_telegram_id(telegram_id):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM players WHERE telegram_id = ?", (telegram_id,))
        return cur.fetchone()

def get_player_by_id(pid):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM players WHERE id = ?", (pid,))
        return cur.fetchone()

def record_match(player1_id, player2_id, score1, score2, winner_id):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO matches (player1_id, player2_id, score1, score2, winner_id, confirmed)
        VALUES (?, ?, ?, ?, ?, 0)
        """, (player1_id, player2_id, score1, score2, winner_id))
        conn.commit()
        return cur.lastrowid

def confirm_match(match_id):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM matches WHERE id = ?", (match_id,))
        match = cur.fetchone()
        if not match:
            return False

        player1 = get_player_by_id(match[1])
        player2 = get_player_by_id(match[2])
        winner_id = match[5]
        loser_id = match[1] if match[2] == winner_id else match[2]

        winner = get_player_by_id(winner_id)
        loser = get_player_by_id(loser_id)

        new_winner_rating, new_loser_rating = calculate_elo(winner[3], loser[3])

        cur.execute("UPDATE players SET rating = ? WHERE id = ?",
                    (new_winner_rating, winner_id))
        cur.execute("UPDATE players SET rating = ? WHERE id = ?",
                    (new_loser_rating, loser_id))
        cur.execute("UPDATE matches SET confirmed = 1 WHERE id = ?", (match_id,))
        conn.commit()
        return True

def calculate_elo(r_winner, r_loser, k=32):
    expected = 1 / (1 + 10 ** ((r_loser - r_winner) / 400))
    r_winner_new = r_winner + k * (1 - expected)
    r_loser_new = r_loser + k * (0 - (1 - expected))
    return round(r_winner_new), round(r_loser_new)

def get_rating_table():
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT username, rating FROM players ORDER BY rating DESC")
        return cur.fetchall()

def get_games_played(player_id):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT COUNT(*) FROM matches 
        WHERE confirmed = 1 AND (player1_id = ? OR player2_id = ?)
        """, (player_id, player_id))
        return cur.fetchone()[0]
