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
        conn = psycopg2.connect(db_url)
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
            
            # Busca dados completos do usuário, incluindo pontos, created_at e team_id
            cur.execute("SELECT id, username, points, created_at, team_id FROM users WHERE id = %s", (user_id,))
            user_data_from_db = cur.fetchone()
            if user_data_from_db:
                g.user.update(user_data_from_db)
            else:
                print(f"WARN: No user data found in DB for user_id: {user_id}")
            
            # Busca token do Strava
            cur.execute("SELECT *, created_at, updated_at FROM strava_tokens WHERE user_id = %s", (user_id,))
            token_data = cur.fetchone()
            cur.close()
            
            if token_data:
                expires_at = token_data["expires_at"]
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                if expires_at > now_utc + datetime.timedelta(seconds=60):
                    g.strava_token_data = token_data
                else:
                    print(f"WARN: Strava token for user {user_id} expired. Needs refresh.")
                    # TODO: Implementar refresh token
                    
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
            cur.execute("""
                SELECT id, name, distance, moving_time, type, start_date
                FROM strava_activities
                WHERE user_id = %s
                  AND type IN ("Run", "Walk") 
                ORDER BY start_date DESC
                LIMIT 5
            """, (current_user_id,))
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
    print("DEBUG: Accessing ranking_page route")
    conn = None
    users_ranking = []
    teams_ranking = []
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Ranking Individual
        print("DEBUG: Fetching users for individual ranking from DB")
        cur.execute("""
            SELECT username, points 
            FROM users
            ORDER BY points DESC, username ASC
            LIMIT 100 
        """)
        users_ranking = cur.fetchall()
        print(f"DEBUG: Fetched {len(users_ranking)} users for individual ranking")

        # Ranking por Equipes
        print("DEBUG: Fetching teams for team ranking from DB")
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
        print(f"DEBUG: Fetched {len(teams_ranking)} teams for ranking")
        
        cur.close()
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR fetching rankings: {db_error}\n{error_details}")
        flash("Erro ao carregar os rankings.", "error")
    finally:
        if conn:
            print("DEBUG: Closing DB connection in ranking route.")
            conn.close()
    
    try:
        print("DEBUG: Rendering ranking.html with both rankings")
        return render_template("ranking.html", 
                               users_ranking=users_ranking, 
                               teams_ranking=teams_ranking)
    except Exception as render_error:
        print(f"!!! Render ERROR ranking: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar a página de ranking.", 500

# --- Rotas de Equipes --- 

@app.route("/teams")
@login_required
def list_teams_page():
    print("DEBUG: Accessing list_teams_page route")
    conn = None
    teams = []
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        print("DEBUG: Fetching teams from DB")
        cur.execute("SELECT id, name, description, created_at FROM teams ORDER BY name ASC")
        teams = cur.fetchall()
        print(f"DEBUG: Fetched {len(teams)} teams")
        cur.close()
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR fetching teams: {db_error}\n{error_details}")
        flash("Erro ao carregar a lista de equipes.", "error")
    finally:
        if conn:
            print("DEBUG: Closing DB connection in list_teams_page route.")
            conn.close()
    
    try:
        print("DEBUG: Rendering teams.html")
        return render_template("teams.html", teams=teams)
    except Exception as render_error:
        print(f"!!! Render ERROR teams: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar a página de equipes.", 500

@app.route("/teams/create", methods=("GET", "POST"))
@login_required
def create_team_page():
    print(f"DEBUG: Accessing create_team_page route, method: {request.method}")
    form_data = {}
    if request.method == "POST":
        print("DEBUG: Processing POST request for create_team")
        conn = None
        try:
            team_name = request.form.get("name")
            description = request.form.get("description")
            print(f"DEBUG: Form data received: name={team_name}, desc={description[:20]}...")

            if not team_name:
                print("WARN: Create team validation failed (name missing).")
                flash("O nome da equipe é obrigatório.", "warning")
                form_data = request.form
                return render_template("create_team.html", form_data=form_data)

            conn = get_db_connection()
            cur = conn.cursor()
            sql = "INSERT INTO teams (name, description) VALUES (%s, %s);"
            print("DEBUG: Executing INSERT query for new team")
            cur.execute(sql, (team_name, description))
            conn.commit()
            print("DEBUG: New team inserted and committed.")
            cur.close()
            flash(f"Equipe ", "success")
            return redirect(url_for("list_teams_page"))

        except psycopg2.errors.UniqueViolation:
            print(f"WARN: Team name ")
            flash("Já existe uma equipe com este nome. Escolha outro.", "warning")
            if conn: conn.rollback()
            form_data = request.form
        except (Exception, psycopg2.DatabaseError) as db_error:
            error_details = traceback.format_exc()
            print(f"!!! DB ERROR creating team: {db_error}\n{error_details}")
            flash("Erro ao criar a equipe no banco de dados.", "error")
            if conn: conn.rollback()
            form_data = request.form
        finally:
            if conn:
                print("DEBUG: Closing DB connection in create_team (POST).")
                conn.close()
    
    try:
        print("DEBUG: Rendering create_team.html for GET request or POST error")
        return render_template("create_team.html", form_data=form_data)
    except Exception as render_error:
        print(f"!!! Render ERROR create_team: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar o formulário de criação de equipe.", 500

@app.route("/teams/<int:team_id>/join", methods=["POST"])
@login_required
def join_team(team_id):
    print(f"DEBUG: Accessing join_team route for team_id: {team_id}")
    user_id = g.user.get("id")
    current_team_id = g.user.get("team_id")
    conn = None

    if current_team_id:
        print(f"WARN: User {user_id} attempted to join team {team_id} but already belongs to team {current_team_id}.")
        flash("Você já pertence a uma equipe. Saia da equipe atual antes de entrar em outra.", "warning")
        return redirect(url_for("list_teams_page"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        print(f"DEBUG: Updating user {user_id} to join team {team_id}")
        cur.execute("UPDATE users SET team_id = %s WHERE id = %s", (team_id, user_id))
        conn.commit()
        cur.close()
        g.user["team_id"] = team_id 
        print(f"DEBUG: User {user_id} successfully joined team {team_id}.")
        flash("Você entrou na equipe!", "success")
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR joining team: {db_error}\n{error_details}")
        flash("Erro ao tentar entrar na equipe.", "error")
        if conn: conn.rollback()
    finally:
        if conn:
            print("DEBUG: Closing DB connection in join_team.")
            conn.close()
            
    return redirect(url_for("list_teams_page"))

@app.route("/teams/leave", methods=["POST"])
@login_required
def leave_team():
    print(f"DEBUG: Accessing leave_team route")
    user_id = g.user.get("id")
    current_team_id = g.user.get("team_id")
    conn = None

    if not current_team_id:
        print(f"WARN: User {user_id} attempted to leave team but does not belong to any.")
        flash("Você não pertence a nenhuma equipe.", "warning")
        return redirect(url_for("list_teams_page"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        print(f"DEBUG: Updating user {user_id} to leave team {current_team_id}")
        cur.execute("UPDATE users SET team_id = NULL WHERE id = %s", (user_id,))
        conn.commit()
        cur.close()
        g.user["team_id"] = None
        print(f"DEBUG: User {user_id} successfully left team {current_team_id}.")
        flash("Você saiu da equipe.", "success")
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR leaving team: {db_error}\n{error_details}")
        flash("Erro ao tentar sair da equipe.", "error")
        if conn: conn.rollback()
    finally:
        if conn:
            print("DEBUG: Closing DB connection in leave_team.")
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
        print(f"!!! DB ERROR fetching mural items: {db_error}\n{error_details}")
        flash("Erro ao carregar os itens do mural.", "error")
    finally:
        if conn:
            conn.close()
    
    try:
        return render_template("mural.html", items=items)
    except Exception as render_error:
        print(f"!!! Render ERROR mural: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar a página do mural.", 500

@app.route("/mural/adicionar", methods=("GET", "POST"))
@login_required
def add_item():
    form_data = {}
    if request.method == "POST":
        conn = None
        try:
            category = request.form.get("category")
            description = request.form.get("description")
            location = request.form.get("location")
            image_url = request.form.get("image_url")
            color = request.form.get("color")
            size = request.form.get("size")
            brand = request.form.get("brand")
            whatsapp_link = request.form.get("whatsapp_link")
            user_id = g.user["id"]

            if not category or not description or not location:
                print("WARN: Add item validation failed.")
                flash("Categoria, descrição e localização são obrigatórios.", "warning")
                form_data = request.form
                return render_template("add_item.html", form_data=form_data)

            conn = get_db_connection()
            cur = conn.cursor()
            sql = """INSERT INTO donation_items 
                     (user_id, category, description, location, image_url, color, size, brand, whatsapp_link)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);"""
            cur.execute(sql, (user_id, category, description, location, image_url, color, size, brand, whatsapp_link))
            conn.commit()
            cur.close()
            flash("Item adicionado com sucesso!", "success")
            return redirect(url_for("mural_page"))

        except (Exception, psycopg2.DatabaseError) as db_error:
            error_details = traceback.format_exc()
            print(f"!!! DB ERROR adding item: {db_error}\n{error_details}")
            flash("Erro ao adicionar o item no banco de dados.", "error")
            if conn: conn.rollback()
            form_data = request.form
        finally:
            if conn:
                conn.close()
    
    try:
        return render_template("add_item.html", form_data=form_data)
    except Exception as render_error:
        print(f"!!! Render ERROR add_item: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar o formulário de adição.", 500

@app.route("/item/<int:item_id>")
def item_detail(item_id):
    conn = None
    item = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT di.*, u.username AS donor_username 
            FROM donation_items di
            JOIN users u ON di.user_id = u.id
            WHERE di.id = %s
        """, (item_id,))
        item = cur.fetchone()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR fetching item detail {item_id}: {db_error}\n{error_details}")
        flash("Erro ao buscar detalhes do item.", "error")
    finally:
        if conn:
            conn.close()

    if item is None:
        print(f"WARN: Item {item_id} not found.")
        flash("Item não encontrado.", "warning")
        return redirect(url_for("mural_page"))

    try:
        return render_template("item_detail.html", item=item)
    except Exception as render_error:
        print(f"!!! Render ERROR item_detail {item_id}: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar a página de detalhes do item.", 500

@app.route("/item/<int:item_id>/interesse", methods=["POST"])
@login_required
def express_interest(item_id):
    current_user_id = g.user.get("id")
    print(f"DEBUG: User {current_user_id} expressed interest in item {item_id}") 
    flash("Seu interesse foi registrado! O doador será notificado (funcionalidade futura).", "info")
    return redirect(url_for("item_detail", item_id=item_id))

# --- Rotas de Conexão Strava --- 

@app.route("/conectar")
@login_required
def conectar_page():
    strava_connected = bool(g.strava_token_data)
    connection_date = None
    if strava_connected:
        connection_date = g.strava_token_data.get("updated_at") or g.strava_token_data.get("created_at")
        if connection_date:
            try:
                if connection_date.tzinfo is None:
                    connection_date = connection_date.replace(tzinfo=datetime.timezone.utc)
                else:
                    connection_date = connection_date.astimezone(datetime.timezone.utc)
                connection_date_formatted = connection_date.strftime("%d/%m/%Y às %H:%M UTC")
                connection_date = connection_date_formatted
            except AttributeError:
                 connection_date = str(connection_date)
                 print(f"DEBUG: Connection date fallback to string: {connection_date}")

    try:
        return render_template("conectar-apps.html", 
                               strava_connected=strava_connected, 
                               connection_date=connection_date)
    except Exception as render_error:
        print(f"!!! Render ERROR conectar_page: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar a página de conexão.", 500

@app.route("/strava/authorize")
@login_required
def strava_authorize():
    print("DEBUG: Accessing strava_authorize route")
    if not STRAVA_CLIENT_ID or not STRAVA_CLIENT_SECRET:
        print("ERROR: Strava client ID or secret not configured.")
        flash("Configuração do Strava incompleta.", "error"); return redirect(url_for("dashboard"))
    strava = OAuth2Session(STRAVA_CLIENT_ID, redirect_uri=STRAVA_REDIRECT_URI, scope=",".join(STRAVA_SCOPES))
    authorization_url, state = strava.authorization_url(STRAVA_AUTHORIZATION_URL, approval_prompt="force")
    session["oauth_state"] = state
    print(f"DEBUG: Generated OAuth state: {state}")
    print(f"DEBUG: Redirecting to Strava authorization URL: {authorization_url}")
    return redirect(authorization_url)

@app.route("/strava/callback")
@login_required
def strava_callback():
    print("DEBUG: Accessing strava_callback route")
    state_from_session = session.pop("oauth_state", None)
    state_from_request = request.args.get("state")
    print(f"DEBUG: State from session: {state_from_session}, State from request: {state_from_request}")
    if state_from_request != state_from_session:
        print("!!! ERROR: OAuth state mismatch!")
        flash("Erro de validação de estado (CSRF?).", "error"); 
        return redirect(url_for("dashboard"))
        
    error_from_request = request.args.get("error")
    if error_from_request:
        print(f"!!! ERROR: Strava authorization error: {error_from_request}")
        flash(f"Erro na autorização Strava: {error_from_request}.", "error"); 
        return redirect(url_for("dashboard"))
        
    code = request.args.get("code")
    print(f"DEBUG: Received Strava authorization code: {code}")
    if not code: 
        print("!!! ERROR: Strava code not received.")
        flash("Código Strava não recebido.", "error"); 
        return redirect(url_for("dashboard"))

    conn = None
    try:
        strava = OAuth2Session(STRAVA_CLIENT_ID, redirect_uri=STRAVA_REDIRECT_URI)
        print(f"DEBUG: Attempting to fetch token from {STRAVA_TOKEN_URL}")
        fetch_params_log = {
            "client_id": STRAVA_CLIENT_ID,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": STRAVA_REDIRECT_URI
        }
        print(f"DEBUG: Fetch token parameters (excluding secret): {fetch_params_log}")
        token = strava.fetch_token(STRAVA_TOKEN_URL, client_secret=STRAVA_CLIENT_SECRET, code=code, include_client_id=True)
        token_keys_str = str(list(token.keys())) if token else "None"
        print(f"DEBUG: Received token response (keys only): {token_keys_str}") 

        if not token or "access_token" not in token:
             print("!!! ERROR: Access token missing in Strava response!")
             flash("Erro ao obter token de acesso do Strava. Resposta inesperada.", "error")
             return redirect(url_for("dashboard"))

        access_token = token.get("access_token")
        refresh_token = token.get("refresh_token")
        expires_at_ts = token.get("expires_at")
        expires_at_dt = datetime.datetime.fromtimestamp(expires_at_ts, tz=datetime.timezone.utc) if expires_at_ts else None
        strava_athlete_id = token.get("athlete", {}).get("id")
        scopes = ",".join(token.get("scope", STRAVA_SCOPES))
        user_id = g.user["id"]
        print(f"DEBUG: Token details parsed - athlete_id: {strava_athlete_id}, expires_at: {expires_at_dt}")

        conn = get_db_connection(); cur = conn.cursor()
        sql = """INSERT INTO strava_tokens (user_id, access_token, refresh_token, expires_at, strava_athlete_id, scopes)
                 VALUES (%s, %s, %s, %s, %s, %s)
                 ON CONFLICT (user_id) DO UPDATE SET
                     access_token = EXCLUDED.access_token, refresh_token = EXCLUDED.refresh_token,
                     expires_at = EXCLUDED.expires_at, strava_athlete_id = EXCLUDED.strava_athlete_id,
                     scopes = EXCLUDED.scopes, updated_at = NOW();"""
        print(f"DEBUG: Executing UPSERT query for Strava token for user {user_id}")
        cur.execute(sql, (user_id, access_token, refresh_token, expires_at_dt, strava_athlete_id, scopes))
        conn.commit(); cur.close()
        print(f"DEBUG: Strava token saved/updated in DB for user {user_id}, athlete {strava_athlete_id}")
        flash("Conta Strava conectada!", "success")
    except Exception as e:
        error_details = traceback.format_exc(); 
        print(f"!!! CRITICAL ERROR fetching/saving Strava token: {e}\n{error_details}")
        flash("Erro crítico ao conectar com Strava. Verifique os logs.", "error")
        if conn: conn.rollback()
    finally: 
        if conn: conn.close()
    return redirect(url_for("conectar_page")) 

@app.route("/strava/disconnect", methods=["POST"])
@login_required
def strava_disconnect():
    print("DEBUG: Accessing strava_disconnect route")
    conn = None
    try:
        # TODO: Chamar API de deauthorize do Strava
        user_id = g.user["id"]
        print(f"DEBUG: Deleting Strava token for user {user_id}")
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM strava_tokens WHERE user_id = %s", (user_id,))
        conn.commit(); cur.close()
        print(f"DEBUG: Strava token deleted from DB for user {user_id}")
        flash("Conta Strava desconectada.", "success")
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc(); 
        print(f"!!! DB ERROR disconnecting Strava: {db_error}\n{error_details}")
        flash("Erro ao desconectar a conta Strava.", "error")
        if conn: conn.rollback()
    finally:
        if conn: conn.close()
    return redirect(url_for("conectar_page"))

@app.route("/strava/fetch", methods=["POST"])
@login_required
def strava_fetch_activities():
    print("DEBUG: Accessing strava_fetch_activities route")
    if not g.strava_token_data:
        print("WARN: Strava fetch attempted but user not connected.")
        flash("Conecte sua conta Strava primeiro.", "warning")
        return redirect(url_for("conectar_page"))

    user_registration_date = g.user.get("created_at")
    current_user_id = g.user.get("id")
    if not user_registration_date:
        print(f"WARN: User created_at not found in g.user for user {current_user_id}. Fetching from DB.")
        conn_temp = None
        try:
            conn_temp = get_db_connection()
            cur_temp = conn_temp.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur_temp.execute("SELECT created_at FROM users WHERE id = %s", (current_user_id,))
            user_reg_data = cur_temp.fetchone()
            cur_temp.close()
            if user_reg_data and user_reg_data["created_at"]:
                user_registration_date = user_reg_data["created_at"]
                g.user["created_at"] = user_registration_date
                print(f"DEBUG: Fetched user created_at from DB: {user_registration_date}")
            else:
                print(f"!!! ERROR: Could not find registration date for user {current_user_id}. Points calculation might be incorrect.")
                user_registration_date = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
                flash("Erro ao encontrar data de cadastro. Cálculo de pontos pode incluir atividades antigas.", "error")
        except Exception as e:
            print(f"!!! DB ERROR fetching user created_at: {e}\n{traceback.format_exc()}")
            flash("Erro ao buscar data de cadastro.", "error")
            user_registration_date = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
        finally:
            if conn_temp: conn_temp.close()

    if user_registration_date.tzinfo is None:
        print(f"WARN: user_registration_date {user_registration_date} was naive. Assuming UTC.")
        user_registration_date = user_registration_date.replace(tzinfo=datetime.timezone.utc)
    else:
        user_registration_date = user_registration_date.astimezone(datetime.timezone.utc)
    print(f"DEBUG: Ensured user_registration_date is UTC: {user_registration_date}")

    access_token = g.strava_token_data["access_token"]
    strava_session = OAuth2Session(token={"access_token": access_token})
    conn = None
    imported_count = 0
    skipped_count = 0
    total_points = 0

    try:
        activities_url = f"{STRAVA_API_BASE_URL}/athlete/activities"
        after_timestamp = int(user_registration_date.timestamp())
        params = {"per_page": 50, "after": after_timestamp}
        print(f"DEBUG: Fetching activities from Strava API: {activities_url} with params: {params}")
        response = strava_session.get(activities_url, params=params)
        response.raise_for_status() 
        activities = response.json()
        print(f"DEBUG: Fetched {len(activities)} activities from Strava API for user {current_user_id}") 

        if not activities:
            print("INFO: No recent activities found on Strava API since registration.")
        else:
            conn = get_db_connection()
            cur = conn.cursor()
            sql_upsert_activity = """INSERT INTO strava_activities 
                     (id, user_id, strava_athlete_id, name, distance, moving_time, elapsed_time, type, start_date, timezone, start_latlng, end_latlng, map_summary_polyline)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                     ON CONFLICT (id) DO UPDATE SET
                         name = EXCLUDED.name, distance = EXCLUDED.distance, moving_time = EXCLUDED.moving_time,
                         elapsed_time = EXCLUDED.elapsed_time, type = EXCLUDED.type, start_date = EXCLUDED.start_date,
                         timezone = EXCLUDED.timezone, start_latlng = EXCLUDED.start_latlng, end_latlng = EXCLUDED.end_latlng,
                         map_summary_polyline = EXCLUDED.map_summary_polyline, imported_at = NOW();"""
            
            print(f"DEBUG: Starting upsert loop for {len(activities)} activities.")
            for activity in activities:
                try:
                    activity_id = activity["id"]
                    print(f"DEBUG: Processing activity {activity_id}")
                    start_date_dt = datetime.datetime.fromisoformat(activity["start_date"].replace("Z", "+00:00"))
                    
                    if start_date_dt < user_registration_date:
                        print(f"DEBUG: Skipping activity {activity_id} (before registration date {user_registration_date})")
                        skipped_count += 1
                        continue
                        
                    start_latlng_str = str(activity.get("start_latlng")) if activity.get("start_latlng") else None
                    end_latlng_str = str(activity.get("end_latlng")) if activity.get("end_latlng") else None
                    map_polyline = activity.get("map", {}).get("summary_polyline")
                    activity_type = activity.get("type", "Unknown")
                    distance_meters = activity.get("distance", 0.0)

                    cur.execute(sql_upsert_activity, (
                        activity_id, current_user_id, activity["athlete"]["id"],
                        activity["name"], distance_meters, activity.get("moving_time", 0),
                        activity.get("elapsed_time", 0), activity_type, start_date_dt,
                        activity.get("timezone"), start_latlng_str, end_latlng_str, map_polyline
                    ))
                    imported_count += 1
                    print(f"DEBUG: Activity {activity_id} upserted.")

                except psycopg2.IntegrityError as ie:
                    conn.rollback()
                    print(f"WARN: Skipping activity {activity_id} due to DB integrity error: {ie}")
                    skipped_count += 1
                    conn = get_db_connection(); cur = conn.cursor() 
                except Exception as insert_error:
                    conn.rollback()
                    print(f"!!! ERROR inserting/updating activity {activity_id}: {insert_error}\n{traceback.format_exc()}")
                    skipped_count += 1
                    conn = get_db_connection(); cur = conn.cursor() 
            
            print(f"DEBUG: Committing {imported_count} successfully processed activities.")
            conn.commit()
            cur.close()

        if not conn or conn.closed:
            conn = get_db_connection()
        cur = conn.cursor()
        
        print(f"DEBUG: Recalculating total points for user {current_user_id} with filters (type=Run/Walk, after={user_registration_date})")
        sql_calculate_points = """
            SELECT SUM(distance) 
            FROM strava_activities 
            WHERE user_id = %s 
              AND type IN ("Run", "Walk") 
              AND start_date >= %s
        """
        cur.execute(sql_calculate_points, (current_user_id, user_registration_date))
        total_distance_result = cur.fetchone()
        total_distance_meters = total_distance_result[0] if total_distance_result and total_distance_result[0] else 0.0
        print(f"DEBUG: Total Run/Walk distance from DB since registration: {total_distance_meters} meters.")
        
        total_points = math.floor((total_distance_meters / 1000) * 10) if total_distance_meters else 0
        print(f"DEBUG: Calculated total points: {total_points}")

        print(f"DEBUG: Updating user points in DB for user {current_user_id}")
        cur.execute("UPDATE users SET points = %s WHERE id = %s", (total_points, current_user_id))
        conn.commit()
        print(f"DEBUG: User points updated to {total_points} for user {current_user_id}.") 

        cur.close()
        flash_message = f"{imported_count} atividades novas importadas/atualizadas. {skipped_count} ignoradas. "
        flash_message += f"Pontuação total (Corridas/Caminhadas desde cadastro) atualizada para {total_points}."
        flash(flash_message, "success")

    except requests.exceptions.RequestException as api_error:
        print(f"!!! Strava API ERROR fetching activities: {api_error}")
        flash("Erro ao buscar atividades da API do Strava.", "error")
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR processing Strava activities/points: {db_error}\n{error_details}")
        flash("Erro ao processar atividades/pontos do Strava.", "error")
        if conn: conn.rollback()
    finally:
        if conn: conn.close()

    return redirect(url_for("dashboard"))

# --- Execução da Aplicação --- 

if __name__ == "__main__":
    print("Starting Flask development server...")
    app.run(debug=True, host="0.0.0.0", port=5000)


