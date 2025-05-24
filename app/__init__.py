from flask import Flask
from app.models.db_instance import db
from app.models.user import User
from app.models.fitness_account import FitnessAccount
from app.models.activity import Activity
from app.models.donation_item import DonationItem
from app.models.donation import Donation
from app.models.challenge import Challenge

def create_app():
    app = Flask(__name__)
    app.config.from_pyfile('../config.py')

    db.init_app(app)

    from routes.main_routes import main
    from routes.donation_routes import donation
    from routes.fitness_routes import fitness

    app.register_blueprint(main)
    app.register_blueprint(donation)
    app.register_blueprint(fitness)

    return app
