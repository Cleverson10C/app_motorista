"""
Blueprint de autenticação (login, cadastro, logout).
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User
from urllib.parse import urlparse

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    """Página de cadastro."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.home'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        phone = request.form.get('phone')
        cpf = request.form.get('cpf')
        city = request.form.get('city')
        state = request.form.get('state')
        
        # Validações
        if User.query.filter_by(email=email).first():
            flash('Email já cadastrado!', 'danger')
            return redirect(url_for('auth.cadastro'))
        
        # Cria usuário
        user = User(
            name=name,
            email=email,
            phone=phone,
            cpf=cpf,
            city=city,
            state=state
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Cadastro realizado com sucesso! Faça login.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/cadastro.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.home'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(email=email).first()
        
        if user is None or not user.check_password(password):
            flash('Email ou senha incorretos.', 'danger')
            return redirect(url_for('auth.login'))
        
        login_user(user, remember=remember)
        
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            next_page = url_for('dashboard.home')
        
        return redirect(next_page)
    
    return render_template('auth/login.html')


@auth_bp.route('/esqueci-senha', methods=['GET', 'POST'])
def esqueci_senha():
    """Página de recuperação de senha."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.home'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()

        if user and current_app.config.get('PASSWORD_RESET_DEMO', False):
            # Modo demonstração: reseta para senha configurada em ambiente.
            nova_senha = current_app.config.get('PASSWORD_RESET_DEMO_PASSWORD', '123456')
            user.set_password(nova_senha)
            db.session.commit()

            flash(
                f'Modo demonstração ativo: sua senha foi resetada para {nova_senha}.',
                'success'
            )
        else:
            # Mensagem genérica para não expor existência de contas.
            flash('Se o email existir, você receberá instruções para resetar sua senha.', 'info')

        return redirect(url_for('auth.login'))

    return render_template(
        'auth/esqueci_senha.html',
        reset_demo_enabled=current_app.config.get('PASSWORD_RESET_DEMO', False)
    )


@auth_bp.route('/logout')
@login_required
def logout():
    """Logout do usuário."""
    logout_user()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('index'))
