import os

# Ideal usar dotenv ou variáveis reais na Railway
SECRET_KEY = os.environ.get("SECRET_KEY", "dev_secret_key")
SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///dev.db")
SQLALCHEMY_TRACK_MODIFICATIONS = False
