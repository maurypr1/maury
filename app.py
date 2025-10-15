import os
import sqlite3
import pandas as pd
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
import database
import odds_calculator

app = Flask(__name__)
app.config.from_mapping(
    SECRET_KEY='dev',
    DATABASE='apuestas.sqlite',
)

try:
    os.makedirs(app.instance_path)
except OSError:
    pass

database.init_app(app)

def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

def admin_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None or not g.user['is_admin']:
            flash('Acceso denegado.', 'danger')
            return redirect(url_for('index'))
        return view(**kwargs)
    return wrapped_view

@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    g.user = None
    if user_id is not None:
        db = database.get_db()
        g.user = db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()

@app.route('/register', methods=('GET', 'POST'))
def register():
    if request.method == 'POST':
        username, email, password = request.form['username'], request.form['email'], request.form['password']
        db = database.get_db()
        error = None
        if not username or not email or not password:
            error = 'Todos los campos son requeridos.'
        if error is None:
            try:
                db.execute("INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)", (username, email, generate_password_hash(password)))
                db.commit()
                user = db.execute('SELECT user_id FROM users WHERE username = ?', (username,)).fetchone()
                db.execute("INSERT INTO transactions (user_id, transaction_type, amount) VALUES (?, ?, ?)", (user['user_id'], 'INITIAL', 1000.00))
                db.commit()
            except db.IntegrityError:
                error = f"El usuario {username} o el email {email} ya están registrados."
            else:
                flash('Registro exitoso. Por favor, inicia sesión.', 'success')
                return redirect(url_for('login'))
        flash(error, 'danger')
    return render_template('register.html')

