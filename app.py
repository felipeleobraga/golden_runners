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
from urllib.parse import urlparse, urlencode, parse_qs # urlencode e parse_qs adicionados
from flask import Flask, render_template, session, g, flash, redirect, url_for, request
from dotenv import load_dotenv
from functools import wraps
from requests_oauthlib import OAuth2Session # Adicionado para OAuth
# Importar exceções específicas do oauthlib para tratamento de erro mais robusto
from oauthlib.oauth2.rfc6749.errors import InsecureTransportError, MissingTokenError, OAuth2Error
from werkzeug.middleware.proxy_fix import ProxyFix # ADICIONADO PARA CORRIGIR HTTPS ATRÁS DE PROXY

# Importar o blueprint de autenticação
from auth import auth_bp

# Carregar variáveis de ambiente do arquivo .env (útil para desenvolvimento local)
load_dotenv()

# Criar a instância da aplicação Flask
app = Flask(__name__)

# Aplicar ProxyFix para que o app reconheça X-Forwarded-Proto (HTTPS)
# Isso é crucial quando rodando atrás de um proxy como o do Railway
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Configurar uma chave secreta (necessária para sessões, flash messages, etc.)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "a_more_secure_default_secret_key_if_not_set")

# Configurações do Strava (carregadas do .env)
STRAVA_CLIENT_ID = os.environ.get("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.environ.get("STRAVA_CLIENT_SECRET")
STRAVA_AUTHORIZATION_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE_URL = "https://www.strava.com/api/v3"
STRAVA_REDIRECT_URI = os.environ.get("STRAVA_REDIRECT_URI") 
STRAVA_SCOPES = ["activity:read"] # Mantido: Apenas activity:read

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

# Context processor para disponibilizar o ano atual em todos os templates
@app.context_processor
def inject_current_year():
    """Adiciona o ano atual como variável disponível em todos os templates."""
    return {'current_year': datetime.datetime.now().year}

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

@app.route("/teams/join/<int:team_id>", methods=("POST",))
@login_required
def join_team(team_id):
    print(f"DEBUG: [join_team] Entered route for team_id: {team_id}")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verificar se a equipe existe
        cur.execute("SELECT name FROM teams WHERE id = %s", (team_id,))
        team = cur.fetchone()
        if not team:
            print(f"WARN: [join_team] Team with ID {team_id} not found.")
            flash("Equipe não encontrada.", "error")
            return redirect(url_for("list_teams_page"))
        
        # Atualizar o team_id do usuário
        user_id = g.user.get("id")
        cur.execute("UPDATE users SET team_id = %s WHERE id = %s", (team_id, user_id))
        conn.commit()
        print(f"DEBUG: [join_team] User {user_id} joined team {team_id}.")
        
        flash(f"Você entrou na equipe '{team[0]}'!", "success")
        return redirect(url_for("list_teams_page"))
        
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [join_team] joining team: {db_error}\n{error_details}")
        flash("Erro ao entrar na equipe.", "error")
        if conn: conn.rollback()
        return redirect(url_for("list_teams_page"))
    finally:
        if conn:
            print("DEBUG: [join_team] Closing DB connection.")
            conn.close()

@app.route("/teams/leave", methods=("POST",))
@login_required
def leave_team():
    print("DEBUG: [leave_team] Entered route")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Atualizar o team_id do usuário para NULL
        user_id = g.user.get("id")
        cur.execute("UPDATE users SET team_id = NULL WHERE id = %s", (user_id,))
        conn.commit()
        print(f"DEBUG: [leave_team] User {user_id} left their team.")
        
        flash("Você saiu da equipe.", "success")
        return redirect(url_for("list_teams_page"))
        
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [leave_team] leaving team: {db_error}\n{error_details}")
        flash("Erro ao sair da equipe.", "error")
        if conn: conn.rollback()
        return redirect(url_for("list_teams_page"))
    finally:
        if conn:
            print("DEBUG: [leave_team] Closing DB connection.")
            conn.close()

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
        return "Erro ao carregar a página de conexão de apps.", 500

@app.route("/strava/login")
@login_required
def strava_login():
    print("DEBUG: [strava_login] Initiating Strava OAuth flow.")
    try:
        # Criar sessão OAuth2 para o Strava
        strava_oauth = OAuth2Session(
            client_id=STRAVA_CLIENT_ID,
            redirect_uri=STRAVA_REDIRECT_URI,
            scope=STRAVA_SCOPES
        )
        
        # Gerar URL de autorização
        authorization_url, state = strava_oauth.authorization_url(STRAVA_AUTHORIZATION_URL)
        
        # Armazenar o state na sessão para validação posterior
        session["oauth_state"] = state
        
        print(f"DEBUG: [strava_login] Redirecting to Strava: {authorization_url}")
        return redirect(authorization_url)
    except Exception as oauth_error:
        error_details = traceback.format_exc()
        print(f"!!! STRAVA OAUTH ERROR [strava_login]: {oauth_error}\n{error_details}")
        flash("Erro ao iniciar o processo de autorização com o Strava.", "error")
        return redirect(url_for("conectar_apps_page"))

@app.route("/strava/callback")
@login_required
def strava_callback():
    print("DEBUG: [strava_callback] Received callback from Strava.")
    try:
        # Criar sessão OAuth2 para o Strava
        strava_oauth = OAuth2Session(
            client_id=STRAVA_CLIENT_ID,
            redirect_uri=STRAVA_REDIRECT_URI,
            state=session.get("oauth_state")
        )
        
        # Obter o token de acesso
        print("DEBUG: [strava_callback] Attempting to fetch token from Strava.")
        token_response = strava_oauth.fetch_token(
            token_url=STRAVA_TOKEN_URL,
            client_secret=STRAVA_CLIENT_SECRET,
            authorization_response=request.url,
            include_client_id=True
        )
        
        # Armazenar o token no banco de dados
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Verificar se já existe um token para este usuário
            user_id = g.user.get("id")
            cur.execute("SELECT id FROM strava_tokens WHERE user_id = %s", (user_id,))
            existing_token = cur.fetchone()
            
            # Preparar dados do token
            access_token = token_response.get("access_token")
            refresh_token = token_response.get("refresh_token")
            expires_at = datetime.datetime.fromtimestamp(token_response.get("expires_at"), tz=datetime.timezone.utc)
            
            if existing_token:
                # Atualizar token existente
                cur.execute("""
                    UPDATE strava_tokens 
                    SET access_token = %s, refresh_token = %s, expires_at = %s, updated_at = NOW() 
                    WHERE user_id = %s
                """, (access_token, refresh_token, expires_at, user_id))
                print(f"DEBUG: [strava_callback] Updated existing Strava token for user {user_id}.")
            else:
                # Inserir novo token
                cur.execute("""
                    INSERT INTO strava_tokens (user_id, access_token, refresh_token, expires_at, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, NOW(), NOW())
                """, (user_id, access_token, refresh_token, expires_at))
                print(f"DEBUG: [strava_callback] Inserted new Strava token for user {user_id}.")
            
            conn.commit()
            cur.close()
            
            flash("Conta do Strava conectada com sucesso!", "success")
            return redirect(url_for("conectar_apps_page"))
            
        except (Exception, psycopg2.DatabaseError) as db_error:
            error_details = traceback.format_exc()
            print(f"!!! DB ERROR [strava_callback] storing token: {db_error}\n{error_details}")
            flash("Erro ao armazenar token do Strava no banco de dados.", "error")
            if conn: conn.rollback()
            return redirect(url_for("conectar_apps_page"))
        finally:
            if conn:
                print("DEBUG: [strava_callback] Closing DB connection.")
                conn.close()
                
    except InsecureTransportError as ite:
        print(f"!!! STRAVA INSECURE TRANSPORT ERROR [strava_callback]: {ite}")
        flash("Erro ao obter o token do Strava: conexão insegura. O OAuth2 requer HTTPS.", "error")
        return redirect(url_for("conectar_apps_page"))
    except MissingTokenError as mte:
        print(f"!!! STRAVA MISSING TOKEN ERROR [strava_callback]: {mte}")
        flash("Erro ao obter o token do Strava: (missing_token) Missing access token parameter.. Verifique as configurações do aplicativo Strava e tente novamente.", "error")
        return redirect(url_for("conectar_apps_page"))
    except OAuth2Error as oauth_error:
        print(f"!!! STRAVA OAUTH ERROR [strava_callback]: {oauth_error}")
        flash(f"Erro ao obter o token do Strava: {str(oauth_error)}. Verifique as configurações do aplicativo Strava e tente novamente.", "error")
        return redirect(url_for("conectar_apps_page"))
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"!!! STRAVA CALLBACK ERROR [strava_callback]: {e}\n{error_details}")
        flash("Erro ao processar o retorno do Strava.", "error")
        return redirect(url_for("conectar_apps_page"))

