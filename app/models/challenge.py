from app.models.user import db
from datetime import datetime

class Challenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100))
    descricao = db.Column(db.Text)
    data_inicio = db.Column(db.DateTime)
    data_fim = db.Column(db.DateTime)
    meta_km = db.Column(db.Float)
    causa = db.Column(db.String(100))

    participantes = db.relationship("UserChallenge", backref="desafio", lazy=True)

class UserChallenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey("challenge.id"), nullable=False)
    progresso_km = db.Column(db.Float, default=0)
