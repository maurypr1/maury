import pandas as pd
import math

K_FACTOR = 32
HOME_ADVANTAGE = 100
MARGIN = 0.05

def calculate_elo_ratings(db):
    """
    Calcula los rankings Elo de todos los equipos basándose en los partidos completados.
    Inicializa todos los equipos con un rating de 1500.
    """
    teams_cursor = db.execute("SELECT team_id FROM teams")
    elo_ratings = {row['team_id']: 1500.0 for row in teams_cursor.fetchall()}
    
    cursor = db.execute("SELECT home_team_id, away_team_id, home_score, away_score FROM matches WHERE status = 'COMPLETED' ORDER BY match_datetime ASC")
    completed_matches = cursor.fetchall()

    for row in completed_matches:
        home_team, away_team = row['home_team_id'], row['away_team_id']
        home_score, away_score = row['home_score'], row['away_score']

        elo_home = elo_ratings.get(home_team, 1500)
        elo_away = elo_ratings.get(away_team, 1500)

        expected_home_win = 1 / (1 + math.pow(10, (elo_away - elo_home - HOME_ADVANTAGE) / 400))

        if home_score > away_score:
            actual_result = 1.0
        elif away_score > home_score:
            actual_result = 0.0
        else:
            actual_result = 0.5

        elo_ratings[home_team] = elo_home + K_FACTOR * (actual_result - expected_home_win)
        elo_ratings[away_team] = elo_away + K_FACTOR * ((1 - actual_result) - (1 - expected_home_win))
    
    return elo_ratings

def get_elo_based_probabilities(home_team_id, away_team_id, elo_ratings):
    """
    Calcula las probabilidades de victoria, empate y derrota
    basadas en los rankings Elo de los equipos.
    """
    elo_home = elo_ratings.get(home_team_id, 1500)
    elo_away = elo_ratings.get(away_team_id, 1500)

    expected_home_win = 1 / (1 + math.pow(10, (elo_away - elo_home - HOME_ADVANTAGE) / 400))
    expected_away_win = 1 - expected_home_win

    prob_draw = 0.25 
    
    total_win_prob = expected_home_win + expected_away_win
    
    if total_win_prob > 0:
        prob_home_win = (expected_home_win / total_win_prob) * (1 - prob_draw)
        prob_away_win = (expected_away_win / total_win_prob) * (1 - prob_draw)
    else:
        prob_home_win = 0.33
        prob_away_win = 0.33
        prob_draw = 0.34

    return {
        'home_win': prob_home_win,
        'draw': prob_draw,
        'away_win': prob_away_win
    }

def convert_to_odds(probabilities):
    """Convierte las probabilidades en cuotas con un margen."""
    prob_home = probabilities['home_win'] * (1 + MARGIN)
    prob_draw = probabilities['draw'] * (1 + MARGIN)
    prob_away = probabilities['away_win'] * (1 + MARGIN)

    return {
        'odds_home': 1 / prob_home,
        'odds_draw': 1 / prob_draw,
        'odds_away': 1 / prob_away
    }

def generate_and_store_odds(db, match_id, home_team_id, away_team_id):
    """Genera y almacena las cuotas de un partido usando Elo."""
    elo_ratings = calculate_elo_ratings(db)
    
    probabilities = get_elo_based_probabilities(home_team_id, away_team_id, elo_ratings)
    odds_to_store = convert_to_odds(probabilities)
    
    try:
        db.execute(
            "INSERT INTO odds (match_id, odds_home, odds_draw, odds_away) VALUES (?, ?, ?, ?)",
            (match_id, odds_to_store['odds_home'], odds_to_store['odds_draw'], odds_to_store['odds_away'])
        )
        db.commit()
        print(f"Cuotas generadas y guardadas para el partido {match_id}")
    except sqlite3.IntegrityError as e:
        print(f"Error de integridad al guardar las cuotas: {e}")