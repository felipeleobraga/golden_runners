# -*- coding: utf-8 -*-
import os
import sys
import psycopg2
import psycopg2.extras # Adicionado para buscar resultados como dicionários
import traceback # Importado para log detalhado de erros
from urllib.parse import urlparse
from flask import Flask, render_template, session, g, flash, redirect, url_for, request
from dotenv import load_dotenv
from functools import wraps

# Importar o blueprint de autenticação
from auth import auth_bp

# Carregar variáveis de ambiente do arquivo .env (útil para desenvolvimento local)
load_dotenv()

# Criar a instância da aplicação Flask
app = Flask(__name__)

# Configurar uma chave secreta (necessária para sessões, flash messages, etc.)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "default_secret_key_for_dev_only")

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
        # Usar RealDictCursor para obter resultados como dicionários
        conn = psycopg2.connect(db_url)
        return conn
    except psycopg2.OperationalError as e:
        print(f"Erro ao conectar ao banco de dados: {e}")
        raise

# --- Funções Auxiliares e Decorators --- 

@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        # Carregar mais dados do usuário se necessário, por enquanto só id e username
        g.user = {"id": user_id, "username": session.get("username")}

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
    """Rota para a página inicial."""
    try:
        # Tenta renderizar a partir da pasta templates primeiro
        return render_template("home.html")
    except Exception as e:
        # Log explícito do erro
        error_details = traceback.format_exc()
        print(f"!!! DETAILED ERROR rendering home.html: {e}\n{error_details}")
        # Fallback para wireframes se não encontrar em templates
        try:
            print("Tentando renderizar home.html do caminho /wireframes como fallback...")
            return render_template("../wireframes/home.html")
        except Exception as fallback_e:
            # Log explícito do erro de fallback
            fallback_error_details = traceback.format_exc()
            print(f"!!! DETAILED FALLBACK ERROR rendering home.html: {fallback_e}\n{fallback_error_details}")
            return "Erro ao carregar a página inicial. Verifique os logs.", 500

@app.route("/dashboard")
@login_required
def dashboard():
    """Rota para o dashboard do usuário logado."""
    # No futuro, buscar dados reais do usuário e atividades
    user_data = {
        "username": g.user["username"],
        "total_km": 0,
        "total_donated": 0,
        "last_activity": "Nenhuma atividade registrada"
    }
    try:
        return render_template("dashboard.html", user=user_data)
    except Exception as e:
        # Log explícito do erro
        error_details = traceback.format_exc()
        print(f"!!! DETAILED ERROR rendering dashboard.html: {e}\n{error_details}")
        return "Erro ao carregar o dashboard. Verifique os logs.", 500

# --- Rotas do Mural de Doações --- 

@app.route("/mural")
def mural_page():
    """Rota para a página do mural de doações (listagem)."""
    conn = None
    items = []
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Modificado: Selecionar mais campos necessários para o template
        cur.execute("SELECT di.id, di.user_id, di.title, di.description, di.category, di.location, di.image_url, di.status, u.username as owner_username FROM donation_items di JOIN users u ON di.user_id = u.id ORDER BY di.created_at DESC")
        items = cur.fetchall()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as db_error:
        # Log explícito do erro de banco
        error_details = traceback.format_exc()
        print(f"!!! DETAILED DB ERROR fetching mural items: {db_error}\n{error_details}")
        flash("Erro ao carregar os itens do mural. Tente novamente mais tarde.", "error")
    finally:
        if conn:
            conn.close()
            
    try:
        # Passa a lista de itens para o template
        return render_template("mural.html", items=items)
    except Exception as e:
        # Log explícito do erro de renderização
        error_details = traceback.format_exc()
        print(f"!!! DETAILED ERROR rendering mural.html: {e}\n{error_details}")
        return "Erro ao carregar o mural. Verifique os logs.", 500

@app.route("/mural/adicionar", methods=("GET", "POST"))
@login_required
def add_item():
    """Rota para adicionar um novo item de doação (GET e POST)."""
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        category = request.form.get("category")
        location = request.form.get("location")
        image_url = request.form.get("image_url")
        user_id = g.user["id"]
        error = None
        conn = None

        if not title:
            error = "O título do item é obrigatório."

        if error is None:
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO donation_items (user_id, title, description, category, location, image_url, status) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (user_id, title, description, category, location, image_url, 'available') # Status inicial 'available'
                )
                conn.commit()
                cur.close()
                flash("Item adicionado para doação com sucesso!", "success")
                return redirect(url_for("mural_page"))
            except (Exception, psycopg2.DatabaseError) as db_error:
                # Log explícito do erro de banco
                error_details = traceback.format_exc()
                error = f"Erro ao salvar no banco de dados: {db_error}"
                print(f"!!! DETAILED DB ERROR adding item: {db_error}\n{error_details}")
                if conn: conn.rollback()
            finally:
                if conn:
                    conn.close()
        
        if error:
            flash(error, "error")
            # Renderiza o form novamente em caso de erro, mantendo os dados (se necessário)
            try:
                return render_template("add_item.html", form_data=request.form)
            except Exception as render_err:
                # Log explícito do erro de renderização no POST
                render_error_details = traceback.format_exc()
                print(f"!!! DETAILED ERROR rendering add_item.html on POST error: {render_err}\n{render_error_details}")
                return "Erro ao recarregar o formulário após falha. Verifique os logs.", 500

    # Método GET: apenas exibe o formulário
    try:
        print("DEBUG: Attempting to render add_item.html for GET request") # Log de depuração
        return render_template("add_item.html")
    except Exception as e:
        # Log explícito e detalhado do erro de renderização no GET
        error_details = traceback.format_exc()
        print(f"!!! DETAILED ERROR rendering add_item.html on GET: {e}\n{error_details}")
        # Retorna a mensagem genérica, mas o erro detalhado deve estar nos logs
        return "Erro ao carregar o formulário de adição. Verifique os logs.", 500

