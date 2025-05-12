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
STRAVA_SCOPES = ["activity:read"] # MODIFICADO: Apenas activity:read

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
        print("DEBUG: [get_db_connection] Connecting to DB...") 
        conn = psycopg2.connect(db_url)
        print("DEBUG: [get_db_connection] Connection successful.") 
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
        g.user = {"id": user_id, "username": session.get("username")}
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            cur.execute("SELECT id, username, points, created_at, team_id FROM users WHERE id = %s", (user_id,))
            user_data_from_db = cur.fetchone()
            if user_data_from_db:
                g.user.update(user_data_from_db)
            else:
                print(f"WARN: [load_logged_in_user] No user data found in DB for user_id: {user_id}")
            
            cur.execute("SELECT *, created_at, updated_at FROM strava_tokens WHERE user_id = %s", (user_id,))
            token_data = cur.fetchone()
            cur.close()
            
            if token_data:
                expires_at = token_data["expires_at"]
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                if expires_at > now_utc + datetime.timedelta(seconds=60):
                    g.strava_token_data = token_data
                else:
                    print(f"WARN: [load_logged_in_user] Strava token for user {user_id} expired. Needs refresh.")
                    
        except Exception as db_error:
            error_details = traceback.format_exc()
            print(f"!!! CRITICAL DB ERROR in load_logged_in_user: {db_error}\n{error_details}") 
            g.user = None
            g.strava_token_data = None
        finally:
            if conn:
                conn.close()

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
        "total_km": 0, 
        "total_donated": 0, 
        "last_activity": "N/A" 
    }
    
    strava_connected = bool(g.strava_token_data)
    strava_activities = []
    conn = None

    if strava_connected:
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            current_user_id = g.user.get("id")
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
        
        print("DEBUG: [ranking_page] Fetching users for individual ranking from DB")
        cur.execute("""
            SELECT username, points 
            FROM users
            ORDER BY points DESC, username ASC
            LIMIT 100 
        """)
        users_ranking = cur.fetchall()
        print(f"DEBUG: [ranking_page] Fetched {len(users_ranking)} users for individual ranking")

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
    except psycopg2.errors.UndefinedTable as ut_err: 
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [ranking_page]: TABLE 'teams' DOES NOT EXIST? {ut_err}\n{error_details}") 
        flash("Erro ao carregar ranking de equipes: estrutura do banco de dados incompleta.", "error")
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

@app.route("/teams")
@login_required
def list_teams_page():
    print("DEBUG: [list_teams_page] Entered route.") 
    conn = None
    teams = []
    try:
        print("DEBUG: [list_teams_page] Attempting to get DB connection.") 
        conn = get_db_connection()
        print("DEBUG: [list_teams_page] DB connection obtained.") 
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        print("DEBUG: [list_teams_page] Cursor created. Executing query for teams.") 
        cur.execute("SELECT id, name, description, created_at FROM teams ORDER BY name ASC")
        print("DEBUG: [list_teams_page] Query executed.") 
        teams = cur.fetchall()
        print(f"DEBUG: [list_teams_page] Fetched {len(teams)} teams.")
        cur.close()
        print("DEBUG: [list_teams_page] Cursor closed.") 
    except psycopg2.errors.UndefinedTable as ut_err: 
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [list_teams_page]: TABLE 'teams' DOES NOT EXIST. {ut_err}\n{error_details}") 
        flash("Erro crítico: A estrutura do banco de dados para equipes não foi encontrada. Contate o administrador.", "error")
        return redirect(url_for("dashboard")) 
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [list_teams_page] fetching teams: {db_error}\n{error_details}")
        flash("Erro ao carregar a lista de equipes.", "error")
        return redirect(url_for("dashboard"))
    finally:
        if conn:
            print("DEBUG: [list_teams_page] Closing DB connection.") 
            conn.close()

    try:
        print("DEBUG: [list_teams_page] Attempting to render teams.html") 
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
        except psycopg2.errors.UndefinedTable as ut_err: 
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
        cur.execute("SELECT id FROM teams WHERE id = %s", (team_id,))
        if not cur.fetchone():
            print(f"WARN: [join_team] Team {team_id} not found.")
            flash("Equipe não encontrada.", "error")
            return redirect(url_for("list_teams_page"))

        if g.user.get("team_id") is not None:
            print(f"WARN: [join_team] User {g.user['id']} already in team {g.user.get('team_id')}.")
            flash("Você já faz parte de uma equipe. Saia da equipe atual para entrar em uma nova.", "warning")
            return redirect(url_for("list_teams_page"))

        cur.execute("UPDATE users SET team_id = %s WHERE id = %s", (team_id, g.user['id']))
        conn.commit()
        cur.close()
        # Atualizar g.user para refletir a mudança imediatamente
        g.user['team_id'] = team_id 
        flash("Você entrou na equipe com sucesso!", "success")
        print(f"DEBUG: [join_team] User {g.user['id']} successfully joined team {team_id}")
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
    print(f"DEBUG: [leave_team] User {g.user['id']} attempting to leave team {g.user.get('team_id')}")
    if g.user.get("team_id") is None:
        print(f"WARN: [leave_team] User {g.user['id']} is not in any team.")
        flash("Você não faz parte de nenhuma equipe.", "info")
        return redirect(url_for("list_teams_page"))
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET team_id = NULL WHERE id = %s", (g.user['id'],))
        conn.commit()
        cur.close()
        # Atualizar g.user para refletir a mudança imediatamente
        g.user['team_id'] = None
        flash("Você saiu da equipe.", "success")
        print(f"DEBUG: [leave_team] User {g.user['id']} successfully left their team.")
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

