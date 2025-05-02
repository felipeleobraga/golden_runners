# -*- coding: utf-8 -*-
import os
import sys
import psycopg2
import psycopg2.extras # Adicionado para buscar resultados como dicionários
import traceback # Importado para log detalhado de erros
import requests # Adicionado para fazer requisições HTTP
import json # Adicionado para lidar com JSON
import datetime # Adicionado para lidar com timestamps
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
        print(f"Erro ao conectar ao banco de dados: {e}")
        raise

# --- Funções Auxiliares e Decorators --- 

@app.before_request
def load_logged_in_user():
    """Carrega dados do usuário logado e token Strava (do DB) antes de cada request."""
    user_id = session.get("user_id")
    g.user = None
    g.strava_token_data = None # Renomeado para clareza

    if user_id is not None:
        g.user = {"id": user_id, "username": session.get("username")}
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM strava_tokens WHERE user_id = %s", (user_id,))
            token_data = cur.fetchone()
            cur.close()
            
            if token_data:
                # TODO: Implementar refresh token se expirado
                if token_data["expires_at"] > datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=60):
                    g.strava_token_data = token_data
                    print(f"Strava token loaded from DB for user {user_id}")
                else:
                    print(f"Strava token for user {user_id} expired. Needs refresh.")
                    # flash("Sua conexão com o Strava expirou. Por favor, conecte novamente.", "warning")
                    
        except Exception as db_error: # Catching broader Exception
            error_details = traceback.format_exc()
            print(f"!!! DETAILED DB ERROR loading Strava token: {db_error}\n{error_details}")
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
    try: return render_template("home.html")
    except Exception as e: print(f"Render ERROR home: {e}"); return "Erro ao carregar página.", 500

@app.route("/dashboard")
@login_required
def dashboard():
    user_data = {"username": g.user["username"], "total_km": 0, "total_donated": 0, "last_activity": "N/A"}
    strava_connected = bool(g.strava_token_data)
    try: return render_template("dashboard.html", user=user_data, strava_connected=strava_connected)
    except Exception as e: print(f"Render ERROR dashboard: {e}"); return "Erro ao carregar dashboard.", 500

# --- Rotas do Mural de Doações --- 

@app.route("/mural")
def mural_page():
    """Exibe o mural com os itens de doação."""
    conn = None
    items = []
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Seleciona os itens, incluindo o nome de usuário do doador
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
        print(f"!!! Render ERROR mural: {render_error}")
        return "Erro ao carregar a página do mural.", 500

@app.route("/mural/adicionar", methods=("GET", "POST"))
@login_required
def add_item():
    """Adiciona um novo item de doação."""
    form_data = {}
    if request.method == "POST":
        conn = None
        try:
            # Coleta dados do formulário
            category = request.form.get("category")
            description = request.form.get("description")
            location = request.form.get("location")
            image_url = request.form.get("image_url") # TODO: Implementar upload de imagem
            color = request.form.get("color")
            size = request.form.get("size")
            brand = request.form.get("brand")
            whatsapp_link = request.form.get("whatsapp_link")
            user_id = g.user["id"]

            # Validação básica (pode ser melhorada)
            if not category or not description or not location:
                flash("Categoria, descrição e localização são obrigatórios.", "warning")
                form_data = request.form # Mantém os dados no formulário
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
            form_data = request.form # Mantém os dados no formulário
        finally:
            if conn:
                conn.close()
    
    # Se GET ou se houve erro no POST, renderiza o formulário
    try:
        print("DEBUG: Attempting to render add_item.html for GET request")
        return render_template("add_item.html", form_data=form_data)
    except Exception as render_error:
        print(f"!!! Render ERROR add_item: {render_error}")
        return "Erro ao carregar o formulário de adição.", 500

@app.route("/item/<int:item_id>")
def item_detail(item_id):
    """Exibe os detalhes de um item específico."""
    conn = None
    item = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Seleciona o item e o nome de usuário do doador
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
        flash("Item não encontrado.", "warning")
        return redirect(url_for("mural_page"))

    try:
        return render_template("item_detail.html", item=item)
    except Exception as render_error:
        print(f"!!! Render ERROR item_detail {item_id}: {render_error}")
        return "Erro ao carregar a página de detalhes do item.", 500

@app.route("/item/<int:item_id>/interesse", methods=["POST"])
@login_required
def express_interest(item_id):
    """Registra o interesse de um usuário em um item (placeholder)."""
    # Lógica futura: registrar interesse no banco, notificar doador, etc.
    print(f"User {g.user['id']} expressed interest in item {item_id}")
    flash("Seu interesse foi registrado! O doador será notificado (funcionalidade futura).", "info")
    return redirect(url_for("item_detail", item_id=item_id))

