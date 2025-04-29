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

# Criar a instância da aplicação Flask
app = Flask(__name__)

# --- Função TEMPORÁRIA para alterar o schema do banco de dados ---
def alter_database_schema_on_startup():
    """Tenta alterar a coluna password_hash para VARCHAR(255) no startup."""
    print("=== TENTANDO ALTERAR SCHEMA DO BANCO DE DADOS NO STARTUP (TEMPORÁRIO) ===")
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL não encontrada. Pulando alteração de schema.")
        print("=== FIM DA TENTATIVA DE ALTERAÇÃO TEMPORÁRIA ===")
        return

    conn = None
    try:
        print("Conectando ao banco de dados para alteração...")
        result = urlparse(db_url)
        username = result.username
        password = result.password
        database = result.path[1:]
        hostname = result.hostname
        port = result.port
        conn = psycopg2.connect(
            database=database,
            user=username,
            password=password,
            host=hostname,
            port=port
        )
        print("Conectado! Executando comando ALTER TABLE...")
        with conn.cursor() as cur:
            # Comando para alterar a coluna
            alter_command = "ALTER TABLE users ALTER COLUMN password_hash TYPE VARCHAR(255);"
            cur.execute(alter_command)
            conn.commit()
            print("Comando ALTER TABLE executado com sucesso.")
    except psycopg2.Error as e:
        # Se der erro (ex: coluna já alterada), apenas loga e continua
        print(f"Erro ao executar ALTER TABLE (pode já ter sido aplicado): {e}")
        if conn:
            conn.rollback() # Desfaz a transação em caso de erro
    except Exception as e:
        print(f"Erro inesperado durante a alteração do schema: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
            print("Conexão com o banco de dados fechada.")
        print("=== FIM DA TENTATIVA DE ALTERAÇÃO TEMPORÁRIA ===")

# --- Chamada TEMPORÁRIA para alterar o schema --- 
# Execute isso logo após criar a instância do app
alter_database_schema_on_startup()
# --- Fim da chamada TEMPORÁRIA ---

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
        # Corrigindo o caminho do template
        return render_template("../wireframes/home.html") 
    except Exception as e:
        print(f"Erro ao renderizar home.html: {e}")
        return "Erro ao carregar a página inicial. Verifique os logs.", 500

@app.route("/mural")
def mural_page():
    """Rota para a página do mural de doações."""
    try:
        # Corrigindo o caminho do template
        return render_template("../wireframes/mural.html") 
    except Exception as e:
        print(f"Erro ao renderizar mural.html: {e}")
        return "Erro ao carregar o mural. Verifique os logs.", 500

@app.route("/conectar")
def conectar_page():
    """Rota para a página de conexão com apps de fitness."""
    try:
        # Corrigindo o caminho do template
        return render_template("../wireframes/conectar-apps.html") 
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
        # Assumindo que dashboard.html está na pasta templates padrão
        return render_template("dashboard.html", user=user_data) 
    except Exception as e:
        print(f"Erro ao renderizar dashboard.html: {e}")
        return "Erro ao carregar o dashboard. Verifique os logs.", 500

# --- Bloco para execução local (não usado pelo Gunicorn no Railway) ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

