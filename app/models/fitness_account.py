from app.models.user import db

class FitnessAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plataforma = db.Column(db.String(50))  # Ex: strava, garmin
    access_token = db.Column(db.Text)
    refresh_token = db.Column(db.Text)
    token_secret = db.Column(db.Text)
    expires_at = db.Column(db.Integer)
    
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
