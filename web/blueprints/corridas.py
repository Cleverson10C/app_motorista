"""
Blueprint de Corridas - CRUD completo.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, Ride
from datetime import datetime, timedelta

corridas_bp = Blueprint('corridas', __name__, url_prefix='/corridas')
FREE_HISTORY_DAYS = 14


def _parse_float(value, default=0.0):
    """Converte valor textual para float com fallback."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _calcular_custo_combustivel(distance_km, km_por_litro, preco_litro):
    """Calcula custo de combustível em R$ para a corrida."""
    if distance_km <= 0 or km_por_litro <= 0 or preco_litro < 0:
        return 0.0
    litros_gastos = distance_km / km_por_litro
    return round(litros_gastos * preco_litro, 2)


@corridas_bp.route('/')
@login_required
def listar():
    """Lista todas as corridas do usuário."""
    if current_user.is_free_trial_expired():
        flash('Seu acesso gratuito de 14 dias expirou. Escolha um plano para continuar.', 'warning')
        return redirect(url_for('subscription.planos'))

    periodo = request.args.get('periodo')
    plataforma = request.args.get('plataforma')
    history_start = None
    history_limited = False
    if current_user.get_effective_plan() == 'free':
        history_start = datetime.utcnow() - timedelta(days=FREE_HISTORY_DAYS)
        history_limited = True

    query = Ride.query.filter_by(user_id=current_user.id)
    if history_start:
        query = query.filter(Ride.created_at >= history_start)

    if periodo:
        agora = datetime.utcnow()
        if periodo == 'hoje':
            data_inicial = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        elif periodo == 'semana':
            data_inicial = agora - timedelta(days=7)
        elif periodo == 'mes':
            data_inicial = agora - timedelta(days=30)
        else:
            data_inicial = None

        if data_inicial:
            query = query.filter(Ride.created_at >= data_inicial)

    if plataforma:
        query = query.filter_by(platform=plataforma)

    corridas = query.order_by(Ride.created_at.desc()).all()
    total_corridas_usuario = Ride.query.filter_by(user_id=current_user.id).count()
    can_delete_rides = not (current_user.get_effective_plan() == 'free' and total_corridas_usuario > 0)

    plataformas = db.session.query(Ride.platform).filter_by(user_id=current_user.id).distinct().all()
    plataformas = [p[0] for p in plataformas if p[0]]

    return render_template(
        'corridas/listar.html',
        corridas=corridas,
        plataformas=plataformas,
        periodo_selecionado=periodo,
        plataforma_selecionada=plataforma,
        can_delete_rides=can_delete_rides,
        history_limited=history_limited,
        history_limit_days=FREE_HISTORY_DAYS
    )


@corridas_bp.route('/nova', methods=['GET', 'POST'])
@login_required
def nova():
    """Adiciona nova corrida."""
    if current_user.is_free_trial_expired():
        flash('Seu acesso gratuito de 14 dias expirou. Escolha um plano para continuar.', 'warning')
        return redirect(url_for('subscription.planos'))

    can_add_ride, rides_used, rides_limit = current_user.can_add_ride_this_month()
    if not can_add_ride:
        flash(
            f'Você atingiu o limite do plano gratuito ({rides_limit} corridas por dia). Faça upgrade para continuar registrando corridas sem limite.',
            'warning'
        )
        return redirect(url_for('subscription.planos'))

    if request.method == 'POST':
        distance_km = _parse_float(request.form.get('distance_km', 0))
        km_por_litro = _parse_float(request.form.get('vehicle_km_per_l', 0))
        preco_litro = _parse_float(request.form.get('fuel_price_per_l', 0))
        fuel_cost = _calcular_custo_combustivel(distance_km, km_por_litro, preco_litro)

        if km_por_litro <= 0:
            flash('Informe o consumo do veículo (km/l) para calcular o combustível.', 'warning')
            return redirect(url_for('corridas.nova'))

        corrida = Ride(
            user_id=current_user.id,
            platform=request.form.get('platform'),
            start_time=datetime.strptime(request.form.get('start_time'), '%Y-%m-%dT%H:%M') if request.form.get('start_time') else None,
            end_time=datetime.strptime(request.form.get('end_time'), '%Y-%m-%dT%H:%M') if request.form.get('end_time') else None,
            distance_km=distance_km,
            duration_min=int(request.form.get('duration_min', 0)),
            gross_amount=float(request.form.get('gross_amount', 0)),
            tip_amount=float(request.form.get('tip_amount', 0)),
            platform_fee=float(request.form.get('platform_fee', 0)),
            tolls=float(request.form.get('tolls', 0)),
            parking=float(request.form.get('parking', 0)),
            fuel_cost=fuel_cost,
            other_costs=float(request.form.get('other_costs', 0)),
            origin=request.form.get('origin'),
            destination=request.form.get('destination')
        )

        db.session.add(corrida)
        db.session.commit()

        flash(
            f'Corrida registrada! Combustível calculado automaticamente: R$ {corrida.fuel_cost:.2f}. '
            f'Receita líquida: R$ {corrida.net_revenue():.2f}',
            'success'
        )

        if rides_limit:
            novo_total = rides_used + 1
            percentual = int((novo_total / rides_limit) * 100)
            if percentual >= 100:
                flash('Você atingiu 100% do limite diário do plano gratuito. Faça upgrade para continuar registrando corridas.', 'warning')
            elif percentual >= 90:
                flash(f'Você já usou {novo_total}/{rides_limit} corridas do plano gratuito hoje.', 'info')
            elif percentual >= 70:
                flash(f'Você está em {novo_total}/{rides_limit} corridas por dia. Considere upgrade para uso ilimitado.', 'info')

        return redirect(url_for('corridas.listar'))

    return render_template('corridas/nova.html')