# --- Rotas de Conexão Strava --- 

@app.route("/strava/authorize")
@login_required
def strava_authorize():
    if not STRAVA_CLIENT_ID or not STRAVA_CLIENT_SECRET:
        flash("Configuração do Strava incompleta.", "error"); return redirect(url_for("dashboard"))
    strava = OAuth2Session(STRAVA_CLIENT_ID, redirect_uri=STRAVA_REDIRECT_URI, scope=",".join(STRAVA_SCOPES))
    authorization_url, state = strava.authorization_url(STRAVA_AUTHORIZATION_URL, approval_prompt="force")
    session["oauth_state"] = state
    print(f"Redirecting to Strava: {authorization_url}")
    return redirect(authorization_url)

@app.route("/strava/callback")
@login_required
def strava_callback():
    if request.args.get("state") != session.pop("oauth_state", None):
        flash("Erro de validação de estado (CSRF?).", "error"); print("OAuth state mismatch!"); return redirect(url_for("dashboard"))
    if "error" in request.args:
        flash(f"Erro na autorização Strava: {request.args.get("error")}.", "error"); print(f"Strava auth error: {request.args.get("error")}"); return redirect(url_for("dashboard"))
    code = request.args.get("code")
    if not code: flash("Código Strava não recebido.", "error"); print("Strava code not received."); return redirect(url_for("dashboard"))

    conn = None
    try:
        strava = OAuth2Session(STRAVA_CLIENT_ID, redirect_uri=STRAVA_REDIRECT_URI)
        print(f"Attempting to fetch token from {STRAVA_TOKEN_URL} with code: {code}") # Log Adicional
        # Log dos parâmetros que serão enviados (exceto o secret)
        fetch_params = {
            "client_id": STRAVA_CLIENT_ID,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": STRAVA_REDIRECT_URI
        }
        print(f"Fetch token parameters (excluding secret): {fetch_params}")
        
        # Tenta buscar o token
        token = strava.fetch_token(STRAVA_TOKEN_URL, client_secret=STRAVA_CLIENT_SECRET, code=code, include_client_id=True)
        
        print(f"Received token response: {token}") # Log Adicional

        # Verifica se o token foi recebido corretamente
        if not token or "access_token" not in token:
             print("!!! Access token missing in Strava response!")
             flash("Erro ao obter token de acesso do Strava. Resposta inesperada.", "error")
             return redirect(url_for("dashboard"))

        access_token = token.get("access_token")
        refresh_token = token.get("refresh_token")
        expires_at_dt = datetime.datetime.fromtimestamp(token.get("expires_at"), tz=datetime.timezone.utc)
        strava_athlete_id = token.get("athlete", {}).get("id")
        scopes = ",".join(token.get("scope", STRAVA_SCOPES))
        user_id = g.user["id"]

        conn = get_db_connection(); cur = conn.cursor()
        sql = """INSERT INTO strava_tokens (user_id, access_token, refresh_token, expires_at, strava_athlete_id, scopes)
                 VALUES (%s, %s, %s, %s, %s, %s)
                 ON CONFLICT (user_id) DO UPDATE SET
                     access_token = EXCLUDED.access_token, refresh_token = EXCLUDED.refresh_token,
                     expires_at = EXCLUDED.expires_at, strava_athlete_id = EXCLUDED.strava_athlete_id,
                     scopes = EXCLUDED.scopes, updated_at = NOW();"""
        cur.execute(sql, (user_id, access_token, refresh_token, expires_at_dt, strava_athlete_id, scopes))
        conn.commit(); cur.close()
        print(f"Strava token saved to DB for user {user_id}, athlete {strava_athlete_id}")
        flash("Conta Strava conectada!", "success")
    except Exception as e:
        error_details = traceback.format_exc(); print(f"!!! ERROR fetching/saving Strava token: {e}\n{error_details}")
        flash("Erro ao conectar com Strava.", "error")
        if conn: conn.rollback() # Rollback em caso de erro no DB
    finally: 
        if conn: conn.close()
    return redirect(url_for("dashboard"))

@app.route("/strava/disconnect", methods=["POST"])
@login_required
def strava_disconnect():
    conn = None
    try:
        # TODO: Chamar API de deauthorize do Strava
        user_id = g.user["id"]
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM strava_tokens WHERE user_id = %s", (user_id,))
        conn.commit(); cur.close()
        print(f"Strava token deleted from DB for user {user_id}")
        g.strava_token_data = None
        flash("Conta Strava desconectada.", "info")
    except Exception as db_error:
        error_details = traceback.format_exc(); print(f"!!! DB ERROR disconnecting Strava: {db_error}\n{error_details}")
        flash("Erro ao desconectar Strava.", "error"); conn.rollback() if conn else None
    finally: conn.close() if conn else None
    return redirect(url_for("dashboard"))

