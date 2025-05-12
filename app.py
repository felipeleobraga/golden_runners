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
                  AND type IN (
                    'Run', 'Walk', 'VirtualRun', 'TrailRun', 'Hike', 
                    'Wheelchair', 'Snowshoe', 'Crossfit', 'Elliptical', 
                    'StairStepper', 'WeightTraining', 'Workout', 'Yoga', 
                    'Swim', 'VirtualRide', 'Ride', 'EBikeRide', 'GravelRide', 
                    'Handcycle', 'MountainBikeRide', 'RollerSki', 'NordicSki', 
                    'AlpineSki', 'BackcountrySki', 'IceSkate', 'InlineSkate', 
                    'RockClimbing', 'Rowing', 'Sail', 'Skateboard', 'Soccer', 
                    'Surfing', 'Velomobile', 'Windsurf', 'Wingfoil', 'Golf', 
                    'Pickleball', 'Racquetball', 'Badminton', 'Squash', 
                    'TableTennis', 'Tennis', 'Canoeing', 'Kayaking', 
                    'Kitesurf', 'StandUpPaddling', 'WaterSki', 'Windsurf', 
                    'Rowing', 'VirtualRow'
                    )
                ORDER BY start_date DESC
                LIMIT 100
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
        return "Erro ao carregar a página de criação de equipe.", 500

@app.route("/teams/join/<int:team_id>", methods=["POST"])
@login_required
def join_team(team_id):
    print(f"DEBUG: [join_team] User {g.user['id']} attempting to join team {team_id}")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Verifica se a equipe existe
        cur.execute("SELECT id FROM teams WHERE id = %s", (team_id,))
        if not cur.fetchone():
            print(f"WARN: [join_team] Team {team_id} not found.")
            flash("Equipe não encontrada.", "error")
            return redirect(url_for("list_teams_page"))

        # Verifica se o usuário já está em uma equipe
        if g.user.get("team_id") is not None:
            print(f"WARN: [join_team] User {g.user['id']} already in team {g.user.get('team_id')}.")
            flash("Você já faz parte de uma equipe. Saia da equipe atual para entrar em uma nova.", "warning")
            return redirect(url_for("list_teams_page"))

        sql = "UPDATE users SET team_id = %s WHERE id = %s"
        print(f"DEBUG: [join_team] Executing UPDATE query to add user {g.user['id']} to team {team_id}")
        cur.execute(sql, (team_id, g.user["id"]))
        conn.commit()
        print("DEBUG: [join_team] User successfully joined team.")
        cur.close()
        flash("Você entrou na equipe com sucesso!", "success")
    except psycopg2.errors.UndefinedTable as ut_err: # Catch specific error
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [join_team]: TABLE 'teams' or 'users' DOES NOT EXIST? {ut_err}\n{error_details}") 
        flash("Erro ao entrar na equipe: estrutura do banco de dados incompleta.", "error")
        if conn: conn.rollback()
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [join_team] joining team: {db_error}\n{error_details}")
        flash("Erro ao entrar na equipe.", "error")
        if conn: conn.rollback()
    finally:
        if conn:
            print("DEBUG: [join_team] Closing DB connection.")
            conn.close()
    return redirect(url_for("list_teams_page"))

@app.route("/teams/leave", methods=["POST"])
@login_required
def leave_team():
    print(f"DEBUG: [leave_team] User {g.user['id']} attempting to leave team.")
    conn = None
    try:
        if g.user.get("team_id") is None:
            print(f"WARN: [leave_team] User {g.user['id']} is not in any team.")
            flash("Você não faz parte de nenhuma equipe.", "warning")
            return redirect(url_for("list_teams_page"))

        conn = get_db_connection()
        cur = conn.cursor()
        sql = "UPDATE users SET team_id = NULL WHERE id = %s"
        print(f"DEBUG: [leave_team] Executing UPDATE query to remove user {g.user['id']} from team.")
        cur.execute(sql, (g.user["id"],))
        conn.commit()
        print("DEBUG: [leave_team] User successfully left team.")
        cur.close()
        flash("Você saiu da equipe.", "success")
    except psycopg2.errors.UndefinedTable as ut_err: # Catch specific error
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [leave_team]: TABLE 'users' DOES NOT EXIST? {ut_err}\n{error_details}") 
        flash("Erro ao sair da equipe: estrutura do banco de dados incompleta.", "error")
        if conn: conn.rollback()
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [leave_team] leaving team: {db_error}\n{error_details}")
        flash("Erro ao sair da equipe.", "error")
        if conn: conn.rollback()
    finally:
        if conn:
            print("DEBUG: [leave_team] Closing DB connection.")
            conn.close()
    return redirect(url_for("list_teams_page"))

