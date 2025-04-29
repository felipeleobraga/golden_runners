# auth.py
import os
import psycopg2
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

# Criar um Blueprint para as rotas de autenticação
auth_bp = Blueprint("auth", __name__)

def get_db_connection():
    """Estabelece conexão com o banco de dados."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL não está definida")
    return psycopg2.connect(db_url)

@auth_bp.route("/register", methods=("GET", "POST"))
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        error = None
        conn = None

        if not username:
            error = "Nome de usuário é obrigatório."
        elif not email:
            error = "Email é obrigatório."
        elif not password:
            error = "Senha é obrigatória."

        if error is None:
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                # Verificar se usuário ou email já existem
                cur.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
                if cur.fetchone() is not None:
                    error = f"Usuário {username} ou email {email} já registrado."
                else:
                    # Inserir novo usuário com senha hasheada
                    password_hash = generate_password_hash(password)
                    cur.execute(
                        "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
                        (username, email, password_hash),
                    )
                    conn.commit()
                    flash("Cadastro realizado com sucesso! Faça o login.", "success")
                    return redirect(url_for("auth.login"))
                cur.close()
            except (Exception, psycopg2.DatabaseError) as db_error:
                error = f"Erro no banco de dados: {db_error}"
            finally:
                if conn:
                    conn.close()
        
        if error:
            flash(error, "error")

    return render_template("register.html")

@auth_bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        error = None
        conn = None
        user = None

        if not username:
            error = "Nome de usuário é obrigatório."
        elif not password:
            error = "Senha é obrigatória."

        if error is None:
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("SELECT id, username, password_hash FROM users WHERE username = %s", (username,))
                user_data = cur.fetchone()
                cur.close()

                if user_data is None:
                    error = "Nome de usuário incorreto."
                elif not check_password_hash(user_data[2], password):
                    error = "Senha incorreta."
                else:
                    # Login bem-sucedido, armazenar ID do usuário na sessão
                    session.clear()
                    session["user_id"] = user_data[0]
                    session["username"] = user_data[1]
                    flash(f"Bem-vindo, {user_data[1]}!", "success")
                    # Redirecionar para o dashboard ou página inicial após login
                    # return redirect(url_for("dashboard")) # Exemplo
                    return redirect(url_for("home")) # Redireciona para a home por enquanto

            except (Exception, psycopg2.DatabaseError) as db_error:
                error = f"Erro no banco de dados: {db_error}"
            finally:
                if conn:
                    conn.close()

        if error:
            flash(error, "error")

    return render_template("login.html")

@auth_bp.route("/logout")
def logout():
    """Limpa a sessão do usuário (logout)."""
    session.clear()
    flash("Você saiu da sua conta.", "info")
    return redirect(url_for("home"))

# Adicionar rota para perfil do usuário (@auth_bp.route("/profile")) aqui depois