# --- Rota de Busca de Atividades Strava --- 

@app.route("/strava/fetch", methods=["POST"])
@login_required
def strava_fetch_activities():
    """Busca atividades recentes do Strava e salva no DB."""
    if not g.strava_token_data:
        flash("Conecte sua conta Strava primeiro.", "warning")
        return redirect(url_for("conectar_page"))

    access_token = g.strava_token_data.get("access_token")
    strava_athlete_id = g.strava_token_data.get("strava_athlete_id")
    user_id = g.user["id"]
    
    # Endpoint da API do Strava para buscar atividades do atleta logado
    activities_url = f"{STRAVA_API_BASE_URL}/athlete/activities"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Parâmetros opcionais: buscar atividades depois de uma certa data/hora
    # TODO: Buscar a data da última atividade importada do DB para evitar buscar tudo sempre
    # params = {"after": timestamp_da_ultima_atividade}
    params = {"per_page": 50} # Busca as últimas 50 atividades por enquanto

    conn = None
    activities_fetched = 0
    activities_saved = 0
    try:
        print(f"Fetching Strava activities for user {user_id}...")
        response = requests.get(activities_url, headers=headers, params=params)
        response.raise_for_status() # Levanta erro para status HTTP 4xx/5xx
        activities = response.json()
        activities_fetched = len(activities)
        print(f"Fetched {activities_fetched} activities from Strava API.")

        if not activities:
            flash("Nenhuma nova atividade encontrada no Strava.", "info")
            return redirect(url_for("dashboard"))

        # Salvar atividades no banco de dados
        conn = get_db_connection()
        cur = conn.cursor()
        
        sql_insert = """
            INSERT INTO strava_activities 
            (id, user_id, strava_athlete_id, name, distance, moving_time, elapsed_time, type, start_date, timezone, start_latlng, end_latlng, map_summary_polyline)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING; -- Ignora se a atividade já existe
        """
        
        for activity in activities:
            # Tratamento de dados (ex: latlng como string)
            start_latlng_str = str(activity.get("start_latlng")) if activity.get("start_latlng") else None
            end_latlng_str = str(activity.get("end_latlng")) if activity.get("end_latlng") else None
            map_polyline = activity.get("map", {}).get("summary_polyline")
            # Converter data string ISO 8601 para datetime object
            start_date_dt = datetime.datetime.fromisoformat(activity["start_date"].replace("Z", "+00:00"))

            values = (
                activity["id"],
                user_id,
                strava_athlete_id,
                activity["name"],
                activity.get("distance"),
                activity.get("moving_time"),
                activity.get("elapsed_time"),
                activity.get("type"),
                start_date_dt,
                activity.get("timezone"),
                start_latlng_str,
                end_latlng_str,
                map_polyline
            )
            try:
                cur.execute(sql_insert, values)
                # Verifica se a inserção ocorreu (rowcount > 0)
                if cur.rowcount > 0:
                    activities_saved += 1
            except Exception as insert_err:
                print(f"Error inserting activity {activity["id"]}: {insert_err}")
                conn.rollback() # Desfaz a inserção da atividade atual em caso de erro
                # Considerar logar o erro e continuar com a próxima atividade

        conn.commit()
        cur.close()
        print(f"Saved {activities_saved} new activities to DB.")
        flash(f"{activities_saved} novas atividades do Strava importadas com sucesso!", "success")

    except requests.exceptions.RequestException as req_err:
        error_details = traceback.format_exc()
        print(f"!!! Strava API request error: {req_err}\n{error_details}")
        flash("Erro ao buscar atividades no Strava. Verifique sua conexão ou tente mais tarde.", "error")
        if conn: conn.rollback() # Garante rollback se erro ocorreu antes do commit
    except (Exception, psycopg2.DatabaseError) as db_error:
        error_details = traceback.format_exc()
        print(f"!!! DB error saving Strava activities: {db_error}\n{error_details}")
        flash("Erro ao salvar atividades no banco de dados.", "error")
        if conn: conn.rollback()
    finally:
        if conn:
            conn.close()

    return redirect(url_for("dashboard"))


# --- Rota de Conexão (Página) --- 

@app.route("/conectar")
@login_required
def conectar_page():
    strava_connected = bool(g.strava_token_data)
    try: return render_template("conectar-apps.html", strava_connected=strava_connected)
    except Exception as e: print(f"Render ERROR conectar-apps: {e}"); return "Erro ao carregar página.", 500

# --- Bloco para execução local ---
if __name__ == "__main__":
    if 'localhost' in STRAVA_REDIRECT_URI and os.environ.get("FLASK_DEBUG") == "True":
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "False") == "True")


