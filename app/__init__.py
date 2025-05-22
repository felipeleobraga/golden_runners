from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from app.models.user import db
from app.models import user, donation_item  # importa os arquivos para registrar os modelos



def create_app():
    app = Flask(__name__)
    app.config.from_pyfile('../config.py')

    db.init_app(app)

    from .routes.main_routes import main
    from .routes.donation_routes import donation
    from .routes.fitness_routes import fitness
    from .user import User
    from .fitness_account import FitnessAccount
    from .activity import Activity
    from .donation_item import DonationItem
    from .donation import Donation
    from .challenge import Challenge


    app.register_blueprint(main)
    app.register_blueprint(donation)
    app.register_blueprint(fitness)

    return app