# --- Rotas do Mural de Doações ---

@app.route("/mural")
@login_required
def mural_page():
    print("DEBUG: [mural_page] Entered route")
    conn = None
    items = []
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) # Para pegar como dict
        print("DEBUG: [mural_page] Fetching donation items from DB")
        # Adicionar JOIN com users para pegar o nome do doador
        cur.execute("""
            SELECT 
                di.id, di.title, di.description, di.category, 
                di.status, di.image_url, di.created_at, 
                u.username AS owner_username, 
                di.location 
            FROM donation_items di
            JOIN users u ON di.owner_user_id = u.id
            ORDER BY di.created_at DESC
        """)
        items = cur.fetchall()
        print(f"DEBUG: [mural_page] Fetched {len(items)} items from DB")
        cur.close()
    except psycopg2.errors.UndefinedTable as ut_err: # Captura erro se a tabela não existir
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [mural_page]: TABLE 'donation_items' or 'users' DOES NOT EXIST? {ut_err}\n{error_details}")
        flash("Erro ao carregar o mural: a estrutura do banco de dados parece estar incompleta. Contate o suporte.", "error")
        # Redireciona para uma página segura se a tabela não existir
        return redirect(url_for('dashboard')) 
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [mural_page] fetching items: {db_error}\n{error_details}")
        flash("Erro ao carregar os itens do mural.", "error")
    finally:
        if conn:
            print("DEBUG: [mural_page] Closing DB connection.")
            conn.close()
    
    try:
        print("DEBUG: [mural_page] Rendering mural.html")
        return render_template("mural.html", items=items)
    except Exception as render_error:
        print(f"!!! Render ERROR [mural_page] rendering mural.html: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar a página do mural.", 500

@app.route("/mural/add", methods=("GET", "POST"))
@login_required
def add_donation_item_page():
    print(f"DEBUG: [add_donation_item_page] Entered route, method: {request.method}")
    form_data = {}
    if request.method == "POST":
        print("DEBUG: [add_donation_item_page] Processing POST request")
        conn = None
        try:
            title = request.form.get("title")
            description = request.form.get("description")
            category = request.form.get("category")
            location = request.form.get("location")
            image_url = request.form.get("image_url") # Pode ser opcional
            owner_user_id = g.user["id"]
            
            print(f"DEBUG: [add_donation_item_page] Form data: title='{title}', category='{category}', owner='{owner_user_id}'")

            if not title or not category:
                print("WARN: [add_donation_item_page] Validation failed (title or category missing).")
                flash("Título e categoria são obrigatórios.", "warning")
                form_data = request.form
                return render_template("add_item.html", form_data=form_data)

            conn = get_db_connection()
            cur = conn.cursor()
            sql = """
                INSERT INTO donation_items 
                (title, description, category, owner_user_id, image_url, location, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'available')
            """
            print("DEBUG: [add_donation_item_page] Executing INSERT query for new donation item")
            cur.execute(sql, (title, description, category, owner_user_id, image_url, location))
            conn.commit()
            print("DEBUG: [add_donation_item_page] New item inserted and committed.")
            cur.close()
            flash("Item adicionado ao mural com sucesso!", "success")
            return redirect(url_for("mural_page"))

        except psycopg2.errors.UndefinedTable as ut_err: # Captura erro se a tabela não existir
            error_details = traceback.format_exc()
            print(f"!!! DB ERROR [add_donation_item_page]: TABLE 'donation_items' DOES NOT EXIST? {ut_err}\n{error_details}")
            flash("Erro ao adicionar item: a estrutura do banco de dados parece estar incompleta.", "error")
            if conn: conn.rollback()
            form_data = request.form
        except (Exception, psycopg2.DatabaseError) as db_error:
            error_details = traceback.format_exc()
            print(f"!!! DB ERROR [add_donation_item_page] adding item: {db_error}\n{error_details}")
            flash("Erro ao adicionar o item no banco de dados.", "error")
            if conn: conn.rollback()
            form_data = request.form
        finally:
            if conn:
                print("DEBUG: [add_donation_item_page] Closing DB connection (POST).")
                conn.close()
    
    try:
        print("DEBUG: [add_donation_item_page] Rendering add_item.html for GET or POST error")
        return render_template("add_item.html", form_data=form_data)
    except Exception as render_error:
        print(f"!!! Render ERROR [add_donation_item_page] rendering add_item.html: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar a página de adicionar item.", 500

# --- Rotas de Conexão com Strava --- 

@app.route("/strava/login")
@login_required
def strava_login():
    print("DEBUG: [strava_login] Initiating Strava OAuth flow.")
    if not STRAVA_CLIENT_ID or not STRAVA_CLIENT_SECRET or not STRAVA_REDIRECT_URI:
        print("!!! ERROR: Strava client credentials or redirect URI not configured.")
        flash("Configuração do Strava incompleta no servidor. Não é possível conectar.", "error")
        return redirect(url_for("conectar_apps_page"))
    
    strava_session = OAuth2Session(STRAVA_CLIENT_ID, redirect_uri=STRAVA_REDIRECT_URI, scope=STRAVA_SCOPES)
    authorization_url, state = strava_session.authorization_url(STRAVA_AUTHORIZATION_URL)
    session["strava_oauth_state"] = state # Salva o estado para verificar no callback
    print(f"DEBUG: [strava_login] Redirecting to Strava: {authorization_url}")
    return redirect(authorization_url)

@app.route("/strava/callback")
@login_required
def strava_callback():
    print("DEBUG: [strava_callback] Received callback from Strava.")
    # Verifica o estado para proteção CSRF
    if request.args.get("state") != session.get("strava_oauth_state"):
        print("!!! ERROR: [strava_callback] OAuth state mismatch. Possible CSRF.")
        flash("Erro de segurança na autenticação com o Strava (state mismatch).", "error")
        return redirect(url_for("conectar_apps_page"))

    # Verifica se houve erro na autorização do Strava (e.g., usuário negou)
    if "error" in request.args:
        error_description = request.args.get("error", "desconhecido")
        print(f"WARN: [strava_callback] Strava authorization denied or failed: {error_description}")
        flash(f"Acesso ao Strava negado ou falhou: {error_description}.", "warning")
        return redirect(url_for("conectar_apps_page"))

    strava_session = OAuth2Session(STRAVA_CLIENT_ID, state=session.get("strava_oauth_state"), redirect_uri=STRAVA_REDIRECT_URI)
    
    conn = None
    try:
        print("DEBUG: [strava_callback] Fetching token from Strava.")
        token_response = strava_session.fetch_token(
            STRAVA_TOKEN_URL,
            client_secret=STRAVA_CLIENT_SECRET,
            authorization_response=request.url # Passa a URL completa do callback
        )
        print("DEBUG: [strava_callback] Token fetched successfully from Strava.")
        
        # Extrai os dados do token
        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")
        expires_at_timestamp = token_response.get("expires_at")
        # Converte timestamp para datetime UTC
        expires_at_dt = datetime.datetime.fromtimestamp(expires_at_timestamp, tz=datetime.timezone.utc)
        
        # Pega o ID do atleta do Strava (vem junto com a resposta do token)
        strava_athlete_id = token_response.get("athlete", {}).get("id")
        if not strava_athlete_id:
            print("!!! ERROR: [strava_callback] Strava athlete ID not found in token response.")
            flash("Não foi possível obter o ID do atleta do Strava.", "error")
            return redirect(url_for("conectar_apps_page"))

        print(f"DEBUG: [strava_callback] Strava Athlete ID: {strava_athlete_id}, Access Token: {access_token[:10]}..., Expires at: {expires_at_dt}")

        # Salva/Atualiza o token no banco de dados
        conn = get_db_connection()
        cur = conn.cursor()
        sql_upsert = """
            INSERT INTO strava_tokens (user_id, strava_athlete_id, access_token, refresh_token, expires_at, scope)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                strava_athlete_id = EXCLUDED.strava_athlete_id,
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at,
                scope = EXCLUDED.scope,
                updated_at = NOW();
        """
        print("DEBUG: [strava_callback] Upserting Strava token into DB.")
        cur.execute(sql_upsert, (
            g.user["id"],
            strava_athlete_id,
            access_token,
            refresh_token,
            expires_at_dt,
            json.dumps(STRAVA_SCOPES) # Salva os escopos como JSON string
        ))
        conn.commit()
        print("DEBUG: [strava_callback] Strava token saved to DB.")
        cur.close()
        
        flash("Conexão com o Strava realizada com sucesso!", "success")
        return redirect(url_for("conectar_apps_page"))

    except requests.exceptions.RequestException as req_err:
        error_details = traceback.format_exc()
        print(f"!!! NETWORK ERROR [strava_callback] fetching token: {req_err}\n{error_details}")
        flash("Erro de comunicação ao tentar obter o token do Strava.", "error")
    except (psycopg2.Error, Exception) as db_err: # Erro no DB ou outro erro genérico
        error_details = traceback.format_exc()
        print(f"!!! DB/GENERAL ERROR [strava_callback] saving token: {db_err}\n{error_details}")
        if conn: conn.rollback()
        flash("Erro ao salvar as informações de conexão com o Strava.", "error")
    finally:
        if conn:
            print("DEBUG: [strava_callback] Closing DB connection.")
            conn.close()
        if "strava_oauth_state" in session:
            del session["strava_oauth_state"] # Limpa o estado da sessão
            print("DEBUG: [strava_callback] OAuth state cleared from session.")

    return redirect(url_for("conectar_apps_page"))

@app.route("/strava/disconnect", methods=["POST"])
@login_required
def strava_disconnect():
    print(f"DEBUG: [strava_disconnect] User {g.user['id']} attempting to disconnect Strava.")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Deleta o token do Strava para este usuário
        sql_delete = "DELETE FROM strava_tokens WHERE user_id = %s"
        print("DEBUG: [strava_disconnect] Executing DELETE query for Strava token.")
        cur.execute(sql_delete, (g.user["id"],))
        conn.commit()
        print("DEBUG: [strava_disconnect] Strava token deleted from DB.")
        cur.close()
        flash("Strava desconectado com sucesso.", "success")
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [strava_disconnect] deleting token: {db_error}\n{error_details}")
        if conn: conn.rollback()
        flash("Erro ao desconectar o Strava.", "error")
    finally:
        if conn:
            print("DEBUG: [strava_disconnect] Closing DB connection.")
            conn.close()
    return redirect(url_for("conectar_apps_page"))

@app.route("/strava/fetch_activities", methods=["POST"])
@login_required
def fetch_strava_activities():
    print(f"DEBUG: [fetch_strava_activities] User {g.user['id']} attempting to fetch Strava activities.")
    if not g.strava_token_data:
        print("WARN: [fetch_strava_activities] No Strava token found for user. Redirecting.")
        flash("Você precisa conectar sua conta Strava primeiro.", "warning")
        return redirect(url_for("conectar_apps_page"))

    # TODO: Implementar lógica de refresh token se necessário aqui
    # if g.strava_token_data['expires_at'] < datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5):
    #     print("INFO: [fetch_strava_activities] Strava token needs refresh. Attempting refresh...")
    #     # Chamar função de refresh e atualizar g.strava_token_data e o DB
    #     pass 

    access_token = g.strava_token_data.get("access_token")
    headers = {"Authorization": f"Bearer {access_token}"}
    # Buscar atividades desde a última sincronização ou um período fixo
    # Por simplicidade, vamos buscar as últimas 30 atividades por enquanto
    params = {"per_page": 30, "page": 1}
    activities_url = f"{STRAVA_API_BASE_URL}/athlete/activities"
    
    conn = None
    activities_fetched_count = 0
    activities_saved_count = 0
    points_earned_total = 0

    try:
        print(f"DEBUG: [fetch_strava_activities] Fetching activities from Strava API: {activities_url}")
        response = requests.get(activities_url, headers=headers, params=params)
        response.raise_for_status() # Lança erro para status HTTP 4xx/5xx
        activities_data = response.json()
        activities_fetched_count = len(activities_data)
        print(f"DEBUG: [fetch_strava_activities] Fetched {activities_fetched_count} activities from Strava API.")

        if not activities_data:
            flash("Nenhuma nova atividade encontrada no Strava.", "info")
            return redirect(url_for("conectar_apps_page"))

        conn = get_db_connection()
        cur = conn.cursor()

        for activity in activities_data:
            activity_id = activity.get("id")
            activity_type = activity.get("type")
            
            # Ignorar tipos de atividade não relevantes para pontuação
            # CORREÇÃO: Usar aspas simples para strings SQL
            relevant_types = [
                'Run', 'Walk', 'VirtualRun', 'TrailRun', 'Hike', 'Wheelchair', 'Snowshoe',
                'Crossfit', 'Elliptical', 'StairStepper', 'WeightTraining', 'Workout', 'Yoga',
                'Swim', 'VirtualRide', 'Ride', 'EBikeRide', 'GravelRide', 'Handcycle', 
                'MountainBikeRide', 'RollerSki', 'NordicSki', 'AlpineSki', 'BackcountrySki', 
                'IceSkate', 'InlineSkate', 'RockClimbing', 'Rowing', 'Sail', 'Skateboard', 
                'Soccer', 'Surfing', 'Velomobile', 'Windsurf', 'Wingfoil', 'Golf', 
                'Pickleball', 'Racquetball', 'Badminton', 'Squash', 'TableTennis', 'Tennis', 
                'Canoeing', 'Kayaking', 'Kitesurf', 'StandUpPaddling', 'WaterSki', 
                'Windsurf', 'Rowing', 'VirtualRow'
            ]
            if activity_type not in relevant_types:
                print(f"DEBUG: [fetch_strava_activities] Skipping activity ID {activity_id} of type '{activity_type}'.")
                continue
            
            # Verificar se a atividade já existe no banco de dados
            cur.execute("SELECT id FROM strava_activities WHERE id = %s AND user_id = %s", (activity_id, g.user["id"]))
            if cur.fetchone():
                print(f"DEBUG: [fetch_strava_activities] Activity ID {activity_id} already exists. Skipping.")
                continue # Atividade já existe, pular

            # Calcular pontos (exemplo: 10 pontos por km de corrida/caminhada, 1 ponto por minuto de outras atividades)
            points_earned = 0
            distance_km = activity.get("distance", 0) / 1000 # Distância em km
            duration_min = activity.get("moving_time", 0) / 60 # Duração em minutos

            if activity_type in ['Run', 'Walk', 'VirtualRun', 'TrailRun', 'Hike', 'Wheelchair']:
                points_earned = math.floor(distance_km * 10) 
            elif duration_min > 0:
                points_earned = math.floor(duration_min * 1)
            
            if points_earned <= 0:
                print(f"DEBUG: [fetch_strava_activities] Activity ID {activity_id} ('{activity.get('name')}') earned 0 points. Skipping save.")
                continue

            # Salvar atividade no banco de dados
            sql_insert_activity = """
                INSERT INTO strava_activities 
                (id, user_id, name, distance, moving_time, elapsed_time, type, 
                 start_date, start_date_local, timezone, total_elevation_gain, 
                 average_speed, max_speed, kilojoules, points_earned, raw_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            start_date_dt = datetime.datetime.fromisoformat(activity.get("start_date").replace("Z", "+00:00"))
            start_date_local_dt = datetime.datetime.fromisoformat(activity.get("start_date_local").replace("Z", "")) # Assumindo que já vem sem Z
            
            print(f"DEBUG: [fetch_strava_activities] Saving activity ID {activity_id} ('{activity.get('name')}') with {points_earned} points.")
            cur.execute(sql_insert_activity, (
                activity_id,
                g.user["id"],
                activity.get("name"),
                activity.get("distance"),
                activity.get("moving_time"),
                activity.get("elapsed_time"),
                activity_type,
                start_date_dt,
                start_date_local_dt,
                activity.get("timezone"),
                activity.get("total_elevation_gain"),
                activity.get("average_speed"),
                activity.get("max_speed"),
                activity.get("kilojoules"),
                points_earned,
                json.dumps(activity) # Salva o JSON bruto da atividade
            ))
            
            # Atualizar pontos do usuário
            sql_update_user_points = "UPDATE users SET points = points + %s WHERE id = %s"
            cur.execute(sql_update_user_points, (points_earned, g.user["id"]))
            
            activities_saved_count += 1
            points_earned_total += points_earned
        
        conn.commit()
        print(f"DEBUG: [fetch_strava_activities] DB commit successful. {activities_saved_count} activities saved, {points_earned_total} points earned.")
        cur.close()
        
        if activities_saved_count > 0:
            flash(f"{activities_saved_count} novas atividades do Strava foram importadas, totalizando {points_earned_total} pontos!", "success")
        else:
            flash("Nenhuma atividade nova (que gera pontos) encontrada no Strava desde a última busca.", "info")

    except requests.exceptions.HTTPError as http_err:
        error_details = traceback.format_exc()
        if http_err.response.status_code == 401: # Unauthorized
            print(f"!!! AUTH ERROR [fetch_strava_activities]: Strava token invalid or expired. {http_err}\n{error_details}")
            flash("Sua conexão com o Strava expirou ou é inválida. Por favor, reconecte.", "warning")
            # Opcional: tentar desconectar o token antigo do DB aqui
        else:
            print(f"!!! HTTP ERROR [fetch_strava_activities]: {http_err}\n{error_details}")
            flash(f"Erro ao buscar atividades do Strava (HTTP {http_err.response.status_code}).", "error")
    except requests.exceptions.RequestException as req_err: # Outros erros de request
        error_details = traceback.format_exc()
        print(f"!!! NETWORK ERROR [fetch_strava_activities]: {req_err}\n{error_details}")
        flash("Erro de comunicação ao buscar atividades do Strava.", "error")
    except (psycopg2.Error, Exception) as db_err: # Erro no DB ou outro erro genérico
        error_details = traceback.format_exc()
        print(f"!!! DB/GENERAL ERROR [fetch_strava_activities] processing activities: {db_err}\n{error_details}")
        if conn: conn.rollback()
        flash("Erro ao salvar as atividades do Strava no banco de dados.", "error")
    finally:
        if conn:
            print("DEBUG: [fetch_strava_activities] Closing DB connection.")
            conn.close()

    return redirect(url_for("conectar_apps_page"))

# --- Rota de Conectar Apps (placeholder) --- 
@app.route("/conectar")
@login_required
def conectar_apps_page():
    print("DEBUG: [conectar_apps_page] Entered route.")
    strava_is_connected = bool(g.strava_token_data)
    last_fetch_time = None # Placeholder para quando foi a última busca

    if strava_is_connected:
        # Poderia buscar a data da última atividade importada ou um log de sincronização
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT MAX(created_at) as last_sync FROM strava_activities WHERE user_id = %s", (g.user['id'],))
            result = cur.fetchone()
            if result and result['last_sync']:
                last_fetch_time = result['last_sync'].strftime("%d/%m/%Y %H:%M:%S")
            cur.close()
        except Exception as e:
            print(f"!!! DB ERROR [conectar_apps_page] fetching last_sync: {e}")
        finally:
            if conn: conn.close()

    try:
        print("DEBUG: [conectar_apps_page] Rendering conectar-apps.html")
        return render_template("conectar-apps.html", 
                               strava_connected=strava_is_connected,
                               last_strava_fetch=last_fetch_time)
    except Exception as render_error:
        print(f"!!! Render ERROR [conectar_apps_page] rendering conectar-apps.html: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar a página de conexão de aplicativos.", 500

# --- Rota de Detalhes do Item do Mural (Placeholder) --- 
@app.route("/mural/item/<int:item_id>")
@login_required
def item_detail(item_id):
    # Por enquanto, apenas uma placeholder
    # No futuro, buscaria o item do DB e renderizaria uma página de detalhes
    print(f"DEBUG: [item_detail] Acessada página de detalhes para o item ID: {item_id}")
    # Você pode criar um template simples item_detail.html ou apenas retornar uma string
    # return render_template("item_detail.html", item_id=item_id) 
    return f"Página de detalhes para o item {item_id}. Em construção."

# --- Execução da Aplicação (para desenvolvimento local) --- 
if __name__ == "__main__":
    # Define a porta a partir da variável de ambiente PORT ou usa 5000 como padrão
    port = int(os.environ.get("PORT", 5000))
    # Roda a aplicação em 0.0.0.0 para ser acessível externamente (e.g. em contêineres)
    # debug=True é útil para desenvolvimento, mas deve ser False em produção
    app.run(host="0.0.0.0", port=port, debug=True)

