from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'main.student_login' 
login_manager.session_protection = "strong"


@login_manager.user_loader
def load_user(user_id):
    # This will be updated to use the User model from db
    from .models import User # Import here to avoid circular dependencies during initialization
    return User.query.get(int(user_id))


def create_app(config_class=None):
    app = Flask(__name__)

    # Configuration
    # Use environment variables for sensitive data or use a config file
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_fall_back_secret_key_123!')
    app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID', 'YOUR_GOOGLE_CLIENT_ID_ENV')
    app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET', 'YOUR_GOOGLE_CLIENT_SECRET_ENV')
    
    # Database Configuration
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, '..', 'classroom.db') # Place db outside app folder
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    login_manager.init_app(app)

    # Import blueprints and models here to avoid circular imports
    # Models need to be defined before db.create_all() is called if using that pattern directly.
    # However, it's better to use Flask-Migrate or CLI commands for DB creation.
    from . import models # Ensure models are imported so SQLAlchemy knows about them.

    from .routes import main_bp # Assuming routes are in main_bp
    app.register_blueprint(main_bp)
    
    # Example: For creating DB tables via a command, this would be in manage.py or run.py
    # with app.app_context():
    #     db.create_all() 
    #     # Seed initial data if needed, e.g., call a seeding function from models or services

    return app
