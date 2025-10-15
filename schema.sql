-- Elimina las tablas existentes si ya existen para una inicialización limpia
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS bets;
DROP TABLE IF EXISTS odds;
DROP TABLE IF EXISTS matches;
DROP TABLE IF EXISTS team_elo_ratings;
DROP TABLE IF EXISTS teams;
DROP TABLE IF EXISTS users;

-- Tablas principales
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    token_balance REAL NOT NULL DEFAULT 1000.00,
    is_admin BOOLEAN NOT NULL DEFAULT 0
);

CREATE TABLE teams (
    team_id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT UNIQUE NOT NULL
);

CREATE TABLE matches (
    match_id INTEGER PRIMARY KEY AUTOINCREMENT,
    home_team_id INTEGER NOT NULL,
    away_team_id INTEGER NOT NULL,
    match_datetime TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'SCHEDULED',
    home_score INTEGER,
    away_score INTEGER,
    FOREIGN KEY (home_team_id) REFERENCES teams (team_id),
    FOREIGN KEY (away_team_id) REFERENCES teams (team_id),
    CONSTRAINT uq_match UNIQUE (home_team_id, away_team_id, match_datetime)
);

CREATE TABLE odds (
    odds_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    odds_home REAL NOT NULL,
    odds_draw REAL NOT NULL,
    odds_away REAL NOT NULL,
    FOREIGN KEY (match_id) REFERENCES matches (match_id)
);

CREATE TABLE bets (
    bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    match_id INTEGER NOT NULL,
    bet_type TEXT NOT NULL,
    wager_amount REAL NOT NULL,
    odds_at_placement REAL NOT NULL,
    potential_payout REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    combo_bet_id INTEGER,
    FOREIGN KEY (user_id) REFERENCES users (user_id),
    FOREIGN KEY (match_id) REFERENCES matches (match_id),
    FOREIGN KEY (combo_bet_id) REFERENCES combo_bets (combo_bet_id)
);

-- Nueva tabla para almacenar los rankings Elo de los equipos
CREATE TABLE team_elo_ratings (
    team_id INTEGER PRIMARY KEY,
    elo_rating REAL NOT NULL,
    FOREIGN KEY (team_id) REFERENCES teams (team_id)
);

-- Tabla para apuestas combinadas
CREATE TABLE combo_bets (
    combo_bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    total_wager REAL NOT NULL,
    potential_payout REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);

-- Tabla de transacciones
CREATE TABLE transactions (
    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    bet_id INTEGER,
    transaction_type TEXT NOT NULL,
    amount REAL NOT NULL,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    combo_bet_id INTEGER,
    FOREIGN KEY (user_id) REFERENCES users (user_id),
    FOREIGN KEY (bet_id) REFERENCES bets (bet_id),
    FOREIGN KEY (combo_bet_id) REFERENCES combo_bets (combo_bet_id)
);

-- Datos iniciales
INSERT INTO users (username, email, password_hash, is_admin) VALUES ('admin', 'admin@uni.edu', 'pbkdf2:sha256:260000$V1iH52r5j2aGg8b2$5f2f4557a10ded0b3134b2195cb154f9921e2b6e115169493d987c7b2d28b8a8', 1);