@corridas_bp.route('/<corrida_id>/editar', methods=['GET', 'POST'])
@login_required
def editar(corrida_id):
    """Edita uma corrida existente."""
    if current_user.is_free_trial_expired():
        flash('Seu acesso gratuito de 14 dias expirou. Escolha um plano para continuar.', 'warning')
        return redirect(url_for('subscription.planos'))

    corrida = Ride.query.filter_by(id=corrida_id, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        distance_km = _parse_float(request.form.get('distance_km', 0))
        km_por_litro = _parse_float(request.form.get('vehicle_km_per_l', 0))
        preco_litro = _parse_float(request.form.get('fuel_price_per_l', 0))
        fuel_cost = _calcular_custo_combustivel(distance_km, km_por_litro, preco_litro)

        if km_por_litro <= 0:
            flash('Informe o consumo do veículo (km/l) para calcular o combustível.', 'warning')
            return redirect(url_for('corridas.editar', corrida_id=corrida_id))

        corrida.platform = request.form.get('platform')
        corrida.start_time = datetime.strptime(request.form.get('start_time'), '%Y-%m-%dT%H:%M') if request.form.get('start_time') else None
        corrida.end_time = datetime.strptime(request.form.get('end_time'), '%Y-%m-%dT%H:%M') if request.form.get('end_time') else None
        corrida.distance_km = distance_km
        corrida.duration_min = int(request.form.get('duration_min', 0))
        corrida.gross_amount = float(request.form.get('gross_amount', 0))
        corrida.tip_amount = float(request.form.get('tip_amount', 0))
        corrida.platform_fee = float(request.form.get('platform_fee', 0))
        corrida.tolls = float(request.form.get('tolls', 0))
        corrida.parking = float(request.form.get('parking', 0))
        corrida.fuel_cost = fuel_cost
        corrida.other_costs = float(request.form.get('other_costs', 0))
        corrida.origin = request.form.get('origin')
        corrida.destination = request.form.get('destination')

        db.session.commit()

        flash(f'Corrida atualizada! Combustível recalculado: R$ {corrida.fuel_cost:.2f}', 'success')
        return redirect(url_for('corridas.listar'))

    return render_template('corridas/editar.html', corrida=corrida)


@corridas_bp.route('/<corrida_id>/deletar', methods=['POST'])
@login_required
def deletar(corrida_id):
    """Deleta uma corrida."""
    if current_user.is_free_trial_expired():
        flash('Seu acesso gratuito de 14 dias expirou. Escolha um plano para continuar.', 'warning')
        return redirect(url_for('subscription.planos'))

    if current_user.get_effective_plan() == 'free':
        flash('No plano gratuito não é possível excluir corridas registradas.', 'warning')
        return redirect(url_for('corridas.listar'))

    corrida = Ride.query.filter_by(id=corrida_id, user_id=current_user.id).first_or_404()

    db.session.delete(corrida)
    db.session.commit()

    flash('Corrida deletada com sucesso!', 'success')
    return redirect(url_for('corridas.listar'))
