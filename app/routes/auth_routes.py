from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from app.models.db_instance import db
from app.models.user import User

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    if request.method == 'POST':
        email = request.form.get('username')  # no login.html o campo é username (mas usa email!)
        senha = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.senha_hash, senha):
            login_user(user)
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('main.home'))
        else:
            flash('Credenciais inválidas.', 'error')

    return render_template('login.html')

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('auth.login'))

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nome = request.form.get('name')
        email = request.form.get('email')
        senha = request.form.get('password')

        if User.query.filter_by(email=email).first():
            flash('Este email já está em uso.', 'error')
            return redirect(url_for('auth.register'))

        novo_user = User(
            nome=nome,
            email=email,
            senha_hash=generate_password_hash(senha)
        )
        db.session.add(novo_user)
        db.session.commit()
        flash('Conta criada com sucesso! Faça login.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('register.html')
