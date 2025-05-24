from flask import Flask
from app.models.user import User
from app.models.fitness_account import FitnessAccount
from app.models.activity import Activity
from app.models.donation_item import DonationItem
from app.models.donation import Donation
from app.models.challenge import Challenge
from app.models.db_instance import db, login_manager

def create_app():
    app = Flask(__name__)
    app.config.from_pyfile('../config.py')

    db.init_app(app)
    login_manager.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    app.register_blueprint(main)
    app.register_blueprint(donation)
    app.register_blueprint(fitness)
    app.register_blueprint(auth)

    return app

