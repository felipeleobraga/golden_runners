import os
from flask import Flask, render_template
from dotenv import load_dotenv

# Carregar variáveis de ambiente do arquivo .env (útil para desenvolvimento local)
load_dotenv()

# Importar blueprints (rotas específicas de módulos)
# Certifique-se de que o nome do arquivo e do blueprint estão corretos
# Exemplo: from donation_wall_api import donation_wall_bp

# Criar a instância da aplicação Flask
app = Flask(__name__)

# Configurar uma chave secreta (necessária para sessões, flash messages, etc.)
# É crucial que a variável SECRET_KEY esteja definida no ambiente do Railway
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "default_secret_key_for_dev_only")

# Registrar os blueprints
# app.register_blueprint(donation_wall_bp, url_prefix=\"/api/donations\")
# Adicione outros blueprints aqui (ex: para autenticação, integrações)

# --- Rotas Principais --- 

@app.route("/")
def home():
    """Rota para a página inicial."""
    # Renderiza o template HTML da página inicial
    # Certifique-se de que 'home.html' existe na pasta 'templates'
    try:
        return render_template("home.html")
    except Exception as e:
        # Log do erro pode ser útil aqui
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

# Adicione outras rotas principais aqui, se necessário
# Ex: @app.route("/dashboard"), @app.route("/profile")

# --- Bloco para execução local (não usado pelo Gunicorn no Railway) ---
if __name__ == "__main__":
    # Obtém a porta da variável de ambiente PORT (usado por algumas plataformas)
    # ou usa 5000 como padrão para desenvolvimento local
    port = int(os.environ.get("PORT", 5000))
    # Executa a aplicação em modo de debug (NÃO use debug=True em produção!)
    # 0.0.0.0 torna o servidor acessível externamente (necessário para contêineres/VMs)
    app.run(host="0.0.0.0", port=port, debug=False) # Mantenha debug=False para produção
