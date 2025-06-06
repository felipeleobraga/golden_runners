from flask import Flask
from app.models.db_instance import db, login_manager

# Importações de modelos
from app.models.fitness_account import FitnessAccount
from app.models.activity import Activity
from app.models.donation_item import DonationItem
from app.models.donation import Donation
from app.models.challenge import Challenge

# Importações de blueprints
from app.routes.main_routes import main
from app.routes.donation_routes import donation
from app.routes.fitness_routes import fitness
from app.routes.auth_routes import auth


def create_app():
    app = Flask(__name__)
    app.config.from_pyfile('../config.py')

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    app.register_blueprint(main)
    app.register_blueprint(donation)
    app.register_blueprint(fitness)
    app.register_blueprint(auth)

    return app
