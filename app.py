# -*- coding: utf-8 -*-
import os
import sys
import psycopg2
from urllib.parse import urlparse
from flask import Flask, render_template, session, g, flash, redirect, url_for
from dotenv import load_dotenv
from functools import wraps

# Importar o blueprint de autenticação
from auth import auth_bp

# Carregar variáveis de ambiente do arquivo .env (útil para desenvolvimento local)
load_dotenv()

# --- INICIALIZAÇÃO TEMPORÁRIA DO BANCO DE DADOS ---
# Este bloco será executado uma vez quando a aplicação iniciar no Railway
# para criar as tabelas. DEVE SER REMOVIDO APÓS A PRIMEIRA IMPLANTAÇÃO BEM-SUCEDIDA.

CREATE_TABLES_SQL = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(80) UNIQUE NOT NULL,
        email VARCHAR(120) UNIQUE NOT NULL,
        password_hash VARCHAR(128) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS activities (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) NOT NULL,
        platform VARCHAR(50) NOT NULL,
        platform_activity_id VARCHAR(100),
        type VARCHAR(50),
        start_time TIMESTAMP NOT NULL,
        distance_km REAL,
        duration_seconds INTEGER,
        calories REAL,
        donation_amount REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS donation_items (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) NOT NULL,
        title VARCHAR(100) NOT NULL,
        description TEXT,
        category VARCHAR(50),
        location VARCHAR(100),
        status VARCHAR(20) DEFAULT 'available',
        image_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS interests (
        id SERIAL PRIMARY KEY,
        donation_item_id INTEGER REFERENCES donation_items(id) NOT NULL,
        user_id INTEGER REFERENCES users(id) NOT NULL,
        message TEXT,
        contact_info VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
]

def initialize_database_on_startup():
    print("=== TENTANDO INICIALIZAR BANCO DE DADOS NO STARTUP (TEMPORÁRIO) ===")
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("AVISO: DATABASE_URL não encontrada. Não foi possível inicializar o banco.")
        return

    conn = None
    try:
        print(f"Conectando ao banco de dados com URL: {db_url[:20]}...")
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        print("Conectado! Executando comandos CREATE TABLE IF NOT EXISTS...")
        for i, sql_command in enumerate(CREATE_TABLES_SQL):
            print(f"Executando SQL #{i+1}...")
            cur.execute(sql_command)
        conn.commit()
        print("Comandos SQL executados com sucesso (ou tabelas já existiam).")
        cur.close()
    except Exception as e:
        print(f"ERRO ao inicializar banco de dados no startup: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn is not None:
            conn.close()
            print("Conexão com banco de dados fechada.")
    print("=== FIM DA TENTATIVA DE INICIALIZAÇÃO TEMPORÁRIA ===")

# --- FIM DA INICIALIZAÇÃO TEMPORÁRIA ---

# Criar a instância da aplicação Flask
app = Flask(__name__)

# Executar a inicialização do banco de dados AQUI
initialize_database_on_startup()

# Configurar uma chave secreta (necessária para sessões, flash messages, etc.)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "default_secret_key_for_dev_only")

# Registrar o blueprint de autenticação
app.register_blueprint(auth_bp, url_prefix="/auth")

# Função para carregar usuário antes de cada requisição
@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        # Aqui você pode carregar mais dados do usuário do banco de dados se necessário
        g.user = {"id": user_id, "username": session.get("username")}

# Decorator para exigir login
def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash("Você precisa fazer login para acessar esta página.", "warning")
            return redirect(url_for("auth.login"))
        return view(**kwargs)
    return wrapped_view

# --- Rotas Principais --- 

@app.route("/")
def home():
    """Rota para a página inicial."""
    # Renderiza o template HTML da página inicial
    try:
        return render_template("home.html")
    except Exception as e:
        print(f"Erro ao renderizar home.html: {e}")
        return "Erro ao carregar a página inicial. Verifique os logs.", 500

@app.route("/mural")
def mural_page():
    """Rota para a página do mural de doações."""
    try:
        return render_template("mural.html")
    except Exception as e:
        print(f"Erro ao renderizar mural.html: {e}")
        return "Erro ao carregar o mural. Verifique os logs.", 500

@app.route("/conectar")
def conectar_page():
    """Rota para a página de conexão com apps de fitness."""
    try:
        return render_template("conectar-apps.html")
    except Exception as e:
        print(f"Erro ao renderizar conectar-apps.html: {e}")
        return "Erro ao carregar a página de conexão. Verifique os logs.", 500

@app.route("/dashboard")
@login_required
def dashboard():
    """Rota para o dashboard do usuário logado."""
    # Aqui você buscaria dados reais do banco de dados
    # Ex: últimas atividades, total doado, etc.
    # Por enquanto, usaremos dados de exemplo
    user_data = {
        "username": g.user["username"],
        "total_km": 125.5,
        "total_donated": 251.00,
        "last_activity": "Corrida de 10km em 28/04/2025"
    }
    try:
        return render_template("dashboard.html", user=user_data)
    except Exception as e:
        print(f"Erro ao renderizar dashboard.html: {e}")
        return "Erro ao carregar o dashboard. Verifique os logs.", 500

# --- Bloco para execução local (não usado pelo Gunicorn no Railway) ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

