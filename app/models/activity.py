from app.models.user import db
from datetime import datetime

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    origem_id = db.Column(db.String(100))  # ID da atividade no Strava/Garmin
    plataforma = db.Column(db.String(50))
    distancia_km = db.Column(db.Float)
    calorias = db.Column(db.Float)
    data = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    doacao_id = db.Column(db.Integer, db.ForeignKey("donation.id"), nullable=True)