@app.route("/mural")
@login_required
def mural_page():
    print("DEBUG: [mural_page] Entered route")
    conn = None
    donation_items = []
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        print("DEBUG: [mural_page] Fetching donation items from DB")
        # Corrigido: di.owner_user_id para di.user_id
        # Corrigido: u.name para u.username
        cur.execute("""
            SELECT di.id, di.title, di.description, di.category, di.image_filename, di.created_at, u.username AS owner_username
            FROM donation_items di
            JOIN users u ON di.user_id = u.id 
            ORDER BY di.created_at DESC
        """)
        donation_items = cur.fetchall()
        print(f"DEBUG: [mural_page] Fetched {len(donation_items)} items from DB")
        cur.close()
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
        return render_template("mural.html", items=donation_items)
    except Exception as render_error:
        print(f"!!! Render ERROR [mural_page] rendering mural.html: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar o mural.", 500

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
            # Simulação de upload de imagem, apenas salvando o nome do arquivo
            image_filename = request.form.get("image_filename", "default_item.png") 
            owner_user_id = g.user["id"]
            print(f"DEBUG: [add_donation_item_page] Form data: title='{title}', category='{category}', owner='{owner_user_id}'")

            if not title or not category:
                print("WARN: [add_donation_item_page] Validation failed (title or category missing).")
                flash("Título e categoria são obrigatórios.", "warning")
                form_data = request.form
                return render_template("add_item.html", form_data=form_data)

            conn = get_db_connection()
            cur = conn.cursor()
            # Corrigido: owner_user_id para user_id na query e nos parâmetros
            sql = "INSERT INTO donation_items (title, description, category, image_filename, user_id) VALUES (%s, %s, %s, %s, %s);"
            print("DEBUG: [add_donation_item_page] Executing INSERT query for new donation item")
            cur.execute(sql, (title, description, category, image_filename, owner_user_id))
            conn.commit()
            print("DEBUG: [add_donation_item_page] New item inserted and committed.")
            cur.close()
            flash("Item adicionado ao mural com sucesso!", "success")
            return redirect(url_for("mural_page"))

        except (Exception, psycopg2.DatabaseError) as db_error:
            error_details = traceback.format_exc()
            print(f"!!! DB ERROR [add_donation_item_page] adding item: {db_error}\n{error_details}")
            flash("Erro ao adicionar o item ao banco de dados.", "error")
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

@app.route("/mural/item/<int:item_id>")
@login_required
def item_detail(item_id):
    print(f"DEBUG: [item_detail] Acessada página de detalhes para o item ID: {item_id}")
    conn = None
    item = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT di.id, di.title, di.description, di.category, di.image_filename, 
                   di.created_at, di.user_id, u.username AS owner_username
            FROM donation_items di
            JOIN users u ON di.user_id = u.id
            WHERE di.id = %s
        """, (item_id,))
        item = cur.fetchone()
        cur.close()
        if not item:
            print(f"WARN: [item_detail] Item com ID {item_id} não encontrado.")
            flash("Item não encontrado.", "error")
            return redirect(url_for("mural_page"))
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [item_detail] fetching item {item_id}: {db_error}\n{error_details}")
        flash("Erro ao buscar detalhes do item.", "error")
        return redirect(url_for("mural_page"))
    finally:
        if conn:
            conn.close()
    
    try:
        return render_template("item_detail.html", item=item)
    except Exception as render_error:
        print(f"!!! Render ERROR [item_detail] rendering item_detail.html: {render_error}\n{traceback.format_exc()}")
        return f"Erro ao carregar detalhes do item {item_id}.", 500

@app.route("/conectar-apps")
@login_required
def conectar_apps_page():
    print("DEBUG: [conectar_apps_page] Entered route.")
    strava_connected = bool(g.strava_token_data)
    try:
        print("DEBUG: [conectar_apps_page] Rendering conectar-apps.html")
        return render_template("conectar-apps.html", strava_connected=strava_connected)
    except Exception as render_error:
        print(f"!!! Render ERROR [conectar_apps_page] rendering conectar-apps.html: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar a página de conexão de aplicativos.", 500

# --- Rotas de Autenticação Strava --- 

@app.route("/strava/login")
@login_required
def strava_login():
    print("DEBUG: [strava_login] Initiating Strava OAuth flow.")
    if not STRAVA_CLIENT_ID or not STRAVA_CLIENT_SECRET or not STRAVA_REDIRECT_URI:
        print("!!! CRITICAL ERROR: Strava client credentials or redirect URI not configured.")
        flash("A integração com o Strava não está configurada corretamente. Contate o administrador.", "error")
        return redirect(url_for("conectar_apps_page"))

    strava_oauth = OAuth2Session(STRAVA_CLIENT_ID, redirect_uri=STRAVA_REDIRECT_URI, scope=STRAVA_SCOPES)
    authorization_url, state = strava_oauth.authorization_url(STRAVA_AUTHORIZATION_URL)
    session["strava_oauth_state"] = state
    print(f"DEBUG: [strava_login] Redirecting to Strava: {authorization_url}")
    return redirect(authorization_url)

@app.route("/strava/callback")
@login_required
def strava_callback():
    print("DEBUG: [strava_callback] Received callback from Strava.")
    if "error" in request.args:
        error_reason = request.args.get("error", "unknown")
        print(f"!!! STRAVA AUTH ERROR: Strava returned an error: {error_reason}")
        flash(f"Erro na autorização do Strava: {error_reason}. Tente novamente.", "error")
        return redirect(url_for("conectar_apps_page"))

    if not STRAVA_CLIENT_ID or not STRAVA_CLIENT_SECRET:
        print("!!! CRITICAL ERROR: Strava client credentials not configured for token exchange.")
        flash("Configuração do Strava incompleta. Contate o administrador.", "error")
        return redirect(url_for("conectar_apps_page"))

    strava_oauth = OAuth2Session(
        STRAVA_CLIENT_ID, 
        state=session.get("strava_oauth_state"), 
        scope=STRAVA_SCOPES, 
        redirect_uri=STRAVA_REDIRECT_URI
    )
    
    try:
        print("DEBUG: [strava_callback] Attempting to fetch token from Strava.")
        token_response = strava_oauth.fetch_token(
            STRAVA_TOKEN_URL,
            client_secret=STRAVA_CLIENT_SECRET,
            authorization_response=request.url
        )
        print("DEBUG: [strava_callback] Token fetched successfully from Strava.")

        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")
        expires_at_timestamp = token_response.get("expires_at")
        strava_athlete_id = token_response.get("athlete", {}).get("id")
        
        if not access_token or not expires_at_timestamp or not strava_athlete_id:
            print("!!! STRAVA TOKEN ERROR: Missing essential data in token response from Strava.")
            flash("Resposta do Strava incompleta ao obter o token. Tente novamente.", "error")
            return redirect(url_for("conectar_apps_page"))

        expires_at_datetime = datetime.datetime.fromtimestamp(expires_at_timestamp, tz=datetime.timezone.utc)
        current_user_id = g.user["id"]

        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            print(f"DEBUG: [strava_callback] Storing/Updating Strava token for user {current_user_id} in DB.")
            # Upsert (insert or update) token data
            cur.execute("""
                INSERT INTO strava_tokens (user_id, access_token, refresh_token, expires_at, strava_athlete_id, scopes)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    access_token = EXCLUDED.access_token,
                    refresh_token = EXCLUDED.refresh_token,
                    expires_at = EXCLUDED.expires_at,
                    strava_athlete_id = EXCLUDED.strava_athlete_id,
                    scopes = EXCLUDED.scopes,
                    updated_at = NOW(); 
            """, (current_user_id, access_token, refresh_token, expires_at_datetime, strava_athlete_id, json.dumps(STRAVA_SCOPES)))
            conn.commit()
            cur.close()
            print("DEBUG: [strava_callback] Strava token stored/updated in DB successfully.")
            flash("Strava conectado com sucesso!", "success")
            # Atualizar g.strava_token_data para refletir o novo token imediatamente
            g.strava_token_data = {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at_datetime,
                "strava_athlete_id": strava_athlete_id,
                "scopes": STRAVA_SCOPES
            }
            # Chamar a função para buscar atividades após conectar
            fetch_strava_activities(current_user_id, access_token, strava_athlete_id)

        except (Exception, psycopg2.DatabaseError) as db_error:
            error_details = traceback.format_exc()
            print(f"!!! DB ERROR [strava_callback] storing token: {db_error}\n{error_details}")
            flash("Erro ao salvar as informações de conexão do Strava.", "error")
            if conn: conn.rollback()
        finally:
            if conn:
                conn.close()

    except Exception as e:
        error_details = traceback.format_exc()
        print(f"!!! STRAVA OAUTH ERROR [strava_callback] during token fetch or processing: {e}\n{error_details}")
        flash(f"Ocorreu um erro durante a autenticação com o Strava: {e}. Tente novamente.", "error")

    return redirect(url_for("conectar_apps_page"))

@app.route("/strava/disconnect", methods=["POST"])
@login_required
def strava_disconnect():
    print(f"DEBUG: [strava_disconnect] User {g.user['id']} attempting to disconnect Strava.")
    current_user_id = g.user["id"]
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Revogar o token no Strava (opcional, mas boa prática)
        if g.strava_token_data and g.strava_token_data.get("access_token"):
            try:
                print(f"DEBUG: [strava_disconnect] Attempting to revoke Strava token for user {current_user_id}")
                revoke_url = f"{STRAVA_API_BASE_URL}/oauth/deauthorize"
                headers = {"Authorization": f"Bearer {g.strava_token_data['access_token']}"}
                response = requests.post(revoke_url, headers=headers)
                if response.status_code == 200:
                    print(f"DEBUG: [strava_disconnect] Strava token successfully revoked for user {current_user_id}.")
                else:
                    print(f"WARN: [strava_disconnect] Failed to revoke Strava token. Status: {response.status_code}, Response: {response.text}")
            except Exception as revoke_err:
                print(f"WARN: [strava_disconnect] Error during Strava token revocation: {revoke_err}")

        print(f"DEBUG: [strava_disconnect] Deleting Strava token and activities from DB for user {current_user_id}.")
        cur.execute("DELETE FROM strava_tokens WHERE user_id = %s", (current_user_id,))
        cur.execute("DELETE FROM strava_activities WHERE user_id = %s", (current_user_id,))
        conn.commit()
        cur.close()
        g.strava_token_data = None # Limpar da sessão global
        flash("Strava desconectado com sucesso.", "success")
        print(f"DEBUG: [strava_disconnect] Strava disconnected successfully for user {current_user_id}.")
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [strava_disconnect]: {db_error}\n{error_details}")
        flash("Erro ao desconectar o Strava.", "error")
        if conn: conn.rollback()
    finally:
        if conn:
            conn.close()
    return redirect(url_for("conectar_apps_page"))

def fetch_strava_activities(user_id, access_token, strava_athlete_id):
    print(f"DEBUG: [fetch_strava_activities] Fetching activities for user {user_id}, athlete {strava_athlete_id}")
    headers = {"Authorization": f"Bearer {access_token}"}
    # Buscar atividades após a última atividade já registrada ou nos últimos 90 dias
    conn_check = None
    last_fetch_timestamp = None
    try:
        conn_check = get_db_connection()
        cur_check = conn_check.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur_check.execute("SELECT MAX(start_date_epoch) as last_epoch FROM strava_activities WHERE user_id = %s", (user_id,))
        last_activity_data = cur_check.fetchone()
        if last_activity_data and last_activity_data['last_epoch']:
            last_fetch_timestamp = int(last_activity_data['last_epoch']) + 1 # Buscar após o último evento
            print(f"DEBUG: [fetch_strava_activities] Last fetch timestamp for user {user_id}: {last_fetch_timestamp}")
        else:
            # Se não houver atividades, buscar dos últimos 90 dias
            last_fetch_timestamp = int((datetime.datetime.now() - datetime.timedelta(days=90)).timestamp())
            print(f"DEBUG: [fetch_strava_activities] No previous activities, fetching last 90 days for user {user_id}. Timestamp: {last_fetch_timestamp}")
        cur_check.close()
    except Exception as e_check:
        print(f"WARN: [fetch_strava_activities] Error getting last fetch time for user {user_id}: {e_check}. Defaulting to 90 days.")
        last_fetch_timestamp = int((datetime.datetime.now() - datetime.timedelta(days=90)).timestamp())
    finally:
        if conn_check:
            conn_check.close()

    params = {"after": last_fetch_timestamp, "per_page": 100} # Limite de 100 por página
    activities_url = f"{STRAVA_API_BASE_URL}/athlete/activities"
    
    all_activities = []
    page = 1
    while True:
        params["page"] = page
        try:
            print(f"DEBUG: [fetch_strava_activities] Requesting page {page} of activities from Strava for user {user_id}.")
            response = requests.get(activities_url, headers=headers, params=params)
            response.raise_for_status() # Lança exceção para erros HTTP 4xx/5xx
            activities_page = response.json()
            if not activities_page: # Se a página estiver vazia, não há mais atividades
                print(f"DEBUG: [fetch_strava_activities] No more activities found on page {page} for user {user_id}.")
                break
            all_activities.extend(activities_page)
            print(f"DEBUG: [fetch_strava_activities] Fetched {len(activities_page)} activities on page {page}. Total so far: {len(all_activities)}.")
            if len(activities_page) < params["per_page"]:
                 print(f"DEBUG: [fetch_strava_activities] Last page of activities reached for user {user_id}.")
                 break # Última página
            page += 1
            if page > 5: # Limite de segurança para evitar loops infinitos em cenários inesperados
                print(f"WARN: [fetch_strava_activities] Reached page limit (5) for user {user_id}. Stopping fetch.")
                break
        except requests.exceptions.RequestException as e_req:
            print(f"!!! STRAVA API ERROR [fetch_strava_activities] fetching activities for user {user_id}: {e_req}")
            flash("Erro ao buscar atividades do Strava. Tente novamente mais tarde.", "error")
            return # Interrompe a busca em caso de erro de API
        except json.JSONDecodeError as e_json:
            print(f"!!! JSON ERROR [fetch_strava_activities] decoding Strava response for user {user_id}: {e_json}")
            flash("Erro ao processar a resposta do Strava.", "error")
            return

    if not all_activities:
        print(f"INFO: [fetch_strava_activities] No new activities found for user {user_id} since last fetch.")
        return

    conn_insert = None
    try:
        conn_insert = get_db_connection()
        cur_insert = conn_insert.cursor()
        print(f"DEBUG: [fetch_strava_activities] Preparing to insert/update {len(all_activities)} activities into DB for user {user_id}.")
        activities_to_insert = []
        points_to_add = 0
        
        # Tipos de atividade que contam pontos e seus multiplicadores (distância em metros)
        # Ajuste os multiplicadores conforme necessário. Ex: 1 ponto por km de corrida.
        # 1 km = 1000 metros. Se 1 ponto por km, então 1/1000 pontos por metro.
        activity_point_multipliers = {
            "Run": 0.001, "Walk": 0.001, "VirtualRun": 0.001, "TrailRun": 0.001, "Hike": 0.0005,
            "Wheelchair": 0.001, "Snowshoe": 0.0005,
            "Swim": 0.004, # Natação geralmente vale mais por distância
            "VirtualRide": 0.0002, "Ride": 0.0002, "EBikeRide": 0.0001, "GravelRide": 0.0002,
            "Handcycle": 0.0002, "MountainBikeRide": 0.0002,
            "RollerSki": 0.0005, "NordicSki": 0.0005, "AlpineSki": 0.0001, "BackcountrySki": 0.0003,
            "IceSkate": 0.0003, "InlineSkate": 0.0003,
            "Rowing": 0.0008, "VirtualRow": 0.0008,
            "Kayaking": 0.0005, "Canoeing": 0.0005, "StandUpPaddling": 0.0004,
            # Atividades baseadas em tempo/esforço podem ter pontos fixos ou por duração
            # Aqui, vamos focar em distância por enquanto, mas poderia ser expandido
            "WeightTraining": 5, # Pontos fixos por sessão
            "Workout": 5,
            "Yoga": 3,
            "Crossfit": 10,
            "StairStepper": 0.002 # Exemplo, pode ser por tempo ou "andares"
        }

        for activity in all_activities:
            activity_id = activity["id"]
            activity_type = activity["type"]
            distance_meters = activity.get("distance", 0)
            moving_time_seconds = activity.get("moving_time", 0)
            start_date_str = activity["start_date"]
            start_date_dt = datetime.datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
            start_date_epoch = int(start_date_dt.timestamp())

            points_for_activity = 0
            if activity_type in activity_point_multipliers:
                if distance_meters > 0:
                    points_for_activity = distance_meters * activity_point_multipliers[activity_type]
                elif isinstance(activity_point_multipliers[activity_type], (int, float)) and activity_point_multipliers[activity_type] > 0.00001 : # Pontos fixos
                    points_for_activity = activity_point_multipliers[activity_type]
            
            points_for_activity = math.ceil(points_for_activity) # Arredonda para cima
            points_to_add += points_for_activity

            activities_to_insert.append((
                activity_id, user_id, strava_athlete_id, activity.get("name", "Atividade Strava"),
                distance_meters, moving_time_seconds, activity.get("elapsed_time", 0),
                activity_type, start_date_dt, activity.get("timezone"),
                start_date_epoch, points_for_activity 
            ))
        
        if activities_to_insert:
            # Usar ON CONFLICT para evitar duplicatas e atualizar se necessário (ex: pontos recalculados)
            sql_insert_activity = """
                INSERT INTO strava_activities (
                    id, user_id, strava_athlete_id, name, distance, moving_time, elapsed_time, 
                    type, start_date, timezone, start_date_epoch, points_awarded
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    distance = EXCLUDED.distance,
                    moving_time = EXCLUDED.moving_time,
                    elapsed_time = EXCLUDED.elapsed_time,
                    type = EXCLUDED.type,
                    start_date = EXCLUDED.start_date,
                    timezone = EXCLUDED.timezone,
                    start_date_epoch = EXCLUDED.start_date_epoch,
                    points_awarded = EXCLUDED.points_awarded; 
            """
            cur_insert.executemany(sql_insert_activity, activities_to_insert)
            print(f"DEBUG: [fetch_strava_activities] Inserted/Updated {len(activities_to_insert)} activities in DB for user {user_id}.")

            if points_to_add > 0:
                cur_insert.execute("UPDATE users SET points = points + %s WHERE id = %s", (points_to_add, user_id))
                print(f"DEBUG: [fetch_strava_activities] Added {points_to_add} points to user {user_id}.")
            
            conn_insert.commit()
            print(f"DEBUG: [fetch_strava_activities] DB commit successful for user {user_id}.")
        else:
            print(f"INFO: [fetch_strava_activities] No new activities qualified for DB insertion for user {user_id}.")

        cur_insert.close()
        flash(f"{len(all_activities)} atividades do Strava foram sincronizadas!", "info")

    except (Exception, psycopg2.DatabaseError) as db_error_insert:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [fetch_strava_activities] inserting activities for user {user_id}: {db_error_insert}\n{error_details}")
        flash("Erro ao salvar as atividades do Strava no banco de dados.", "error")
        if conn_insert: conn_insert.rollback()
    finally:
        if conn_insert:
            conn_insert.close()

# --- Ponto de Entrada Principal (para desenvolvimento local) ---
if __name__ == "__main__":
    # Certifique-se de que as variáveis de ambiente são carregadas se não estiverem já definidas
    if not os.environ.get("DATABASE_URL") or \
       not os.environ.get("STRAVA_CLIENT_ID") or \
       not os.environ.get("STRAVA_CLIENT_SECRET") or \
       not os.environ.get("STRAVA_REDIRECT_URI"):
        print("WARN: Variáveis de ambiente não totalmente configuradas. Carregando do .env se existir.")
        load_dotenv()
        # Verificar novamente após carregar do .env
        if not os.environ.get("DATABASE_URL"):
            print("!!! FATAL: DATABASE_URL não definida. A aplicação não pode iniciar.")
            sys.exit(1)
        if not os.environ.get("STRAVA_CLIENT_ID") or \
           not os.environ.get("STRAVA_CLIENT_SECRET") or \
           not os.environ.get("STRAVA_REDIRECT_URI"):
            print("WARN: Configurações do Strava não totalmente definidas. A integração com o Strava pode falhar.")

    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

