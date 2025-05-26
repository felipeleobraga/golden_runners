from app.models.db_instance import db
from datetime import datetime

class Donation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    valor = db.Column(db.Float)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    atividades = db.relationship("Activity", backref="doacao", lazy=True)
