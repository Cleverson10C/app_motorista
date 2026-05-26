"""
Modelos do banco de dados Flask-SQLAlchemy.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import uuid

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """Modelo de usuário."""
    __tablename__ = 'users'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20))
    cpf = db.Column(db.String(14))
    city = db.Column(db.String(100))
    state = db.Column(db.String(2))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relacionamentos
    subscription = db.relationship('Subscription', backref='user', uselist=False, cascade='all, delete-orphan')
    rides = db.relationship('Ride', backref='user', lazy=True, cascade='all, delete-orphan')
    support_tickets = db.relationship('SupportTicket', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Define senha com hash."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verifica senha."""
        return check_password_hash(self.password_hash, password)
    
    def has_active_subscription(self):
        """Verifica se tem assinatura ativa."""
        if not self.subscription:
            return False
        
        # Se assinatura está ativa ou programada para cancelar, verifica o período
        if self.subscription.status in ['active', 'canceled'] and self.subscription.cancel_at_period_end:
            # Ainda tem acesso até o fim do período mesmo com cancelamento programado
            return self.subscription.current_period_end and \
                   self.subscription.current_period_end > datetime.utcnow()
        
        # Para assinaturas ativas normais
        return self.subscription.status == 'active' and \
               (not self.subscription.current_period_end or 
                self.subscription.current_period_end > datetime.utcnow())

    def get_active_plan(self):
        """Retorna o plano ativo atual (monthly, quarterly, annual) ou None."""
        if not self.has_active_subscription():
            return None
        return self.subscription.plan

    def get_effective_plan(self):
        """Retorna o plano efetivo para controle de acesso (free quando sem assinatura)."""
        return self.get_active_plan() or 'free'

    def free_trial_expires_at(self):
        """Retorna a data de expiração do plano gratuito inicial (14 dias)."""
        return self.created_at + timedelta(days=14) if self.created_at else datetime.utcnow()

    def is_free_trial_expired(self):
        """Indica se o período gratuito de 14 dias já expirou para usuários sem assinatura."""
        if self.has_active_subscription():
            return False
        return datetime.utcnow() > self.free_trial_expires_at()

    def free_trial_days_remaining(self):
        """Retorna dias restantes do gratuito inicial (0 quando expirado)."""
        if self.has_active_subscription():
            return 0
        expires_at = self.free_trial_expires_at()
        days_left = (expires_at.date() - datetime.utcnow().date()).days
        return max(days_left, 0)

    def get_monthly_ride_limit(self):
        """Retorna limite de corridas no período aplicável ao plano (None = ilimitado)."""
        plan = self.get_effective_plan()
        limits = {
            'free': 15,
            'monthly': None,
            'quarterly': None,
            'annual': None
        }
        return limits.get(plan)

    def get_monthly_ride_count(self):
        """Conta corridas dentro da janela de uso do plano atual."""
        if self.get_effective_plan() == 'free':
            # No plano gratuito, o limite é diário.
            inicio_janela = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            # Planos pagos mantêm referência mensal.
            inicio_janela = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        return Ride.query.filter(
            Ride.user_id == self.id,
            Ride.created_at >= inicio_janela
        ).count()

    def can_add_ride_this_month(self):
        """Valida se o usuário ainda pode registrar corridas no período do plano."""
        limit = self.get_monthly_ride_limit()
        used = self.get_monthly_ride_count()
        if limit is None:
            return True, used, None
        return used < limit, used, limit

    def can_access_feature(self, feature):
        """Verifica se o plano atual inclui o recurso informado."""
        plan = self.get_effective_plan()

        plan_rank = {
            'free': 0,
            'monthly': 1,
            'quarterly': 2,
            'annual': 3
        }

        feature_min_rank = {
            # Base (mensal+)
            'dashboard_complete': 1,
            'unlimited_rides': 1,
            'detailed_stats': 1,
            'interactive_charts': 1,
            'email_support': 1,
            # Trimestral+
            'report_export': 2,
            'comparative_analysis': 2,
            'priority_support': 2,
            # Anual
            'early_access_features': 3,
            'vip_support_24_7': 3
        }

        required_rank = feature_min_rank.get(feature)
        if required_rank is None:
            return False

        return plan_rank.get(plan, 0) >= required_rank
    
    def __repr__(self):
        return f'<User {self.email}>'


class Subscription(db.Model):
    """Modelo de assinatura."""
    __tablename__ = 'subscriptions'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, unique=True)
    plan = db.Column(db.String(20), nullable=False)  # monthly, annual
    status = db.Column(db.String(20), nullable=False, default='active')  # active, past_due, canceled
    current_period_end = db.Column(db.DateTime)
    cancel_at_period_end = db.Column(db.Boolean, default=False)
    canceled_at = db.Column(db.DateTime)
    gateway = db.Column(db.String(50))  # stripe, asaas, pagseguro
    gateway_subscription_id = db.Column(db.String(200))  # ID da assinatura no gateway
    gateway_payment_id = db.Column(db.String(200))  # ID do pagamento pendente no gateway
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def cancel(self):
        """Cancela a assinatura no final do período."""
        self.cancel_at_period_end = True
        self.canceled_at = datetime.utcnow()
        # NÃO muda o status para 'canceled' - mantém 'active' até o fim do período
        self.updated_at = datetime.utcnow()
    
    def cancel_immediately(self):
        """Cancela a assinatura imediatamente."""
        self.status = 'canceled'
        self.canceled_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def __repr__(self):
        return f'<Subscription {self.plan} - {self.status}>'


class Ride(db.Model):
    """Modelo de corrida."""
    __tablename__ = 'rides'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    platform = db.Column(db.String(50))  # uber, 99, indrive
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    distance_km = db.Column(db.Float)
    duration_min = db.Column(db.Integer)
    gross_amount = db.Column(db.Float)
    tip_amount = db.Column(db.Float, default=0.0)
    platform_fee = db.Column(db.Float, default=0.0)
    tolls = db.Column(db.Float, default=0.0)
    parking = db.Column(db.Float, default=0.0)
    fuel_cost = db.Column(db.Float, default=0.0)
    other_costs = db.Column(db.Float, default=0.0)
    origin = db.Column(db.Text)
    destination = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def net_revenue(self):
        """Calcula receita líquida."""
        return (
            (self.gross_amount or 0) + (self.tip_amount or 0) -
            ((self.platform_fee or 0) + (self.tolls or 0) + (self.parking or 0) +
             (self.fuel_cost or 0) + (self.other_costs or 0))
        )

    def costs(self):
        """Calcula custos totais da corrida (inclui taxa da plataforma)."""
        return (
            (self.platform_fee or 0) +
            (self.tolls or 0) +
            (self.parking or 0) +
            (self.fuel_cost or 0) +
            (self.other_costs or 0)
        )
    
    def __repr__(self):
        return f'<Ride {self.platform} - R$ {self.gross_amount}>'


class SupportTicket(db.Model):
    """Modelo de chamado de suporte."""
    __tablename__ = 'support_tickets'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False, index=True)
    level = db.Column(db.String(20), nullable=False)  # email, priority, vip
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='open')  # open, in_progress, resolved
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<SupportTicket {self.level} - {self.status}>'

