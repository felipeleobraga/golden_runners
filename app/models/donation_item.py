from app.models.db_instance import db
from datetime import datetime

class DonationItem(db.Model):
    id = db.Column(db.String(100), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(100))
    description = db.Column(db.Text)
    category = db.Column(db.String(50))
    location = db.Column(db.String(100))
    image_path = db.Column(db.String(255))
    status = db.Column(db.String(20), default="available")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
