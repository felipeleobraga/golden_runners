from app import create_app
from app.models.user import db

app = create_app()

with app.app_context():
    db.create_all()
    print("✅ Banco inicializado com sucesso.")