@app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        email, password = request.form['email'], request.form['password']
        db = database.get_db()
        error = None
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if user is None or not check_password_hash(user['password_hash'], password):
            error = 'Email o contraseña incorrectos.'
        if error is None:
            session.clear()
            session['user_id'] = user['user_id']
            flash('Has iniciado sesión correctamente.', 'success')
            return redirect(url_for('index'))
        flash(error, 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado la sesión.', 'info')
    return redirect(url_for('index'))

@app.route('/')
def index():
    db = database.get_db()
    matches = db.execute("SELECT m.match_id, m.match_datetime, o.odds_home, o.odds_draw, o.odds_away, ht.team_name as home_team, at.team_name as away_team FROM matches m JOIN odds o ON m.match_id = o.match_id JOIN teams ht ON m.home_team_id = ht.team_id JOIN teams at ON m.away_team_id = at.team_id WHERE m.status = 'SCHEDULED' ORDER BY m.match_datetime ASC").fetchall()
    return render_template('index.html', matches=matches)

@app.route('/profile')
@login_required
def profile():
    db = database.get_db()
    if g.user:
        g.user = db.execute('SELECT * FROM users WHERE user_id = ?', (g.user['user_id'],)).fetchone()
    bets = db.execute("SELECT b.*, m.match_datetime, ht.team_name as home_team, at.team_name as away_team FROM bets b JOIN matches m ON b.match_id = m.match_id JOIN teams ht ON m.home_team_id = ht.team_id JOIN teams at ON m.away_team_id = at.team_id WHERE b.user_id = ? ORDER BY b.created_at DESC", (g.user['user_id'],)).fetchall()
    
    combo_bets_rows = db.execute("SELECT combo_bet_id, total_wager, potential_payout, status, created_at FROM combo_bets WHERE user_id = ? ORDER BY created_at DESC", (g.user['user_id'],)).fetchall()
    
    combo_bets = [dict(row) for row in combo_bets_rows]
    
    for combo in combo_bets:
        combo_selections = db.execute(
            """
            SELECT b.*, m.match_datetime, ht.team_name as home_team, at.team_name as away_team
            FROM bets b
            JOIN matches m ON b.match_id = m.match_id
            JOIN teams ht ON m.home_team_id = ht.team_id
            JOIN teams at ON m.away_team_id = at.team_id
            WHERE b.combo_bet_id = ?
            ORDER BY m.match_datetime ASC
            """, (combo['combo_bet_id'],)).fetchall()
        combo['selections'] = combo_selections

    return render_template('profile.html', bets=bets, combo_bets=combo_bets)

@app.route('/bet/<int:match_id>', methods=('POST',))
@login_required
def bet(match_id):
    wager_amount, bet_type = float(request.form['wager_amount']), request.form['bet_type']
    db = database.get_db()
    match = db.execute('SELECT * FROM matches WHERE match_id = ?', (match_id,)).fetchone()
    if match is None or match['status'] != 'SCHEDULED':
        flash('No se puede apostar en este partido.', 'danger')
        return redirect(url_for('index'))
    if g.user['token_balance'] < wager_amount:
        flash('No tienes suficientes tokens.', 'danger')
        return redirect(url_for('index'))
    match_odds = db.execute('SELECT * FROM odds WHERE match_id = ?', (match_id,)).fetchone()
    if bet_type == 'HOME_WIN':
        odds = match_odds['odds_home']
    elif bet_type == 'DRAW':
        odds = match_odds['odds_draw']
    else:
        odds = match_odds['odds_away']
    potential_payout = wager_amount * odds
    try:
        with db:
            cursor = db.execute("INSERT INTO bets (user_id, match_id, bet_type, wager_amount, odds_at_placement, potential_payout) VALUES (?, ?, ?, ?, ?, ?)", (g.user['user_id'], match_id, bet_type, wager_amount, odds, potential_payout))
            bet_id = cursor.lastrowid
            db.execute("INSERT INTO transactions (user_id, bet_id, transaction_type, amount) VALUES (?, ?, ?, ?)", (g.user['user_id'], bet_id, 'BET_PLACED', -wager_amount))
            new_balance = g.user['token_balance'] - wager_amount
            db.execute("UPDATE users SET token_balance = ? WHERE user_id = ?", (new_balance, g.user['user_id']))
        flash('Apuesta realizada con éxito.', 'success')
    except sqlite3.Error as e:
        flash(f'Error al realizar la apuesta: {e}', 'danger')
    return redirect(url_for('index'))

@app.route('/combo_bet', methods=['POST'])
@login_required
def combo_bet():
    selections = request.form.getlist('selection')
    wager = float(request.form['combo_wager'])

    if len(selections) < 2:
        flash('Debes seleccionar al menos dos partidos para una apuesta combinada.', 'danger')
        return redirect(url_for('index'))

    selected_matches = set()
    for selection in selections:
        match_id, _ = selection.split('-')
        if match_id in selected_matches:
            flash('Error: No puedes seleccionar más de una opción por partido en una apuesta combinada.', 'danger')
            return redirect(url_for('index'))
        selected_matches.add(match_id)

    db = database.get_db()
    
    if g.user['token_balance'] < wager:
        flash('No tienes suficientes tokens para esta apuesta combinada.', 'danger')
        return redirect(url_for('index'))
    
    total_odds = 1.0
    bets_to_insert = []
    
    combo_bet_id = None 
    try:
        with db:
            cursor = db.execute("INSERT INTO combo_bets (user_id, total_wager, potential_payout) VALUES (?, ?, ?)",
                                (g.user['user_id'], wager, 0))
            combo_bet_id = cursor.lastrowid

            for selection in selections:
                match_id, bet_type = selection.split('-')
                match_id = int(match_id)
                
                match_odds = db.execute("SELECT odds_home, odds_draw, odds_away FROM odds WHERE match_id = ?", (match_id,)).fetchone()
                
                if not match_odds:
                    raise ValueError(f"Cuotas no encontradas para el partido {match_id}")

                if bet_type == 'HOME_WIN':
                    odds = match_odds['odds_home']
                elif bet_type == 'DRAW':
                    odds = match_odds['odds_draw']
                else:
                    odds = match_odds['odds_away']
                
                total_odds *= odds
                bets_to_insert.append((g.user['user_id'], match_id, bet_type, wager, odds, wager * odds, combo_bet_id))

            final_payout = wager * total_odds
            
            db.execute("UPDATE combo_bets SET potential_payout = ? WHERE combo_bet_id = ?",
                       (final_payout, combo_bet_id))

            for bet_data in bets_to_insert:
                db.execute("INSERT INTO bets (user_id, match_id, bet_type, wager_amount, odds_at_placement, potential_payout, combo_bet_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           bet_data)

            new_balance = g.user['token_balance'] - wager
            db.execute("UPDATE users SET token_balance = ? WHERE user_id = ?", (new_balance, g.user['user_id']))
            db.execute("INSERT INTO transactions (user_id, transaction_type, amount, combo_bet_id) VALUES (?, ?, ?, ?)", (g.user['user_id'], 'COMBO_BET_PLACED', -wager, combo_bet_id))

            flash(f'Apuesta combinada realizada con éxito! Cuota total: {total_odds:.2f}. Ganancia potencial: {final_payout:.2f}', 'success')

    except Exception as e:
        flash(f'Error al realizar la apuesta combinada: {e}', 'danger')
        with db:
            if combo_bet_id:
                db.execute("DELETE FROM combo_bets WHERE combo_bet_id = ?", (combo_bet_id,))
                db.execute("DELETE FROM bets WHERE combo_bet_id = ?", (combo_bet_id,))
            
    return redirect(url_for('index'))

@app.route('/admin', methods=['GET'])
@admin_required
def admin():
    db = database.get_db()
    teams = db.execute("SELECT * FROM teams ORDER BY team_name").fetchall()
    unsettled_matches = db.execute("SELECT m.match_id, ht.team_name as home_team, at.team_name as away_team FROM matches m JOIN odds o ON m.match_id = o.match_id JOIN teams ht ON m.home_team_id = ht.team_id JOIN teams at ON m.away_team_id = at.team_id WHERE m.status = 'SCHEDULED' ORDER BY m.match_datetime").fetchall()
    users = db.execute("SELECT * FROM users ORDER BY username").fetchall()
    return render_template('admin.html', teams=teams, unsettled_matches=unsettled_matches, users=users)

@app.route('/admin-actions', methods=['POST'])
@admin_required
def admin_actions():
    db = database.get_db()
    action = request.form.get('action')

    if action == 'add_team':
        team_name = request.form['team_name']
        if team_name:
            try:
                db.execute("INSERT INTO teams (team_name) VALUES (?)", (team_name,))
                db.commit()
                flash(f'Equipo "{team_name}" añadido.', 'success')
            except db.IntegrityError:
                flash(f'El equipo "{team_name}" ya existe.', 'warning')
        
    elif action == 'add_match':
        home_team_id, away_team_id = request.form['home_team_id'], request.form['away_team_id']
        match_datetime = request.form['match_datetime']
        
        existing_match = db.execute("SELECT 1 FROM matches WHERE home_team_id = ? AND away_team_id = ? AND match_datetime = ? AND status IN ('SCHEDULED', 'COMPLETED')", (home_team_id, away_team_id, match_datetime)).fetchone()
        
        if existing_match:
            flash('Error: Ya existe un partido con los mismos equipos y fecha programado o completado.', 'danger')
        elif home_team_id == away_team_id:
            flash('Un equipo no puede jugar contra sí mismo.', 'danger')
        else:
            try:
                with db:
                    cursor = db.execute("INSERT INTO matches (home_team_id, away_team_id, match_datetime) VALUES (?, ?, ?)", (home_team_id, away_team_id, match_datetime))
                    new_match_id = cursor.lastrowid
                    odds_calculator.generate_and_store_odds(db, new_match_id, int(home_team_id), int(away_team_id))
                flash('Partido programado y cuotas calculadas.', 'success')
            except Exception as e:
                flash(f'Ocurrió un error inesperado al agregar el partido: {e}', 'danger')
        
    elif action == 'settle_match':
        match_id, home_score, away_score = request.form['match_id'], int(request.form['home_score']), int(request.form['away_score'])
        try:
            with db:
                db.execute("UPDATE matches SET home_score = ?, away_score = ?, status = 'COMPLETED' WHERE match_id = ?", (home_score, away_score, match_id))
                active_bets = db.execute("SELECT * FROM bets WHERE match_id = ? AND status = 'ACTIVE'", (match_id,)).fetchall()
                if home_score > away_score:
                    match_result = 'HOME_WIN'
                elif home_score < away_score:
                    match_result = 'AWAY_WIN'
                else:
                    match_result = 'DRAW'
                for bet in active_bets:
                    if bet['bet_type'] == match_result:
                        new_status, payout = 'WON', bet['potential_payout']
                        user = db.execute("SELECT token_balance FROM users WHERE user_id = ?", (bet['user_id'],)).fetchone()
                        new_balance = user['token_balance'] + payout
                        db.execute("UPDATE users SET token_balance = ? WHERE user_id = ?", (new_balance, bet['user_id']))
                        db.execute("INSERT INTO transactions (user_id, bet_id, transaction_type, amount) VALUES (?, ?, ?, ?)", (bet['user_id'], bet['bet_id'], 'WINNINGS', payout))
                    else:
                        new_status = 'LOST'
                    db.execute("UPDATE bets SET status = ? WHERE bet_id = ?", (new_status, bet['bet_id']))
            flash(f'Partido {match_id} liquidado.', 'success')
        except sqlite3.Error as e:
            flash(f'Error al liquidar: {e}', 'danger')
        
    elif action == 'cancel_match':
        match_id = request.form['match_id']
        try:
            with db:
                bets_to_refund = db.execute("SELECT * FROM bets WHERE match_id = ? AND status = 'ACTIVE'", (match_id,)).fetchall()
                for bet in bets_to_refund:
                    user = db.execute("SELECT token_balance FROM users WHERE user_id = ?", (bet['user_id'],)).fetchone()
                    new_balance = user['token_balance'] + bet['wager_amount']
                    db.execute("UPDATE users SET token_balance = ? WHERE user_id = ?", (new_balance, bet['user_id']))
                    db.execute("INSERT INTO transactions (user_id, bet_id, transaction_type, amount) VALUES (?, ?, ?, ?)", (bet['user_id'], bet['bet_id'], 'BET_REFUND', bet['wager_amount']))
                    db.execute("UPDATE bets SET status = 'CANCELLED' WHERE bet_id = ?", (bet['bet_id'],))
                db.execute("UPDATE matches SET status = 'CANCELLED' WHERE match_id = ?", (match_id,))
            flash(f'Partido {match_id} ha sido cancelado y las apuestas devueltas.', 'info')
        except sqlite3.Error as e:
            flash(f'Error al cancelar el partido: {e}', 'danger')
        
    elif action == 'add_tokens':
        user_id = request.form['user_id']
        amount = float(request.form['amount'])
        
        try:
            with db:
                user = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
                if user:
                    new_balance = user['token_balance'] + amount
                    db.execute("UPDATE users SET token_balance = ? WHERE user_id = ?", (new_balance, user_id))
                    db.execute("INSERT INTO transactions (user_id, transaction_type, amount) VALUES (?, ?, ?)", (user_id, 'ADMIN_ADD', amount))
                    flash(f'Se han añadido {amount} tokens a {user["username"]}. Nuevo balance: {new_balance}.', 'success')
                else:
                    flash('Usuario no encontrado.', 'danger')
        except Exception as e:
            flash(f'Ocurrió un error inesperado: {e}', 'danger')
    
    elif action == 'subtract_tokens':
        user_id = request.form['user_id']
        amount = float(request.form['amount'])
        
        try:
            with db:
                user = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
                if user:
                    new_balance = user['token_balance'] - amount
                    if new_balance < 0:
                        flash('El balance del usuario no puede ser negativo.', 'danger')
                    else:
                        db.execute("UPDATE users SET token_balance = ? WHERE user_id = ?", (new_balance, user_id))
                        db.execute("INSERT INTO transactions (user_id, transaction_type, amount) VALUES (?, ?, ?)", (user_id, 'ADMIN_SUBTRACT', -amount))
                        flash(f'Se han quitado {amount} tokens a {user["username"]}. Nuevo balance: {new_balance}.', 'success')
                else:
                    flash('Usuario no encontrado.', 'danger')
        except Exception as e:
            flash(f'Ocurrió un error inesperado: {e}', 'danger')
    
    return redirect(url_for('admin'))

@app.route('/admin/upload', methods=['POST'])
@admin_required
def upload_results():
    if 'file' not in request.files:
        flash('No se seleccionó ningún archivo.', 'danger')
        return redirect(url_for('admin'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No se seleccionó un archivo.', 'danger')
        return redirect(url_for('admin'))

    if file and file.filename.endswith('.csv'):
        try:
            df = pd.read_csv(file)
            db = database.get_db()
            
            if df.empty:
                flash("El archivo CSV está vacío.", 'danger')
                return redirect(url_for('admin'))

            with db:
                all_teams = pd.concat([df['home_team_id'], df['away_team_id']]).unique()

                for team_name in all_teams:
                    try:
                        db.execute("INSERT INTO teams (team_name) VALUES (?)", (team_name,))
                    except sqlite3.IntegrityError:
                        pass

                team_mapping = {row['team_name']: row['team_id'] for row in db.execute("SELECT team_id, team_name FROM teams").fetchall()}

                for index, row in df.iterrows():
                    home_team_id = team_mapping.get(row['home_team_id'])
                    away_team_id = team_mapping.get(row['away_team_id'])

                    db.execute(
                        "INSERT INTO matches (home_team_id, away_team_id, match_datetime, home_score, away_score, status) VALUES (?, ?, ?, ?, ?, ?)",
                        (home_team_id, away_team_id, row['match_datetime'], row['home_score'], row['away_score'], 'COMPLETED')
                    )

            flash('Resultados cargados y guardados exitosamente. Ahora puedes programar partidos para generar cuotas dinámicas.', 'success')
        except Exception as e:
            flash(f'Ocurrió un error al procesar el archivo: {e}', 'danger')
    else:
        flash('Tipo de archivo no válido. Por favor, sube un archivo CSV.', 'danger')

    return redirect(url_for('admin'))

@app.route('/fix-admin')
def fix_admin_password():
    db = database.get_db()
    try:
        admin_user = db.execute("SELECT * FROM users WHERE email = 'admin@uni.edu'").fetchone()
        if admin_user:
            new_hash = generate_password_hash('admin')
            db.execute("UPDATE users SET password_hash = ? WHERE user_id = ?", (new_hash, admin_user['user_id']))
            db.commit()
            return "¡Contraseña del admin actualizada con éxito!"
        else:
            return "No se encontró al usuario admin."
    except Exception as e:
        return f"Ocurrió un error: {e}"