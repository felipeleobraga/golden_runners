from app.models.db_instance import db
from flask_login import UserMixin
from datetime import datetime
from app.models.fitness_account import FitnessAccount

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(128))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    fitness_accounts = db.relationship(FitnessAccount, backref="user", lazy=True)
    atividades = db.relationship("Activity", backref="user", lazy=True)
    doacoes = db.relationship("Donation", backref="user", lazy=True)

    def get_id(self):
        return str(self.id)
