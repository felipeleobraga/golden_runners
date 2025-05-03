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
        print("DEBUG: Attempting to connect to DB...")
        conn = psycopg2.connect(db_url)
        print("DEBUG: DB Connection successful.")
        return conn
    except psycopg2.OperationalError as e:
        print(f"!!! FATAL DB CONNECTION ERROR: {e}")
        raise

# --- Funções Auxiliares e Decorators --- 

@app.before_request
def load_logged_in_user():
    """Carrega dados do usuário logado (incluindo created_at) e token Strava (do DB) antes de cada request."""
    print("DEBUG: Entering load_logged_in_user")
    user_id = session.get("user_id")
    g.user = None
    g.strava_token_data = None # Renomeado para clareza
    print(f"DEBUG: Session user_id: {user_id}")

    if user_id is not None:
        print(f"DEBUG: User {user_id} found in session. Loading data...")
        # Carrega dados básicos do usuário da sessão
        g.user = {"id": user_id, "username": session.get("username")}
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Busca dados completos do usuário, incluindo pontos e created_at
            print(f"DEBUG: Fetching user data (incl. points, created_at) for user_id: {user_id}")
            cur.execute("SELECT id, username, points, created_at FROM users WHERE id = %s", (user_id,))
            user_data_from_db = cur.fetchone()
            print(f"DEBUG: User data from DB: {user_data_from_db}")
            if user_data_from_db:
                g.user.update(user_data_from_db) # Atualiza g.user com dados do DB
                print(f"DEBUG: g.user updated: {g.user}")
            else:
                print(f"WARN: No user data found in DB for user_id: {user_id}")
            
            # Busca token do Strava
            print(f"DEBUG: Fetching Strava token for user_id: {user_id}")
            cur.execute("SELECT *, created_at, updated_at FROM strava_tokens WHERE user_id = %s", (user_id,))
            token_data = cur.fetchone()
            print(f"DEBUG: Strava token data from DB: {token_data}")
            cur.close()
            
            if token_data:
                print("DEBUG: Strava token found in DB.")
                # Verifica se o token expirou (considerando um buffer de 60s)
                expires_at = token_data["expires_at"]
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                print(f"DEBUG: Token expires_at: {expires_at}, Now UTC: {now_utc}")
                if expires_at > now_utc + datetime.timedelta(seconds=60):
                    g.strava_token_data = token_data
                    print(f"DEBUG: Strava token is valid and loaded into g.strava_token_data for user {user_id}")
                else:
                    print(f"WARN: Strava token for user {user_id} expired. Needs refresh.")
                    # TODO: Implementar refresh token
            else:
                print(f"DEBUG: No Strava token found in DB for user {user_id}.")
                    
        except Exception as db_error: # Catching broader Exception
            error_details = traceback.format_exc()
            # Usando print para garantir visibilidade nos logs
            print(f"!!! CRITICAL DB ERROR in load_logged_in_user: {db_error}\n{error_details}") 
            g.user = None # Garante que o usuário não seja considerado logado se houver erro
            g.strava_token_data = None
        finally:
            if conn:
                print("DEBUG: Closing DB connection in load_logged_in_user.")
                conn.close()
    else:
        print("DEBUG: No user_id in session.")
    print("DEBUG: Exiting load_logged_in_user")