@app.route("/strava/disconnect", methods=("POST",))
@login_required
def strava_disconnect():
    print("DEBUG: [strava_disconnect] Entered route")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Remover o token do Strava para este usuário
        user_id = g.user.get("id")
        cur.execute("DELETE FROM strava_tokens WHERE user_id = %s", (user_id,))
        conn.commit()
        print(f"DEBUG: [strava_disconnect] Removed Strava token for user {user_id}.")
        
        flash("Conta do Strava desconectada com sucesso!", "success")
        return redirect(url_for("conectar_apps_page"))
        
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [strava_disconnect] removing token: {db_error}\n{error_details}")
        flash("Erro ao desconectar conta do Strava.", "error")
        if conn: conn.rollback()
        return redirect(url_for("conectar_apps_page"))
    finally:
        if conn:
            print("DEBUG: [strava_disconnect] Closing DB connection.")
            conn.close()

@app.route("/mural")
def mural_page():
    print("DEBUG: [mural_page] Entered route")
    conn = None
    items = []
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Buscar todos os itens de doação
        print("DEBUG: [mural_page] Fetching donation items from DB")
        cur.execute("""
            SELECT di.id, di.title, di.description, di.category, di.location, 
                   di.status, di.image_url, di.created_at, di.user_id,
                   u.username as owner_username
            FROM donation_items di
            LEFT JOIN users u ON di.user_id = u.id
            ORDER BY di.created_at DESC
        """)
        items = cur.fetchall()
        print(f"DEBUG: [mural_page] Fetched {len(items)} items from DB")
        cur.close()
        print("DEBUG: [mural_page] Closing DB connection.")
        conn.close()
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [mural_page] fetching items: {db_error}\n{error_details}")
        flash("Erro ao carregar os itens do mural.", "error")
        items = []
        if conn: conn.close()
    
    try:
        print("DEBUG: [mural_page] Rendering mural.html")
        return render_template("mural.html", items=items)
    except Exception as render_error:
        print(f"!!! Render ERROR [mural_page] rendering mural.html: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar a página do mural.", 500

@app.route("/mural/item/<int:item_id>")
def item_detail(item_id):
    print(f"DEBUG: [item_detail] Acessada página de detalhes para o item ID: {item_id}")
    conn = None
    item = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Buscar detalhes do item específico
        cur.execute("""
            SELECT di.id, di.title, di.description, di.category, di.location, 
                   di.status, di.image_url, di.created_at, di.user_id,
                   u.username as owner_username
            FROM donation_items di
            LEFT JOIN users u ON di.user_id = u.id
            WHERE di.id = %s
        """, (item_id,))
        item = cur.fetchone()
        cur.close()
        conn.close()
        
        if not item:
            print(f"WARN: [item_detail] Item ID {item_id} not found.")
            flash("Item não encontrado.", "warning")
            return redirect(url_for("mural_page"))
            
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR [item_detail] fetching item: {db_error}\n{error_details}")
        flash("Erro ao carregar os detalhes do item.", "error")
        if conn: conn.close()
        return redirect(url_for("mural_page"))
    
    try:
        return render_template("item_detail.html", item=item)
    except Exception as render_error:
        print(f"!!! Render ERROR [item_detail] rendering item_detail.html: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar a página de detalhes do item.", 500

@app.route("/mural/add", methods=("GET", "POST"))
@login_required
def add_donation_item_page():
    print(f"DEBUG: [add_donation_item_page] Entered route, method: {request.method}")
    form_data = {}
    
    if request.method == "POST":
        print("DEBUG: [add_donation_item_page] Processing POST request")
        conn = None
        try:
            # Obter dados do formulário
            title = request.form.get("title")
            description = request.form.get("description")
            category = request.form.get("category")
            location = request.form.get("location")
            image_url = request.form.get("image_url")
            
            # Validação básica
            if not title:
                print("WARN: [add_donation_item_page] Validation failed (title missing).")
                flash("O título do item é obrigatório.", "warning")
                form_data = request.form
                return render_template("add_item.html", form_data=form_data)
            
            # Inserir no banco de dados
            conn = get_db_connection()
            cur = conn.cursor()
            
            sql = """
                INSERT INTO donation_items 
                (title, description, category, location, image_url, status, user_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            """
            
            user_id = g.user.get("id")
            status = "available"  # Status padrão para novos itens
            
            print("DEBUG: [add_donation_item_page] Executing INSERT query for new item")
            cur.execute(sql, (title, description, category, location, image_url, status, user_id))
            conn.commit()
            print("DEBUG: [add_donation_item_page] New item inserted and committed.")
            cur.close()
            
            flash("Item adicionado com sucesso ao mural de doações!", "success")
            return redirect(url_for("mural_page"))
            
        except (Exception, psycopg2.DatabaseError) as db_error:
            error_details = traceback.format_exc()
            print(f"!!! DB ERROR [add_donation_item_page] adding item: {db_error}\n{error_details}")
            flash("Erro ao adicionar o item ao banco de dados.", "error")
            if conn: conn.rollback()
            form_data = request.form
        finally:
            if conn:
                print("DEBUG: [add_donation_item_page] Closing DB connection.")
                conn.close()
    
    try:
        print("DEBUG: [add_donation_item_page] Rendering add_item.html")
        return render_template("add_item.html", form_data=form_data)
    except Exception as render_error:
        print(f"!!! Render ERROR [add_donation_item_page] rendering add_item.html: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar a página de adição de item.", 500

# Rota para erro 404 (página não encontrada)
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

# Rota para erro 500 (erro interno do servidor)
@app.errorhandler(500)
def internal_server_error(e):
    return render_template("500.html"), 500

# Iniciar a aplicação se este arquivo for executado diretamente
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
