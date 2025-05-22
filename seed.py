# seed.py

from app import create_app
from app.models.donation_item import DonationItem
from app.models.user import db
from datetime import datetime
import uuid

app = create_app()

with app.app_context():
    db.drop_all()
    db.create_all()

    # Usuário exemplo
    user_id = 1x

    # Doações de exemplo
    items = [
        DonationItem(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title="Tênis de Corrida Nike",
            description="Tamanho 42, usado apenas 3 vezes. Ótimo estado.",
            category="tênis",
            location="São Paulo",
            image_path="/static/img/tenis1.jpg",
            status="available",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        ),
        DonationItem(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title="Camisa Dry Fit",
            description="Camisa dry fit tamanho M, seminova.",
            category="roupas",
            location="Rio de Janeiro",
            image_path="/static/img/camisa1.jpg",
            status="available",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
    ]

    db.session.add_all(items)
    db.session.commit()
    print("✅ Banco populado com sucesso.")