def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        print("DEBUG: Entering login_required decorator")
        if g.user is None:
            print("DEBUG: User not logged in, redirecting to login.")
            flash("Você precisa fazer login para acessar esta página.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        print("DEBUG: User logged in, proceeding to view.")
        return view(**kwargs)
    return wrapped_view

# --- Rotas Principais --- 

@app.route("/")
def home():
    print("DEBUG: Accessing home route")
    try: 
        print("DEBUG: Rendering home.html")
        return render_template("home.html")
    except Exception as e: 
        print(f"!!! Render ERROR home: {e}\n{traceback.format_exc()}"); 
        return "Erro ao carregar página inicial.", 500

@app.route("/dashboard")
@login_required
def dashboard():
    print("DEBUG: Accessing dashboard route")
    # g.user já contém os pontos carregados pelo before_request
    if not g.user:
        # Isso não deveria acontecer devido ao @login_required, mas é uma segurança extra
        print("!!! ERROR: g.user is None in dashboard route despite @login_required")
        flash("Erro interno: usuário não carregado.", "error")
        return redirect(url_for("auth.login"))
        
    print(f"DEBUG: Preparing user_data for dashboard. g.user: {g.user}")
    user_data = {
        "username": g.user.get("username", "N/A"),
        "points": g.user.get("points", 0), # Pega os pontos de g.user
        "total_km": 0, # Placeholder
        "total_donated": 0, # Placeholder
        "last_activity": "N/A" # Placeholder
    }
    print(f"DEBUG: user_data prepared: {user_data}")
    
    strava_connected = bool(g.strava_token_data)
    print(f"DEBUG: strava_connected: {strava_connected}")
    strava_activities = []
    conn = None

    if strava_connected:
        print("DEBUG: Strava is connected, attempting to fetch activities from DB.")
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            # CORRIGIDO: Aspas simples dentro da f-string (linha 182)
            print(f"DEBUG: Fetching activities for user_id: {g.user['id']}") 
            cur.execute("""
                SELECT id, name, distance, moving_time, type, start_date
                FROM strava_activities
                WHERE user_id = %s
                ORDER BY start_date DESC
                LIMIT 5
            """, (g.user["id"],))
            strava_activities = cur.fetchall()
            print(f"DEBUG: Fetched {len(strava_activities)} activities from DB: {strava_activities}")
            cur.close()
        except (Exception, psycopg2.DatabaseError) as db_error:
            error_details = traceback.format_exc()
            print(f"!!! DB ERROR fetching Strava activities for dashboard: {db_error}\n{error_details}")
            flash("Erro ao buscar atividades recentes do Strava.", "error")
            # Não retorna erro aqui, apenas mostra o dashboard sem atividades
            strava_activities = [] 
        finally:
            if conn:
                print("DEBUG: Closing DB connection in dashboard route.")
                conn.close()
    else:
        print("DEBUG: Strava is not connected, skipping activity fetch.")

    try: 
        print("DEBUG: Attempting to render dashboard.html")
        print(f"DEBUG: Data passed to template - user: {user_data}, strava_connected: {strava_connected}, strava_activities: {strava_activities}")
        return render_template("dashboard.html", 
                               user=user_data, 
                               strava_connected=strava_connected,
                               strava_activities=strava_activities)
    except Exception as e: 
        # Log detalhado do erro de renderização
        print(f"!!! CRITICAL Render ERROR dashboard: {e}\n{traceback.format_exc()}") 
        # Retorna uma mensagem de erro mais genérica para o usuário
        return "Erro interno ao carregar o dashboard. Por favor, tente novamente mais tarde.", 500

# --- Rotas do Mural de Doações --- 

@app.route("/mural")
def mural_page():
    print("DEBUG: Accessing mural route")
    conn = None
    items = []
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        print("DEBUG: Fetching mural items from DB")
        cur.execute("""
            SELECT di.*, u.username AS donor_username 
            FROM donation_items di
            JOIN users u ON di.user_id = u.id
            ORDER BY di.created_at DESC
        """)
        items = cur.fetchall()
        print(f"DEBUG: Fetched {len(items)} mural items")
        cur.close()
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR fetching mural items: {db_error}\n{error_details}")
        flash("Erro ao carregar os itens do mural.", "error")
    finally:
        if conn:
            print("DEBUG: Closing DB connection in mural route.")
            conn.close()
    
    try:
        print("DEBUG: Rendering mural.html")
        return render_template("mural.html", items=items)
    except Exception as render_error:
        print(f"!!! Render ERROR mural: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar a página do mural.", 500

@app.route("/mural/adicionar", methods=("GET", "POST"))
@login_required
def add_item():
    print(f"DEBUG: Accessing add_item route, method: {request.method}")
    form_data = {}
    if request.method == "POST":
        print("DEBUG: Processing POST request for add_item")
        conn = None
        try:
            # Coleta dados do formulário
            category = request.form.get("category")
            description = request.form.get("description")
            location = request.form.get("location")
            image_url = request.form.get("image_url")
            color = request.form.get("color")
            size = request.form.get("size")
            brand = request.form.get("brand")
            whatsapp_link = request.form.get("whatsapp_link")
            user_id = g.user["id"]
            print(f"DEBUG: Form data received: category={category}, desc={description[:20]}..., loc={location}, user={user_id}")

            # Validação básica
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
            print("DEBUG: Executing INSERT query for new item")
            cur.execute(sql, (user_id, category, description, location, image_url, color, size, brand, whatsapp_link))
            conn.commit()
            print("DEBUG: New item inserted and committed.")
            cur.close()
            flash("Item adicionado com sucesso!", "success")
            return redirect(url_for("mural_page"))

        except (Exception, psycopg2.DatabaseError) as db_error:
            error_details = traceback.format_exc()
            print(f"!!! DB ERROR adding item: {db_error}\n{error_details}")
            flash("Erro ao adicionar o item no banco de dados.", "error")
            if conn: 
                print("DEBUG: Rolling back DB transaction.")
                conn.rollback()
            form_data = request.form
        finally:
            if conn:
                print("DEBUG: Closing DB connection in add_item (POST).")
                conn.close()
    
    # Se GET ou se houve erro no POST, renderiza o formulário
    try:
        print("DEBUG: Rendering add_item.html for GET request or POST error")
        return render_template("add_item.html", form_data=form_data)
    except Exception as render_error:
        print(f"!!! Render ERROR add_item: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar o formulário de adição.", 500

@app.route("/item/<int:item_id>")
def item_detail(item_id):
    print(f"DEBUG: Accessing item_detail route for item_id: {item_id}")
    conn = None
    item = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        print(f"DEBUG: Fetching details for item {item_id}")
        cur.execute("""
            SELECT di.*, u.username AS donor_username 
            FROM donation_items di
            JOIN users u ON di.user_id = u.id
            WHERE di.id = %s
        """, (item_id,))
        item = cur.fetchone()
        print(f"DEBUG: Fetched item details: {item}")
        cur.close()
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB ERROR fetching item detail {item_id}: {db_error}\n{error_details}")
        flash("Erro ao buscar detalhes do item.", "error")
    finally:
        if conn:
            print("DEBUG: Closing DB connection in item_detail.")
            conn.close()

    if item is None:
        print(f"WARN: Item {item_id} not found.")
        flash("Item não encontrado.", "warning")
        return redirect(url_for("mural_page"))

    try:
        print(f"DEBUG: Rendering item_detail.html for item {item_id}")
        return render_template("item_detail.html", item=item)
    except Exception as render_error:
        print(f"!!! Render ERROR item_detail {item_id}: {render_error}\n{traceback.format_exc()}")
        return "Erro ao carregar a página de detalhes do item.", 500

@app.route("/item/<int:item_id>/interesse", methods=["POST"])
@login_required
def express_interest(item_id):
    print(f"DEBUG: Accessing express_interest route for item_id: {item_id}")
    # Lógica futura: registrar interesse no banco, notificar doador, etc.
    # CORRIGIDO: Aspas simples dentro da f-string
    print(f"DEBUG: User {g.user['id']} expressed interest in item {item_id}") 
    flash("Seu interesse foi registrado! O doador será notificado (funcionalidade futura).", "info")
    return redirect(url_for("item_detail", item_id=item_id))

# --- Rotas de Conexão Strava --- 

@app.route("/conectar")
@login_required
def conectar_page():
    print("DEBUG: Accessing conectar_page route")
    strava_connected = bool(g.strava_token_data)
    connection_date = None
    print(f"DEBUG: Strava connected status: {strava_connected}")
    if strava_connected:
        connection_date = g.strava_token_data.get("updated_at") or g.strava_token_data.get("created_at")
        print(f"DEBUG: Connection date raw: {connection_date}")
        if connection_date:
            try:
                connection_date = connection_date.strftime("%d/%m/%Y às %H:%M")
                print(f"DEBUG: Connection date formatted: {connection_date}")
            except AttributeError:
                 connection_date = str(connection_date)
                 print(f"DEBUG: Connection date fallback to string: {connection_date}")

    try:
        print("DEBUG: Rendering conectar-apps.html")
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
        # Não logar o client_secret
        fetch_params_log = {
            "client_id": STRAVA_CLIENT_ID,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": STRAVA_REDIRECT_URI
        }
        print(f"DEBUG: Fetch token parameters (excluding secret): {fetch_params_log}")
        token = strava.fetch_token(STRAVA_TOKEN_URL, client_secret=STRAVA_CLIENT_SECRET, code=code, include_client_id=True)
        # Não logar o token completo em produção, apenas confirmação
        print(f"DEBUG: Received token response (keys only): {list(token.keys()) if token else 'None'}") 

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
        if conn: 
            print("DEBUG: Rolling back DB transaction.")
            conn.rollback()
    finally: 
        if conn: 
            print("DEBUG: Closing DB connection in strava_callback.")
            conn.close()
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
        # Resetar pontos ao desconectar? Decidimos manter por enquanto.
        # cur.execute("UPDATE users SET points = 0 WHERE id = %s", (user_id,))
        conn.commit(); cur.close()
        print(f"DEBUG: Strava token deleted from DB for user {user_id}")
        flash("Conta Strava desconectada.", "success")
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc(); 
        print(f"!!! DB ERROR disconnecting Strava: {db_error}\n{error_details}")
        flash("Erro ao desconectar a conta Strava.", "error")
        if conn: 
            print("DEBUG: Rolling back DB transaction.")
            conn.rollback()
    finally:
        if conn:
            print("DEBUG: Closing DB connection in strava_disconnect.")
            conn.close()
    return redirect(url_for("conectar_page"))

@app.route("/strava/fetch", methods=["POST"])
@login_required
def strava_fetch_activities():
    print("DEBUG: Accessing strava_fetch_activities route")
    if not g.strava_token_data:
        print("WARN: Strava fetch attempted but user not connected.")
        flash("Conecte sua conta Strava primeiro.", "warning")
        return redirect(url_for("conectar_page"))

    # Busca a data de cadastro do usuário (já deve estar em g.user)
    user_registration_date = g.user.get("created_at")
    if not user_registration_date:
        # Fallback: Se não encontrar a data (usuário antigo?), busca no DB
        print(f"WARN: User created_at not found in g.user for user {g.user['id']}. Fetching from DB.")
        conn_temp = None
        try:
            conn_temp = get_db_connection()
            cur_temp = conn_temp.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur_temp.execute("SELECT created_at FROM users WHERE id = %s", (g.user["id"],))
            user_reg_data = cur_temp.fetchone()
            cur_temp.close()
            if user_reg_data and user_reg_data["created_at"]:
                user_registration_date = user_reg_data["created_at"]
                g.user["created_at"] = user_registration_date # Atualiza em g.user para futuras chamadas
                print(f"DEBUG: Fetched user created_at from DB: {user_registration_date}")
            else:
                # Se ainda não encontrar, usa uma data muito antiga para incluir tudo (ou lança erro?)
                print(f"!!! ERROR: Could not find registration date for user {g.user['id']}. Points calculation might be incorrect.")
                # Define uma data padrão antiga para não quebrar, mas loga o erro
                user_registration_date = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
                flash("Erro ao encontrar data de cadastro. Cálculo de pontos pode incluir atividades antigas.", "error")
        except Exception as e:
            print(f"!!! DB ERROR fetching user created_at: {e}\n{traceback.format_exc()}")
            flash("Erro ao buscar data de cadastro.", "error")
            # Define uma data padrão antiga para não quebrar
            user_registration_date = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
        finally:
            if conn_temp:
                conn_temp.close()

    access_token = g.strava_token_data["access_token"]
    strava_session = OAuth2Session(token={"access_token": access_token})
    conn = None
    imported_count = 0
    skipped_count = 0
    total_points = 0 # Reinicia para recalcular

    try:
        # Busca atividades da API do Strava
        activities_url = f"{STRAVA_API_BASE_URL}/athlete/activities"
        # Adiciona filtro 'after' na API se possível (melhor performance)
        # Convertendo user_registration_date para timestamp Unix
        after_timestamp = int(user_registration_date.timestamp())
        params = {"per_page": 50, "after": after_timestamp} # Busca 50 atividades APÓS o cadastro
        print(f"DEBUG: Fetching activities from Strava API: {activities_url} with params: {params}")
        response = strava_session.get(activities_url, params=params)
        response.raise_for_status() 
        activities = response.json()
        # CORRIGIDO: Aspas simples dentro da f-string
        print(f"DEBUG: Fetched {len(activities)} activities from Strava API for user {g.user['id']}") 

        if not activities:
            print("INFO: No recent activities found on Strava API since registration.")
            # Mesmo sem novas atividades, recalcula os pontos com base no que já está no DB
            # flash("Nenhuma atividade nova encontrada no Strava desde o cadastro.", "info")
            # Não retorna aqui, continua para recalcular pontos
        else:
            conn = get_db_connection()
            cur = conn.cursor()

            # Insere ou atualiza atividades no banco
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
                    
                    # Pula atividades anteriores ao cadastro (redundante com filtro API, mas seguro)
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
                        activity_id,
                        g.user["id"],
                        activity["athlete"]["id"],
                        activity["name"],
                        distance_meters,
                        activity.get("moving_time", 0),
                        activity.get("elapsed_time", 0),
                        activity_type,
                        start_date_dt,
                        activity.get("timezone"),
                        start_latlng_str,
                        end_latlng_str,
                        map_polyline
                    ))
                    imported_count += 1
                    print(f"DEBUG: Activity {activity_id} upserted.")

                except psycopg2.IntegrityError as ie:
                    conn.rollback() # Desfaz a transação atual para esta atividade
                    print(f"WARN: Skipping activity {activity_id} due to DB integrity error: {ie}")
                    skipped_count += 1
                    # Inicia nova transação para a próxima atividade
                    conn = get_db_connection(); cur = conn.cursor() 
                except Exception as insert_error:
                    conn.rollback()
                    print(f"!!! ERROR inserting/updating activity {activity_id}: {insert_error}\n{traceback.format_exc()}")
                    skipped_count += 1
                    # Inicia nova transação para a próxima atividade
                    conn = get_db_connection(); cur = conn.cursor() 
            
            # Commit final das atividades inseridas/atualizadas com sucesso
            print(f"DEBUG: Committing {imported_count} successfully processed activities.")
            conn.commit()
            cur.close() # Fecha o cursor após o loop de inserção

        # --- CÁLCULO TOTAL DE PONTOS (COM FILTROS) --- 
        # Abre nova conexão/cursor se necessário (se não houve atividades novas)
        if not conn or conn.closed:
            conn = get_db_connection()
        cur = conn.cursor() # Abre ou reabre o cursor
        
        print(f"DEBUG: Recalculating total points for user {g.user['id']} with filters (type=Run/Walk, after={user_registration_date})")
        sql_calculate_points = """
            SELECT SUM(distance) 
            FROM strava_activities 
            WHERE user_id = %s 
              AND type IN ("Run", "Walk") 
              AND start_date >= %s
        """
        cur.execute(sql_calculate_points, (g.user["id"], user_registration_date))
        total_distance_result = cur.fetchone()
        total_distance_meters = total_distance_result[0] if total_distance_result and total_distance_result[0] else 0.0
        print(f"DEBUG: Total Run/Walk distance from DB since registration: {total_distance_meters} meters.")
        
        total_points = math.floor((total_distance_meters / 1000) * 10) if total_distance_meters else 0
        print(f"DEBUG: Calculated total points: {total_points}")

        print(f"DEBUG: Updating user points in DB for user {g.user['id']}")
        cur.execute("UPDATE users SET points = %s WHERE id = %s", (total_points, g.user["id"]))
        conn.commit()
        print(f"DEBUG: User points updated to {total_points} for user {g.user['id']}.") 
        # -------------------------------------------------

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
        if conn: 
            print("DEBUG: Rolling back DB transaction due to error.")
            conn.rollback()
    finally:
        if conn:
            print("DEBUG: Closing DB connection in strava_fetch_activities.")
            conn.close()

    return redirect(url_for("dashboard"))

# --- Execução da Aplicação --- 

if __name__ == "__main__":
    # O Flask Development Server não é recomendado para produção.
    # Use um servidor WSGI como Gunicorn ou uWSGI.
    # Ex: gunicorn --bind 0.0.0.0:5000 app:app
    print("Starting Flask development server...")
    app.run(debug=True, host="0.0.0.0", port=5000)

