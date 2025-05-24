from flask import Blueprint, render_template, request, redirect, url_for, flash

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Simples verificação estática para teste
        if username == 'admin' and password == '123':
            flash('Login bem-sucedido!', 'success')
            return redirect(url_for('main.mural_page'))  # ajuste conforme necessário
        else:
            flash('Credenciais inválidas.', 'error')

    return render_template('login.html')


@auth.route('/register')
def register():
    flash('Página de cadastro ainda não implementada.', 'info')
    return redirect(url_for('auth.login'))
