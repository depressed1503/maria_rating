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
        cur.execute("""
        CREATE TABLE IF NOT EXISTS team_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team1_player1_id INTEGER,
            team1_player2_id INTEGER,
            team2_player1_id INTEGER,
            team2_player2_id INTEGER,
            score1 INTEGER,
            score2 INTEGER,
            confirmed_player2 BOOLEAN DEFAULT 0,
            confirmed_player3 BOOLEAN DEFAULT 0,
            confirmed_player4 BOOLEAN DEFAULT 0,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(team1_player1_id) REFERENCES players(id),
            FOREIGN KEY(team1_player2_id) REFERENCES players(id),
            FOREIGN KEY(team2_player1_id) REFERENCES players(id),
            FOREIGN KEY(team2_player2_id) REFERENCES players(id)
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

def record_team_match(t1p1, t1p2, t2p1, t2p2, score1, score2):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO team_matches (
            team1_player1_id, team1_player2_id,
            team2_player1_id, team2_player2_id,
            score1, score2, confirmed
        ) VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (t1p1, t1p2, t2p1, t2p2, score1, score2))
        conn.commit()
        return cur.lastrowid

def confirm_team_match(match_id, k=32):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM team_matches WHERE id = ?", (match_id,))
        match = cur.fetchone()

        if not match or match[7]:  # already confirmed
            return False

        # unpack players and scores
        _, t1p1, t1p2, t2p1, t2p2, score1, score2, *_ = match

        winner_team = 1 if score1 > score2 else 2

        team1 = [get_player_by_id(t1p1), get_player_by_id(t1p2)]
        team2 = [get_player_by_id(t2p1), get_player_by_id(t2p2)]

        team1_avg = sum(p[3] for p in team1) / 2
        team2_avg = sum(p[3] for p in team2) / 2

        if winner_team == 1:
            winners = team1
            losers = team2
            r_win_avg = team1_avg
            r_lose_avg = team2_avg
        else:
            winners = team2
            losers = team1
            r_win_avg = team2_avg
            r_lose_avg = team1_avg

        # Пересчёт рейтингов каждого игрока
        for player in winners:
            new_rating, _ = calculate_elo(player[3], r_lose_avg, k)
            cur.execute("UPDATE players SET rating = ? WHERE id = ?", (new_rating, player[0]))

        for player in losers:
            _, new_rating = calculate_elo(r_win_avg, player[3], k)
            cur.execute("UPDATE players SET rating = ? WHERE id = ?", (new_rating, player[0]))

        cur.execute("UPDATE team_matches SET confirmed = 1 WHERE id = ?", (match_id,))
        conn.commit()
        return True

def record_team_match(t1p1, t1p2, t2p1, t2p2, score1, score2):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO team_matches (
            team1_player1_id, team1_player2_id,
            team2_player1_id, team2_player2_id,
            score1, score2
        ) VALUES (?, ?, ?, ?, ?, ?)
        """, (t1p1, t1p2, t2p1, t2p2, score1, score2))
        conn.commit()
        return cur.lastrowid

def get_team_match(match_id):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM team_matches WHERE id = ?", (match_id,))
        return cur.fetchone()

def confirm_team_participant(match_id, telegram_id):
    match = get_team_match(match_id)
    if not match:
        return False

    # Получаем ID игроков
    _, t1p1, t1p2, t2p1, t2p2, *_ = match
    player_ids = [t1p1, t1p2, t2p1, t2p2]
    player_map = {get_player_by_id(pid)[1]: pid for pid in player_ids}  # telegram_id → id

    if telegram_id not in player_map:
        return False

    # Определим, какая колонка подтверждения относится к пользователю
    telegram_ids = list(player_map.keys())
    pid_index = telegram_ids.index(telegram_id)

    column = f"confirmed_player{pid_index + 1}"

    with connect() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE team_matches SET {column} = 1 WHERE id = ?", (match_id,))
        conn.commit()

    return True

def is_team_match_fully_confirmed(match_id):
    match = get_team_match(match_id)
    if not match:
        return False
    confirmed_flags = match[7:10]
    return all(confirmed_flags)

def finalize_team_match(match_id, k=32):
    match = get_team_match(match_id)
    if not match:
        return False

    _, t1p1, t1p2, t2p1, t2p2, score1, score2, *_ = match

    winner_team = 1 if score1 > score2 else 2

    team1 = [get_player_by_id(t1p1), get_player_by_id(t1p2)]
    team2 = [get_player_by_id(t2p1), get_player_by_id(t2p2)]

    team1_avg = sum(p[3] for p in team1) / 2
    team2_avg = sum(p[3] for p in team2) / 2

    if winner_team == 1:
        winners = team1
        losers = team2
        r_win_avg = team1_avg
        r_lose_avg = team2_avg
    else:
        winners = team2
        losers = team1
        r_win_avg = team2_avg
        r_lose_avg = team1_avg

    with connect() as conn:
        cur = conn.cursor()
        for player in winners:
            new_rating, _ = calculate_elo(player[3], r_lose_avg, k)
            cur.execute("UPDATE players SET rating = ? WHERE id = ?", (new_rating, player[0]))
        for player in losers:
            _, new_rating = calculate_elo(r_win_avg, player[3], k)
            cur.execute("UPDATE players SET rating = ? WHERE id = ?", (new_rating, player[0]))
        conn.commit()

    return True