@app.route("/item/<int:item_id>")
def item_detail(item_id):
    """Rota para ver os detalhes de um item específico."""
    conn = None
    item = None
    show_interest_button = False
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Seleciona todos os detalhes do item e nome do dono
        cur.execute("SELECT di.*, u.username as owner_username FROM donation_items di JOIN users u ON di.user_id = u.id WHERE di.id = %s", (item_id,))
        item = cur.fetchone()
        
        if item is None:
            cur.close() # Fecha o cursor antes de redirecionar
            flash("Item não encontrado.", "warning")
            return redirect(url_for("mural_page"))

        # Verificar se o botão de interesse deve ser mostrado:
        # 1. Usuário logado? 2. Item está disponível? 3. Usuário logado NÃO é o dono?
        if g.user and item['status'] == 'available' and item['user_id'] != g.user['id']:
            # Adicional: Verificar se já não demonstrou interesse
            cur.execute("SELECT id FROM interests WHERE donation_item_id = %s AND user_id = %s", (item_id, g.user['id']))
            already_interested = cur.fetchone()
            if not already_interested:
                show_interest_button = True
        
        cur.close() # Fecha o cursor após todas as consultas

    except (Exception, psycopg2.DatabaseError) as db_error:
        # Log explícito do erro de banco
        error_details = traceback.format_exc()
        print(f"!!! DETAILED DB ERROR fetching item detail {item_id}: {db_error}\n{error_details}")
        flash("Erro ao carregar detalhes do item.", "error")
        # Fecha a conexão se ainda estiver aberta em caso de erro
        if conn: conn.close()
        return redirect(url_for("mural_page"))
    finally:
        # Garante que a conexão seja fechada se não houve erro antes
        if conn and not conn.closed:
            conn.close()

    try:
        return render_template("item_detail.html", item=item, show_interest_button=show_interest_button)
    except Exception as e:
        # Log explícito do erro de renderização
        error_details = traceback.format_exc()
        print(f"!!! DETAILED ERROR rendering item_detail.html for item {item_id}: {e}\n{error_details}")
        return "Erro ao carregar detalhes do item. Verifique os logs.", 500

@app.route("/item/<int:item_id>/interesse", methods=["POST"])
@login_required
def express_interest(item_id):
    """Rota para registrar interesse em um item (POST)."""
    conn = None
    error = None
    user_id = g.user['id']

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 1. Verificar se o item existe, está disponível e não pertence ao usuário
        cur.execute("SELECT user_id, status FROM donation_items WHERE id = %s", (item_id,))
        item = cur.fetchone()

        if item is None:
            error = "Item não encontrado."
        elif item['status'] != 'available':
            error = "Este item não está mais disponível para doação."
        elif item['user_id'] == user_id:
            error = "Você não pode expressar interesse no seu próprio item."
        else:
            # 2. Verificar se o usuário já expressou interesse
            cur.execute("SELECT id FROM interests WHERE donation_item_id = %s AND user_id = %s", (item_id, user_id))
            if cur.fetchone():
                error = "Você já expressou interesse neste item."
            else:
                # 3. Inserir o interesse
                cur.execute("INSERT INTO interests (donation_item_id, user_id) VALUES (%s, %s)", (item_id, user_id))
                conn.commit()
                flash("Seu interesse foi registrado com sucesso!", "success")
        
        cur.close()

    except (Exception, psycopg2.DatabaseError) as db_error:
        # Log explícito do erro de banco
        error_details = traceback.format_exc()
        print(f"!!! DETAILED DB ERROR expressing interest for item {item_id}: {db_error}\n{error_details}")
        error = "Ocorreu um erro ao registrar seu interesse. Tente novamente."
        if conn: conn.rollback()
    finally:
        if conn:
            conn.close()

    if error:
        flash(error, "error")

    # Redireciona de volta para a página de detalhes do item em qualquer caso
    return redirect(url_for("item_detail", item_id=item_id))


# --- Rota de Conexão (Exemplo - Manter como está ou remover se não for usar) --- 

@app.route("/conectar")
@login_required
def conectar_page():
    """Rota para a página de conexão com apps de fitness."""
    try:
        return render_template("conectar-apps.html")
    except Exception as e:
        # Log explícito do erro
        error_details = traceback.format_exc()
        print(f"!!! DETAILED ERROR rendering conectar-apps.html: {e}\n{error_details}")
        # Fallback para wireframes se não encontrar em templates
        try:
            print("Tentando renderizar conectar-apps.html do caminho /wireframes como fallback...")
            return render_template("../wireframes/conectar-apps.html")
        except Exception as fallback_e:
            # Log explícito do erro de fallback
            fallback_error_details = traceback.format_exc()
            print(f"!!! DETAILED FALLBACK ERROR rendering conectar-apps.html: {fallback_e}\n{fallback_error_details}")
            return "Erro ao carregar a página de conexão. Verifique os logs.", 500

# --- Bloco para execução local (não usado pelo Gunicorn no Railway) ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # debug=True é útil para desenvolvimento, mas deve ser False em produção
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "False") == "True")

