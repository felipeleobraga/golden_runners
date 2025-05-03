# -*- coding: utf-8 -*-
import os
import sys
import psycopg2
import psycopg2.extras # Adicionado para buscar resultados como dicionários
import traceback # Importado para log detalhado de erros
import requests # Adicionado para fazer requisições HTTP
import json # Adicionado para lidar com JSON
import datetime # Adicionado para lidar com timestamps
import math # Adicionado para arredondamento de pontos
from urllib.parse import urlparse, urlencode # urlencode adicionado
from flask import Flask, render_template, session, g, flash, redirect, url_for, request
from dotenv import load_dotenv
from functools import wraps
from requests_oauthlib import OAuth2Session # Adicionado para OAuth

# Importar o blueprint de autenticação
from auth import auth_bp

# Carregar variáveis de ambiente do arquivo .env (útil para desenvolvimento local)
load_dotenv()

# Criar a instância da aplicação Flask
app = Flask(__name__)

# Configurar uma chave secreta (necessária para sessões, flash messages, etc.)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "a_more_secure_default_secret_key_if_not_set")

# Configurações do Strava (carregadas do .env)
STRAVA_CLIENT_ID = os.environ.get("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.environ.get("STRAVA_CLIENT_SECRET")
STRAVA_AUTHORIZATION_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE_URL = "https://www.strava.com/api/v3"
STRAVA_REDIRECT_URI = os.environ.get("STRAVA_REDIRECT_URI", "http://localhost:5000/strava/callback") 
STRAVA_SCOPES = ["read", "activity:read_all"]

# Registrar o blueprint de autenticação
app.register_blueprint(auth_bp, url_prefix="/auth")

# --- Conexão com Banco de Dados --- 
def get_db_connection():
    """Estabelece conexão com o banco de dados."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        load_dotenv()
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
             raise ValueError("DATABASE_URL não está definida no ambiente ou .env")
    try:
        print("DEBUG: [get_db_connection] Connecting to DB...") # Added debug
        conn = psycopg2.connect(db_url)
        print("DEBUG: [get_db_connection] Connection successful.") # Added debug
        return conn
    except psycopg2.OperationalError as e:
        print(f"!!! FATAL DB CONNECTION ERROR: {e}")
        raise

# --- Funções Auxiliares e Decorators --- 

@app.before_request
def load_logged_in_user():
    """Carrega dados do usuário logado (incluindo team_id) e token Strava antes de cada request."""
    user_id = session.get("user_id")
    g.user = None
    g.strava_token_data = None

    if user_id is not None:
        # print(f"DEBUG: [load_logged_in_user] User ID {user_id} found in session.") # Verbose debug
        g.user = {"id": user_id, "username": session.get("username")}
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Busca dados completos do usuário, incluindo pontos, created_at e team_id
            # print(f"DEBUG: [load_logged_in_user] Fetching user data for {user_id}") # Verbose debug
            cur.execute("SELECT id, username, points, created_at, team_id FROM users WHERE id = %s", (user_id,))
            user_data_from_db = cur.fetchone()
            if user_data_from_db:
                g.user.update(user_data_from_db)
                # print(f"DEBUG: [load_logged_in_user] User data loaded: {g.user}") # Verbose debug
            else:
                print(f"WARN: [load_logged_in_user] No user data found in DB for user_id: {user_id}")
            
            # Busca token do Strava
            # print(f"DEBUG: [load_logged_in_user] Fetching Strava token for {user_id}") # Verbose debug
            cur.execute("SELECT *, created_at, updated_at FROM strava_tokens WHERE user_id = %s", (user_id,))
            token_data = cur.fetchone()
            cur.close()
            # print("DEBUG: [load_logged_in_user] DB cursor closed.") # Verbose debug
            
            if token_data:
                expires_at = token_data["expires_at"]
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                if expires_at > now_utc + datetime.timedelta(seconds=60):
                    g.strava_token_data = token_data
                    # print("DEBUG: [load_logged_in_user] Valid Strava token loaded.") # Verbose debug
                else:
                    print(f"WARN: [load_logged_in_user] Strava token for user {user_id} expired. Needs refresh.")
                    # TODO: Implementar refresh token
            # else: # Verbose debug
                # print("DEBUG: [load_logged_in_user] No Strava token found for user.") # Verbose debug
                    
        except Exception as db_error:
            error_details = traceback.format_exc()
            print(f"!!! CRITICAL DB ERROR in load_logged_in_user: {db_error}\n{error_details}") 
            g.user = None
            g.strava_token_data = None
        finally:
            if conn:
                # print("DEBUG: [load_logged_in_user] Closing DB connection.") # Verbose debug
                conn.close()
    # else: # Verbose debug
        # print("DEBUG: [load_logged_in_user] No user ID in session.") # Verbose debug

def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash("Você precisa fazer login para acessar esta página.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        return view(**kwargs)
    return wrapped_view

# --- Rotas Principais --- 

@app.route("/")
def home():
    try: 
        return render_template("home.html")
    except Exception as e: 
        print(f"!!! Render ERROR home: {e}\n{traceback.format_exc()}"); 
        return "Erro ao carregar página inicial.", 500

@app.route("/dashboard")
@login_required
def dashboard():
    if not g.user:
        print("!!! ERROR: g.user is None in dashboard route despite @login_required")
        flash("Erro interno: usuário não carregado.", "error")
        return redirect(url_for("auth.login"))
        
    user_data = {
        "username": g.user.get("username", "N/A"),
        "points": g.user.get("points", 0),
        "total_km": 0, # Placeholder
        "total_donated": 0, # Placeholder
        "last_activity": "N/A" # Placeholder
    }
    
    strava_connected = bool(g.strava_token_data)
    strava_activities = []
    conn = None

    if strava_connected:
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            current_user_id = g.user.get("id")
            # CORREÇÃO: Usar aspas simples para strings SQL
            sql_query = """
                SELECT id, name, distance, moving_time, type, start_date
                FROM strava_activities
                WHERE user_id = %s
                  AND type IN ('Run', 'Walk') 
                ORDER BY start_date DESC
                LIMIT 5
            """
            # print(f"DEBUG: [dashboard] Executing query: {sql_query} with user_id: {current_user_id}") # Debug query
            cur.execute(sql_query, (current_user_id,))
            strava_activities = cur.fetchall()
            cur.close()
        except (Exception, psycopg2.DatabaseError) as db_error:
            error_details = traceback.format_exc()
            print(f"!!! DB ERROR fetching Strava activities for dashboard: {db_error}\n{error_details}")
            flash("Erro ao buscar atividades recentes do Strava.", "error")
            strava_activities = [] 
        finally:
            if conn:
                conn.close()

    try: 
        return render_template("dashboard.html", 
                               user=user_data, 
                               strava_connected=strava_connected,
                               strava_activities=strava_activities)
    except Exception as e: 
        print(f"!!! CRITICAL Render ERROR dashboard: {e}\n{traceback.format_exc()}") 
        return "Erro interno ao carregar o dashboard. Por favor, tente novamente mais tarde.", 500

# --- Rota de Ranking (Individual e por Equipes) --- 
@app.route("/ranking")
@login_required
def ranking_page():
    print("DEBUG: [ranking_page] Entered route")
    conn = None
    users_ranking = []
    teams_ranking = []
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Ranking Individual
        print("DEBUG: [ranking_page] Fetching users for individual ranking from DB")
        cur.execute("""
            SELECT username, points 
            FROM users
            ORDER BY points DESC, username ASC
            LIMIT 100 
        """)
        users_ranking = cur.fetchall()
        print(f"DEBUG: [ranking_page] Fetched {len(users_ranking)} users for individual ranking")

        # Ranking por Equipes
        print("DEBUG: [ranking_page] Fetching teams for team ranking from DB")
        cur.execute("""
            SELECT 
                t.id, 
                t.name, 
                COALESCE(SUM(u.points), 0) AS total_points,
                COUNT(u.id) AS member_count
            FROM teams t
            LEFT JOIN users u ON t.id = u.team_id
            GROUP BY t.id, t.name
            ORDER BY total_points DESC, t.name ASC;
        """)
        teams_ranking = cur.fetchall()
        print(f"DEBUG: [ranking_page] Fetched {len(teams_ranking)} teams for ranking")
        
        cur.close()
    except psycopg2.errors.UndefinedTable as ut_err: # Catch specific error for teams table
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [ranking_page]: TABLE 'teams' DOES NOT EXIST? {ut_err}\n{error_details}") 
        flash("Erro ao carregar ranking de equipes: estrutura do banco de dados incompleta.", "error")
        # Allow rendering individual ranking even if teams fail
        teams_ranking = [] 
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [ranking_page] fetching rankings: {db_error}\n{error_details}")
        flash("Erro ao carregar os rankings.", "error")
    finally:
        if conn:
            print("DEBUG: [ranking_page] Closing DB connection.")
            conn.close()
    
    try:
        print("DEBUG: [ranking_page] Rendering ranking.html with both rankings")
        return render_template("ranking.html", 
                               users_ranking=users_ranking, 
                               teams_ranking=teams_ranking)
    except Exception as render_error:
        print(f"!!! Render ERROR [ranking_page] rendering ranking.html: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar a página de ranking.", 500

# --- Rotas de Equipes --- 

@app.route("/teams")
@login_required
def list_teams_page():
    print("DEBUG: [list_teams_page] Entered route.") # Added
    conn = None
    teams = []
    try:
        print("DEBUG: [list_teams_page] Attempting to get DB connection.") # Added
        conn = get_db_connection()
        print("DEBUG: [list_teams_page] DB connection obtained.") # Added
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        print("DEBUG: [list_teams_page] Cursor created. Executing query for teams.") # Added
        cur.execute("SELECT id, name, description, created_at FROM teams ORDER BY name ASC")
        print("DEBUG: [list_teams_page] Query executed.") # Added
        teams = cur.fetchall()
        print(f"DEBUG: [list_teams_page] Fetched {len(teams)} teams.")
        cur.close()
        print("DEBUG: [list_teams_page] Cursor closed.") # Added
    except psycopg2.errors.UndefinedTable as ut_err: # Catch specific error
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [list_teams_page]: TABLE 'teams' DOES NOT EXIST. {ut_err}\n{error_details}") # Specific log
        flash("Erro crítico: A estrutura do banco de dados para equipes não foi encontrada. Contate o administrador.", "error")
        # Don't try to render the page if the table doesn't exist
        return redirect(url_for("dashboard")) # Redirect somewhere safe
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [list_teams_page] fetching teams: {db_error}\n{error_details}")
        flash("Erro ao carregar a lista de equipes.", "error")
        # Optionally redirect if error is severe
        return redirect(url_for("dashboard"))
    finally:
        if conn:
            print("DEBUG: [list_teams_page] Closing DB connection.") # Added
            conn.close()

    # Only attempt to render if no critical error occurred
    try:
        print("DEBUG: [list_teams_page] Attempting to render teams.html") # Added
        return render_template("teams.html", teams=teams)
    except Exception as render_error:
        print(f"!!! Render ERROR [list_teams_page] rendering teams.html: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar a página de equipes.", 500

@app.route("/teams/create", methods=("GET", "POST"))
@login_required
def create_team_page():
    print(f"DEBUG: [create_team_page] Entered route, method: {request.method}")
    form_data = {}
    if request.method == "POST":
        print("DEBUG: [create_team_page] Processing POST request")
        conn = None
        try:
            team_name = request.form.get("name")
            description = request.form.get("description")
            print(f"DEBUG: [create_team_page] Form data received: name={team_name}, desc={description[:20]}...")

            if not team_name:
                print("WARN: [create_team_page] Validation failed (name missing).")
                flash("O nome da equipe é obrigatório.", "warning")
                form_data = request.form
                return render_template("create_team.html", form_data=form_data)

            conn = get_db_connection()
            cur = conn.cursor()
            sql = "INSERT INTO teams (name, description) VALUES (%s, %s);"
            print("DEBUG: [create_team_page] Executing INSERT query for new team")
            cur.execute(sql, (team_name, description))
            conn.commit()
            print("DEBUG: [create_team_page] New team inserted and committed.")
            cur.close()
            flash(f"Equipe '{team_name}' criada com sucesso!", "success") 
            return redirect(url_for("list_teams_page"))

        except psycopg2.errors.UniqueViolation:
            print(f"WARN: [create_team_page] Team name '{team_name}' already exists.") 
            flash("Já existe uma equipe com este nome. Escolha outro.", "warning")
            if conn: conn.rollback()
            form_data = request.form
        except psycopg2.errors.UndefinedTable as ut_err: # Catch specific error
             error_details = traceback.format_exc()
             print(f"!!! DB ERROR [create_team_page]: TABLE 'teams' DOES NOT EXIST? {ut_err}\n{error_details}") 
             flash("Erro ao criar equipe: estrutura do banco de dados incompleta.", "error")
             if conn: conn.rollback()
             form_data = request.form
        except (Exception, psycopg2.DatabaseError) as db_error:
            error_details = traceback.format_exc()
            print(f"!!! DB ERROR [create_team_page] creating team: {db_error}\n{error_details}")
            flash("Erro ao criar a equipe no banco de dados.", "error")
            if conn: conn.rollback()
            form_data = request.form
        finally:
            if conn:
                print("DEBUG: [create_team_page] Closing DB connection (POST).")
                conn.close()
    
    try:
        print("DEBUG: [create_team_page] Rendering create_team.html for GET request or POST error")
        return render_template("create_team.html", form_data=form_data)
    except Exception as render_error:
        print(f"!!! Render ERROR [create_team_page] rendering create_team.html: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar o formulário de criação de equipe.", 500

@app.route("/teams/<int:team_id>/join", methods=["POST"])
@login_required
def join_team(team_id):
    print(f"DEBUG: [join_team] Entered route for team_id: {team_id}")
    user_id = g.user.get("id")
    current_team_id = g.user.get("team_id")
    conn = None

    if current_team_id:
        print(f"WARN: [join_team] User {user_id} attempted to join team {team_id} but already belongs to team {current_team_id}.")
        flash("Você já pertence a uma equipe. Saia da equipe atual antes de entrar em outra.", "warning")
        return redirect(url_for("list_teams_page"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        print(f"DEBUG: [join_team] Updating user {user_id} to join team {team_id}")
        # First, check if team exists to give a better error message
        cur.execute("SELECT id FROM teams WHERE id = %s", (team_id,))
        if cur.fetchone() is None:
            print(f"WARN: [join_team] Attempted to join non-existent team {team_id}.")
            flash("A equipe que você tentou entrar não existe.", "error")
            cur.close()
            return redirect(url_for("list_teams_page"))
            
        # Team exists, proceed to update user
        cur.execute("UPDATE users SET team_id = %s WHERE id = %s", (team_id, user_id))
        conn.commit()
        cur.close()
        g.user["team_id"] = team_id 
        print(f"DEBUG: [join_team] User {user_id} successfully joined team {team_id}.")
        flash("Você entrou na equipe!", "success")
    except psycopg2.errors.UndefinedTable as ut_err: # Catch specific error
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [join_team]: TABLE 'teams' or 'users' DOES NOT EXIST? {ut_err}\n{error_details}") 
        flash("Erro ao entrar na equipe: estrutura do banco de dados incompleta.", "error")
        if conn: conn.rollback()
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [join_team] joining team: {db_error}\n{error_details}")
        flash("Erro ao tentar entrar na equipe.", "error")
        if conn: conn.rollback()
    finally:
        if conn:
            print("DEBUG: [join_team] Closing DB connection.")
            conn.close()
            
    return redirect(url_for("list_teams_page"))

@app.route("/teams/leave", methods=["POST"])
@login_required
def leave_team():
    print(f"DEBUG: [leave_team] Entered route")
    user_id = g.user.get("id")
    current_team_id = g.user.get("team_id")
    conn = None

    if not current_team_id:
        print(f"WARN: [leave_team] User {user_id} attempted to leave team but does not belong to any.")
        flash("Você não pertence a nenhuma equipe.", "warning")
        return redirect(url_for("list_teams_page"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        print(f"DEBUG: [leave_team] Updating user {user_id} to leave team {current_team_id}")
        cur.execute("UPDATE users SET team_id = NULL WHERE id = %s", (user_id,))
        conn.commit()
        cur.close()
        g.user["team_id"] = None
        print(f"DEBUG: [leave_team] User {user_id} successfully left team {current_team_id}.")
        flash("Você saiu da equipe.", "success")
    except psycopg2.errors.UndefinedTable as ut_err: # Catch specific error
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [leave_team]: TABLE 'users' DOES NOT EXIST? {ut_err}\n{error_details}") 
        flash("Erro ao sair da equipe: estrutura do banco de dados incompleta.", "error")
        if conn: conn.rollback()
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [leave_team] leaving team: {db_error}\n{error_details}")
        flash("Erro ao tentar sair da equipe.", "error")
        if conn: conn.rollback()
    finally:
        if conn:
            print("DEBUG: [leave_team] Closing DB connection.")
            conn.close()
            
    return redirect(url_for("list_teams_page"))

# --- Rotas do Mural de Doações --- 

@app.route("/mural")
def mural_page():
    conn = None
    items = []
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT di.*, u.username AS donor_username 
            FROM donation_items di
            JOIN users u ON di.user_id = u.id
            ORDER BY di.created_at DESC
        """)
        items = cur.fetchall()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR fetching donation items: {db_error}\n{error_details}")
        flash("Erro ao carregar os itens do mural.", "error")
    finally:
        if conn:
            conn.close()
    
    try:
        return render_template("mural.html", items=items)
    except Exception as render_error:
        print(f"!!! Render ERROR mural: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar o mural de doações.", 500

@app.route("/mural/add", methods=("GET", "POST"))
@login_required
def add_donation_item_page():
    if request.method == "POST":
        conn = None
        try:
            item_name = request.form.get("item_name")
            description = request.form.get("description")
            user_id = g.user.get("id")

            if not item_name:
                flash("O nome do item é obrigatório.", "warning")
                return render_template("add_donation_item.html", form_data=request.form)

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO donation_items (user_id, item_name, description) VALUES (%s, %s, %s)",
                        (user_id, item_name, description))
            conn.commit()
            cur.close()
            flash("Item adicionado ao mural com sucesso!", "success")
            return redirect(url_for("mural_page"))

        except (Exception, psycopg2.DatabaseError) as db_error:
            error_details = traceback.format_exc()
            print(f"!!! DB ERROR adding donation item: {db_error}\n{error_details}")
            flash("Erro ao adicionar o item ao banco de dados.", "error")
            if conn: conn.rollback()
            return render_template("add_donation_item.html", form_data=request.form)
        finally:
            if conn:
                conn.close()
    
    try:
        return render_template("add_donation_item.html", form_data={})
    except Exception as render_error:
        print(f"!!! Render ERROR add_donation_item: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar o formulário de adição de item.", 500

# --- Rotas de Conexão Strava --- 

@app.route("/conectar")
@login_required
def conectar_page():
    strava_connected = bool(g.strava_token_data)
    connection_date = None
    if strava_connected and g.strava_token_data.get("created_at"):
        connection_date = g.strava_token_data["created_at"].strftime("%d/%m/%Y %H:%M")
    
    # Adiciona a variável de depuração
    debug_strava_connected = strava_connected
    
    try:
        return render_template("conectar-apps.html", 
                               strava_connected=strava_connected, 
                               connection_date=connection_date,
                               debug_strava_connected=debug_strava_connected) # Passa para o template
    except Exception as e:
        print(f"!!! Render ERROR conectar-apps: {e}\n{traceback.format_exc()}")
        return "Erro ao carregar a página de conexão.", 500

@app.route("/strava/login")
@login_required
def strava_login():
    strava = OAuth2Session(STRAVA_CLIENT_ID, redirect_uri=STRAVA_REDIRECT_URI, scope=STRAVA_SCOPES)
    authorization_url, state = strava.authorization_url(STRAVA_AUTHORIZATION_URL)
    session["oauth_state"] = state
    return redirect(authorization_url)

@app.route("/strava/callback")
@login_required
def strava_callback():
    print("DEBUG: [strava_callback] Received callback from Strava")
    if 'oauth_state' not in session or request.args.get('state') != session['oauth_state']:
        print("ERROR: [strava_callback] OAuth state mismatch")
        flash("Erro de segurança na autenticação Strava (state mismatch).", "error")
        return redirect(url_for("conectar_page"))

    if 'error' in request.args:
        error_desc = request.args.get('error')
        print(f"ERROR: [strava_callback] Strava authorization denied: {error_desc}")
        flash(f"Autorização do Strava negada: {error_desc}", "warning")
        return redirect(url_for("conectar_page"))

    strava = OAuth2Session(STRAVA_CLIENT_ID, state=session['oauth_state'], redirect_uri=STRAVA_REDIRECT_URI)
    conn = None
    try:
        print("DEBUG: [strava_callback] Fetching token from Strava")
        token = strava.fetch_token(STRAVA_TOKEN_URL, client_secret=STRAVA_CLIENT_SECRET, authorization_response=request.url)
        print(f"DEBUG: [strava_callback] Received token response (keys only): {list(token.keys()) if token else 'None'}")

        if not token or 'access_token' not in token:
             print("ERROR: [strava_callback] Failed to fetch token or token is invalid")
             flash("Falha ao obter o token de acesso do Strava.", "error")
             return redirect(url_for("conectar_page"))

        # Salvar o token no banco de dados
        user_id = g.user.get("id")
        access_token = token["access_token"]
        refresh_token = token.get("refresh_token")
        expires_at_ts = token.get("expires_at")
        expires_at_dt = datetime.datetime.fromtimestamp(expires_at_ts, tz=datetime.timezone.utc) if expires_at_ts else None
        strava_athlete_id = token.get("athlete", {}).get("id") # Pegar ID do atleta Strava

        print(f"DEBUG: [strava_callback] Preparing to save token for user {user_id}. Expires at: {expires_at_dt}")

        conn = get_db_connection()
        cur = conn.cursor()
        
        # Usar INSERT ... ON CONFLICT para atualizar se já existir
        sql = """
            INSERT INTO strava_tokens (user_id, access_token, refresh_token, expires_at, strava_athlete_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at,
                strava_athlete_id = EXCLUDED.strava_athlete_id,
                updated_at = NOW();
        """
        cur.execute(sql, (user_id, access_token, refresh_token, expires_at_dt, strava_athlete_id))
        conn.commit()
        cur.close()
        print(f"DEBUG: [strava_callback] Token for user {user_id} saved/updated successfully.")
        flash("Conta Strava conectada com sucesso!", "success")
        return redirect(url_for("conectar_page"))

    except Exception as e:
        error_details = traceback.format_exc()
        print(f"!!! ERROR [strava_callback] during token fetch/save: {e}\n{error_details}")
        flash("Ocorreu um erro inesperado ao conectar com o Strava.", "error")
        if conn: conn.rollback()
        return redirect(url_for("conectar_page"))
    finally:
        if conn:
            print("DEBUG: [strava_callback] Closing DB connection.")
            conn.close()

@app.route("/strava/disconnect", methods=["POST"])
@login_required
def strava_disconnect():
    print("DEBUG: [strava_disconnect] Entered route")
    user_id = g.user.get("id")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        print(f"DEBUG: [strava_disconnect] Deleting Strava token for user {user_id}")
        cur.execute("DELETE FROM strava_tokens WHERE user_id = %s", (user_id,))
        conn.commit()
        cur.close()
        g.strava_token_data = None # Limpa o token da sessão global
        print(f"DEBUG: [strava_disconnect] Token for user {user_id} deleted successfully.")
        flash("Conta Strava desconectada.", "info")
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [strava_disconnect] disconnecting Strava: {db_error}\n{error_details}")
        flash("Erro ao desconectar a conta Strava.", "error")
        if conn: conn.rollback()
    finally:
        if conn:
            print("DEBUG: [strava_disconnect] Closing DB connection.")
            conn.close()
            
    return redirect(url_for("conectar_page"))

@app.route("/strava/fetch_activities", methods=["POST"])
@login_required
def fetch_strava_activities():
    print("DEBUG: [fetch_strava_activities] Entered route")
    if not g.strava_token_data:
        print("WARN: [fetch_strava_activities] User attempted to fetch activities without Strava connection.")
        flash("Conecte sua conta Strava primeiro.", "warning")
        return redirect(url_for("conectar_page"))

    access_token = g.strava_token_data.get("access_token")
    user_id = g.user.get("id")
    user_created_at = g.user.get("created_at")

    if not access_token:
        print("ERROR: [fetch_strava_activities] No access token found in g.strava_token_data")
        flash("Erro interno: token de acesso não encontrado.", "error")
        return redirect(url_for("conectar_page"))
        
    if not user_created_at:
        print(f"ERROR: [fetch_strava_activities] User {user_id} created_at date is missing in g.user")
        flash("Erro interno: Data de cadastro do usuário não encontrada.", "error")
        return redirect(url_for("dashboard"))

    headers = {"Authorization": f"Bearer {access_token}"}
    # Buscar atividades após a data de cadastro do usuário
    # Certifique-se que user_created_at é timezone-aware (UTC preferencialmente)
    if user_created_at.tzinfo is None:
        # Assume UTC if naive, mas o ideal é garantir que seja salvo como UTC no DB
        user_created_at = user_created_at.replace(tzinfo=datetime.timezone.utc)
        print("WARN: [fetch_strava_activities] user_created_at was naive, assuming UTC.")
        
    params = {"after": int(user_created_at.timestamp())}
    print(f"DEBUG: [fetch_strava_activities] Fetching activities from Strava API for user {user_id} after {user_created_at}")

    conn = None
    new_activities_count = 0
    updated_activities_count = 0
    ignored_activities_count = 0
    total_points_added = 0

    try:
        response = requests.get(f"{STRAVA_API_BASE_URL}/athlete/activities", headers=headers, params=params)
        response.raise_for_status() # Levanta erro para status HTTP 4xx/5xx
        activities = response.json()
        print(f"DEBUG: [fetch_strava_activities] Received {len(activities)} activities from Strava API")

        if not activities:
            flash("Nenhuma nova atividade encontrada no Strava desde o seu cadastro.", "info")
            return redirect(url_for("dashboard"))

        conn = get_db_connection()
        cur = conn.cursor()

        for activity in activities:
            activity_id = activity.get("id")
            activity_type = activity.get("type")
            distance_meters = activity.get("distance", 0)
            moving_time_seconds = activity.get("moving_time", 0)
            start_date_str = activity.get("start_date") # Use start_date (UTC) para consistência
            name = activity.get("name", "Atividade sem nome")
            
            # Converter data/hora UTC para objeto datetime com fuso horário
            try:
                # Strava API v3 usually returns ISO 8601 format like '2018-02-20T10:02:13Z'
                start_date_dt = datetime.datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                print(f"WARN: [fetch_strava_activities] Could not parse start_date '{start_date_str}' for activity {activity_id}. Skipping.")
                ignored_activities_count += 1
                continue
                
            # Comparar com user_created_at (ambos devem ser timezone-aware)
            if start_date_dt < user_created_at:
                # print(f"DEBUG: [fetch_strava_activities] Skipping activity {activity_id} (started before user registration: {start_date_dt} < {user_created_at})")
                ignored_activities_count += 1
                continue

            # Verificar se a atividade já existe no banco
            cur.execute("SELECT id, points_calculated FROM strava_activities WHERE id = %s", (activity_id,))
            existing_activity = cur.fetchone()

            points_for_activity = 0
            # Calcular pontos apenas para Corridas e Caminhadas
            # Python check - OK
            if activity_type in ('Run', 'Walk'):
                distance_km = distance_meters / 1000.0
                points_for_activity = math.floor(distance_km) # 1 ponto por KM completo
            else:
                # Não é Run ou Walk, não calcula pontos
                # print(f"DEBUG: [fetch_strava_activities] Ignoring activity {activity_id} (type: {activity_type}) for points calculation.")
                pass # Não incrementa ignored_activities_count aqui, pois ainda pode ser salva

            # Flag indica se a atividade é do tipo que GERA pontos (Run/Walk)
            points_eligible_flag = (activity_type in ('Run', 'Walk'))

            if existing_activity:
                existing_id, existing_points_calculated = existing_activity
                # Atualizar se: 
                # 1. Atividade é elegível para pontos E ainda não foram calculados
                # 2. Ou talvez outros campos mudaram (nome, etc.) - por simplicidade, focamos nos pontos
                should_update = points_eligible_flag and not existing_points_calculated
                
                if should_update:
                    print(f"DEBUG: [fetch_strava_activities] Updating activity {activity_id} (was not calculated, now eligible). Adding {points_for_activity} points.")
                    cur.execute("""
                        UPDATE strava_activities 
                        SET name = %s, distance = %s, moving_time = %s, type = %s, start_date = %s, points_calculated = TRUE, updated_at = NOW()
                        WHERE id = %s
                    """, (name, distance_meters, moving_time_seconds, activity_type, start_date_dt, activity_id))
                    updated_activities_count += 1
                    total_points_added += points_for_activity
                # else: # Debug
                    # print(f"DEBUG: [fetch_strava_activities] No update needed for existing activity {activity_id} (Eligible: {points_eligible_flag}, Calculated: {existing_points_calculated})")
                    
            else:
                # Inserir nova atividade
                points_calculated_on_insert = points_eligible_flag # Marca como calculado se for elegível
                print(f"DEBUG: [fetch_strava_activities] Inserting new activity {activity_id} (Eligible: {points_eligible_flag}). Adding {points_for_activity if points_eligible_flag else 0} points.")
                cur.execute("""
                    INSERT INTO strava_activities (id, user_id, name, distance, moving_time, type, start_date, points_calculated, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                """, (activity_id, user_id, name, distance_meters, moving_time_seconds, activity_type, start_date_dt, points_calculated_on_insert))
                new_activities_count += 1
                if points_eligible_flag:
                    total_points_added += points_for_activity
                    
            # Se a atividade não for Run/Walk, contamos como ignorada para pontuação
            if not points_eligible_flag:
                 ignored_activities_count += 1

        # Atualizar pontuação total do usuário APENAS com os pontos adicionados nesta execução
        if total_points_added > 0:
            print(f"DEBUG: [fetch_strava_activities] Updating total points for user {user_id}. Adding {total_points_added} points.")
            cur.execute("UPDATE users SET points = points + %s WHERE id = %s", (total_points_added, user_id))
            # Atualizar g.user para refletir novos pontos imediatamente no dashboard
            if g.user: # Check if g.user exists
                 g.user["points"] = g.user.get("points", 0) + total_points_added

        conn.commit()
        cur.close()
        
        # Mensagem mais clara
        current_total_points = g.user.get('points', 'N/A') if g.user else 'N/A'
        flash_message = f"{new_activities_count} novas atividades importadas, {updated_activities_count} atualizadas. {ignored_activities_count} atividades não eram corridas/caminhadas ou ocorreram antes do cadastro. Sua pontuação total é {current_total_points}."
        flash(flash_message, "success")
        print(f"DEBUG: [fetch_strava_activities] Activity fetch complete. {flash_message}")

    except requests.exceptions.RequestException as req_err:
        error_details = traceback.format_exc()
        print(f"!!! Strava API ERROR fetching activities: {req_err}\n{error_details}")
        flash("Erro ao comunicar com a API do Strava para buscar atividades.", "error")
    except psycopg2.errors.UndefinedTable as ut_err: # Catch specific error
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [fetch_strava_activities]: TABLE 'strava_activities' or 'users' DOES NOT EXIST? {ut_err}\n{error_details}") 
        flash("Erro ao processar atividades: estrutura do banco de dados incompleta.", "error")
        if conn: conn.rollback()
    except (Exception, psycopg2.DatabaseError) as db_err:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [fetch_strava_activities] processing activities: {db_err}\n{error_details}")
        flash("Erro no banco de dados ao processar as atividades do Strava.", "error")
        if conn: conn.rollback()
    finally:
        if conn:
            print("DEBUG: [fetch_strava_activities] Closing DB connection.")
            conn.close()

    return redirect(url_for("dashboard"))

# --- Ponto de Entrada Principal --- 

if __name__ == "__main__":
    # Usar Waitress como servidor de produção WSGI
    # from waitress import serve
    # serve(app, host="0.0.0.0", port=5000)
    
    # Usar o servidor de desenvolvimento do Flask (apenas para depuração local)
    app.run(debug=True, host="0.0.0.0", port=5000)

