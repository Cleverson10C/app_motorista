# Aplicação principal Flask - App Motoristas.

from flask import Flask, render_template, redirect, url_for
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from config import Config
from models import db, User

# Inicializa extensões
login_manager = LoginManager()
migrate = Migrate()


def create_app():
    # Factory para criar a aplicação Flask.
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Inicializa extensões
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    
    # Configurações do Flask-Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor, faça login para acessar esta página.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(user_id)
    
    # Registra blueprints
    from blueprints.auth import auth_bp
    from blueprints.dashboard import dashboard_bp
    from blueprints.corridas import corridas_bp
    from blueprints.subscription import subscription_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(corridas_bp)
    app.register_blueprint(subscription_bp)
    
    # Rota principal
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.home'))
        return render_template('landing.html')
    
    # Cria tabelas do banco
    with app.app_context():
        db.create_all()
    
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
