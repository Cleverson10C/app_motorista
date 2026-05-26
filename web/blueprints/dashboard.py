"""
Blueprint do Dashboard - visualizações e estatísticas.
"""
from flask import Blueprint, render_template, request, current_app, Response, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import Ride
from datetime import datetime, timedelta
import json
import csv
import io

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')
FREE_HISTORY_DAYS = 14


def _get_history_start_for_user():
    """Retorna data mínima de histórico para o plano atual."""
    if current_user.get_effective_plan() == 'free':
        return datetime.utcnow() - timedelta(days=FREE_HISTORY_DAYS)
    return None


def formatar_tempo_humano(total_minutos):
    """Converte minutos para formato amigável (Xh Ymin)."""
    minutos = int(round(total_minutos or 0))
    if minutos < 60:
        return f"{minutos} min"

    horas = minutos // 60
    restante = minutos % 60
    if restante == 0:
        return f"{horas}h"
    return f"{horas}h {restante}min"


@dashboard_bp.route('/')
@login_required
def home():
    """Página principal do dashboard."""
    if current_user.is_free_trial_expired():
        flash('Seu acesso gratuito de 14 dias expirou. Escolha um plano para continuar.', 'warning')
        return redirect(url_for('subscription.planos'))

    history_start = _get_history_start_for_user()
    is_free_plan = current_user.get_effective_plan() == 'free'
    free_trial_days_left = current_user.free_trial_days_remaining() if is_free_plan else None
    free_trial_expires_at = (
        current_user.free_trial_expires_at().strftime('%d/%m/%Y')
        if is_free_plan else None
    )
    rides_limit = current_user.get_monthly_ride_limit()
    rides_used = current_user.get_monthly_ride_count() if rides_limit else None
    rides_percent = None
    if rides_limit:
        rides_percent = min(int((rides_used / rides_limit) * 100), 100)

    # Estatísticas gerais
    query_base = Ride.query.filter_by(user_id=current_user.id)
    if history_start:
        query_base = query_base.filter(Ride.created_at >= history_start)

    total_corridas = rides_used if is_free_plan and rides_used is not None else query_base.count()
    corridas = query_base.all()
    
    receita_total = sum(c.net_revenue() for c in corridas)
    distancia_total = sum(c.distance_km or 0 for c in corridas)
    tempo_total_min = sum(c.duration_min or 0 for c in corridas)
    
    # Estatísticas do mês
    inicio_mes = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    corridas_mes = Ride.query.filter(
        Ride.user_id == current_user.id,
        Ride.created_at >= inicio_mes
    ).all()
    
    receita_mes = sum(c.net_revenue() for c in corridas_mes)
    corridas_mes_count = len(corridas_mes)
    
    # Dados para gráficos - últimos 7 dias
    dados_graficos = preparar_dados_graficos(current_user.id, history_start)
    
    return render_template('dashboard/home.html',
                         total_corridas=total_corridas,
                         receita_total=receita_total,
                         distancia_total=distancia_total,
                         tempo_total_formatado=formatar_tempo_humano(tempo_total_min),
                         receita_mes=receita_mes,
                         corridas_mes=corridas_mes_count,
                         dados_graficos=dados_graficos,
                         rides_limit=rides_limit,
                         rides_used=rides_used,
                         rides_percent=rides_percent,
                         free_trial_days_left=free_trial_days_left,
                         free_trial_expires_at=free_trial_expires_at,
                         history_limited=bool(history_start),
                         history_limit_days=FREE_HISTORY_DAYS)


@dashboard_bp.route('/estatisticas')
@login_required
def estatisticas():
    """Página de estatísticas detalhadas."""
    if current_user.is_free_trial_expired():
        flash('Seu acesso gratuito de 14 dias expirou. Escolha um plano para continuar.', 'warning')
        return redirect(url_for('subscription.planos'))

    history_start = _get_history_start_for_user()
    history_limited = bool(history_start)

    periodo = request.args.get('periodo', '30')
    if history_limited and periodo == 'all':
        periodo = str(FREE_HISTORY_DAYS)
    platform = request.args.get('platform', 'all')
    corridas, data_inicial = consultar_corridas_filtradas(
        current_user.id,
        periodo,
        platform,
        history_start
    )
    
    # Calcula estatísticas detalhadas
    stats = calcular_estatisticas_detalhadas(corridas)
    
    # Dados para gráficos
    labels_plataformas, dados_plataformas = preparar_grafico_plataformas(corridas)
    labels_dias, dados_dias = preparar_grafico_dia_semana(corridas, data_inicial)

    can_export = current_user.can_access_feature('report_export')
    can_compare = current_user.can_access_feature('comparative_analysis')
    can_advanced = current_user.can_access_feature('early_access_features')

    comparativo = calcular_analise_comparativa(periodo, platform) if can_compare else None
    insights_avancados = calcular_insights_avancados(corridas, data_inicial) if can_advanced else None
    labels_custos, dados_custos = preparar_grafico_custos(corridas) if can_compare else ([], [])
    labels_horarios, dados_horarios = preparar_grafico_horarios(corridas) if can_advanced else ([], [])
    
    return render_template('dashboard/estatisticas.html',
                         stats=stats,
                         tempo_total_formatado=formatar_tempo_humano(stats.get('tempo_total', 0)),
                         periodo=periodo,
                         platform=platform,
                         history_limited=history_limited,
                         history_limit_days=FREE_HISTORY_DAYS,
                         effective_plan=current_user.get_effective_plan(),
                         labels_plataformas=labels_plataformas,
                         dados_plataformas=dados_plataformas,
                         labels_dias=labels_dias,
                         dados_dias=dados_dias,
                         can_export=can_export,
                         can_compare=can_compare,
                         can_advanced=can_advanced,
                         comparativo=comparativo,
                         insights_avancados=insights_avancados,
                         labels_custos=labels_custos,
                         dados_custos=dados_custos,
                         labels_horarios=labels_horarios,
                         dados_horarios=dados_horarios)


@dashboard_bp.route('/estatisticas/exportar')
@login_required
def exportar_estatisticas():
    """Exporta relatório CSV (recurso trimestral+)."""
    if current_user.is_free_trial_expired():
        flash('Seu acesso gratuito de 14 dias expirou. Escolha um plano para continuar.', 'warning')
        return redirect(url_for('subscription.planos'))


    if not current_user.can_access_feature('report_export'):
        flash('Exportação de relatórios disponível a partir do plano trimestral.', 'warning')
        return redirect(url_for('dashboard.estatisticas'))

    def _fmt_num(valor, casas=2):
        """Formata número em padrão pt-BR para CSV."""
        return f"{valor:.{casas}f}".replace('.', ',')

    periodo = request.args.get('periodo', '30')
    platform = request.args.get('platform', 'all')
    corridas, _ = consultar_corridas_filtradas(current_user.id, periodo, platform)
    stats = calcular_estatisticas_detalhadas(corridas)

    csv_buffer = io.StringIO(newline='')
    writer = csv.writer(csv_buffer, delimiter=';', lineterminator='\n')
    writer.writerow(['sep=;'])  # Ajuda o Excel a interpretar delimitador corretamente.
    writer.writerow(['Relatório App Motoristas'])
    writer.writerow(['Usuário', current_user.email])
    writer.writerow(['Período', periodo])
    writer.writerow(['Plataforma', platform])
    writer.writerow([])
    writer.writerow(['Métrica', 'Valor'])
    writer.writerow(['Total de corridas', stats['total_corridas']])
    writer.writerow(['Receita bruta total (R$)', _fmt_num(stats['receita_bruta_total'])])
    writer.writerow(['Receita líquida total (R$)', _fmt_num(stats['receita_liquida_total'])])
    writer.writerow(['Custos totais (R$)', _fmt_num(stats['custos_total'])])
    writer.writerow(['Distância total (km)', _fmt_num(stats['distancia_total'], 1)])
    writer.writerow(['Tempo total (min)', _fmt_num(stats['tempo_total'], 0)])
    writer.writerow([])
    writer.writerow(['Plataforma', 'Corridas', 'Receita Bruta (R$)', 'Gorjetas (R$)', 'Taxas (R$)', 'Custos (R$)', 'Receita Líquida (R$)'])
    for item in stats['por_plataforma']:
        writer.writerow([
            item['platform'],
            item['total'],
            _fmt_num(item['receita_bruta']),
            _fmt_num(item['gorjetas']),
            _fmt_num(item['taxas']),
            _fmt_num(item['custos']),
            _fmt_num(item['receita_liquida'])
        ])

    filename = f"relatorio_{current_user.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    csv_content = '\ufeff' + csv_buffer.getvalue()  # BOM UTF-8 para evitar problemas de acentuação no Excel.
    return Response(
        csv_content,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@dashboard_bp.route('/insights-avancados')
@login_required
def insights_avancados():
    """Retorna insights avançados (acesso anual)."""
    if current_user.is_free_trial_expired():
        return jsonify({'error': 'Seu acesso gratuito expirou. Escolha um plano para continuar.'}), 403

    if not current_user.can_access_feature('early_access_features'):
        return jsonify({'error': 'Recurso disponível apenas no plano anual.'}), 403

    corridas, data_inicial = consultar_corridas_filtradas(current_user.id, '30', 'all')
    dados = calcular_insights_avancados(corridas, data_inicial)
    return jsonify({'status': 'ok', 'data': dados})


def consultar_corridas_filtradas(user_id, periodo, platform, history_start=None):
    """Consulta corridas com os filtros de período e plataforma."""
    agora = datetime.utcnow()
    if periodo == 'all':
        data_inicial = datetime(2000, 1, 1)
    else:
        dias = int(periodo)
        data_inicial = agora - timedelta(days=dias)
    if history_start and data_inicial < history_start:
        data_inicial = history_start

    query = Ride.query.filter(
        Ride.user_id == user_id,
        Ride.created_at >= data_inicial
    )

    if platform != 'all':
        query = query.filter(Ride.platform == platform)

    return query.all(), data_inicial


def preparar_dados_graficos(user_id, history_start=None):
    """Prepara dados para gráficos (últimos 7 dias)."""
    agora = datetime.utcnow()
    data_inicial = agora - timedelta(days=7)
    if history_start and data_inicial < history_start:
        data_inicial = history_start
    
    corridas = Ride.query.filter(
        Ride.user_id == user_id,
        Ride.created_at >= data_inicial
    ).all()
    
    # Agrupa por dia
    dados_por_dia = {}
    for corrida in corridas:
        dia = corrida.created_at.date().isoformat()
        if dia not in dados_por_dia:
            dados_por_dia[dia] = {
                'receita': 0,
                'corridas': 0,
                'distancia': 0
            }
        
        dados_por_dia[dia]['receita'] += corrida.net_revenue()
        dados_por_dia[dia]['corridas'] += 1
        dados_por_dia[dia]['distancia'] += corrida.distance_km or 0
    
    # Formata para Chart.js
    labels = []
    receitas = []
    corridas_count = []
    distancias = []
    
    for i in range(7):
        dia = (agora - timedelta(days=6-i)).date().isoformat()
        labels.append(dia)
        
        if dia in dados_por_dia:
            receitas.append(round(dados_por_dia[dia]['receita'], 2))
            corridas_count.append(dados_por_dia[dia]['corridas'])
            distancias.append(round(dados_por_dia[dia]['distancia'], 2))
        else:
            receitas.append(0)
            corridas_count.append(0)
            distancias.append(0)
    
    return {
        'labels': json.dumps(labels),
        'receitas': json.dumps(receitas),
        'corridas': json.dumps(corridas_count),
        'distancias': json.dumps(distancias)
    }


def calcular_estatisticas_detalhadas(corridas):
    """Calcula estatísticas detalhadas para a página de estatísticas."""
    if not corridas:
        return {
            'total_corridas': 0,
            'distancia_total': 0,
            'tempo_total': 0,
            'ticket_medio': 0,
            'por_plataforma': [],
            'receita_bruta_total': 0,
            'gorjetas_total': 0,
            'taxas_total': 0,
            'custos_total': 0,
            'receita_liquida_total': 0,
            'distancia_media': 0,
            'tempo_medio': 0,
            'receita_media': 0,
            'custo_medio': 0,
            'lucro_medio': 0,
            'corridas_por_dia': 0,
            'percentual_taxa': 0,
            'percentual_custos': 0,
            'margem_liquida': 0,
            'percentual_gorjetas': 0,
            'custo_por_km': 0,
            'receita_por_km': 0
        }
    
    # Totais
    receita_bruta_total = sum((c.gross_amount or 0) + (c.tip_amount or 0) for c in corridas)
    gorjetas_total = sum(c.tip_amount or 0 for c in corridas)
    taxas_total = sum(c.platform_fee or 0 for c in corridas)
    custos_total = sum(c.costs() for c in corridas)
    receita_liquida_total = sum(c.net_revenue() for c in corridas)
    distancia_total = sum(c.distance_km or 0 for c in corridas)
    tempo_total = sum(c.duration_min or 0 for c in corridas)
    
    # Médias
    n = len(corridas)
    distancia_media = distancia_total / n
    tempo_medio = tempo_total / n
    receita_media = receita_liquida_total / n
    custo_medio = custos_total / n
    lucro_medio = receita_media - custo_medio
    
    # Dias únicos
    dias_unicos = len(set(c.created_at.date() for c in corridas))
    corridas_por_dia = n / dias_unicos if dias_unicos > 0 else 0
    
    # Percentuais
    percentual_taxa = (taxas_total / receita_bruta_total * 100) if receita_bruta_total > 0 else 0
    percentual_custos = (custos_total / receita_bruta_total * 100) if receita_bruta_total > 0 else 0
    margem_liquida = (receita_liquida_total / receita_bruta_total * 100) if receita_bruta_total > 0 else 0
    percentual_gorjetas = (gorjetas_total / receita_bruta_total * 100) if receita_bruta_total > 0 else 0
    
    # Por km
    custo_por_km = custos_total / distancia_total if distancia_total > 0 else 0
    receita_por_km = receita_bruta_total / distancia_total if distancia_total > 0 else 0
    
    # Por plataforma
    por_plataforma = {}
    for c in corridas:
        plat = c.platform or 'Outro'
        if plat not in por_plataforma:
            por_plataforma[plat] = {
                'platform': plat,
                'total': 0,
                'receita_bruta': 0,
                'gorjetas': 0,
                'taxas': 0,
                'custos': 0,
                'receita_liquida': 0
            }
        
        por_plataforma[plat]['total'] += 1
        por_plataforma[plat]['receita_bruta'] += (c.gross_amount or 0)
        por_plataforma[plat]['gorjetas'] += (c.tip_amount or 0)
        por_plataforma[plat]['taxas'] += (c.platform_fee or 0)
        por_plataforma[plat]['custos'] += c.costs()
        por_plataforma[plat]['receita_liquida'] += c.net_revenue()
    
    return {
        'total_corridas': n,
        'distancia_total': round(distancia_total, 1),
        'tempo_total': round(tempo_total, 0),
        'ticket_medio': round(receita_bruta_total / n, 2),
        'por_plataforma': list(por_plataforma.values()),
        'receita_bruta_total': round(receita_bruta_total, 2),
        'gorjetas_total': round(gorjetas_total, 2),
        'taxas_total': round(taxas_total, 2),
        'custos_total': round(custos_total, 2),
        'receita_liquida_total': round(receita_liquida_total, 2),
        'distancia_media': round(distancia_media, 1),
        'tempo_medio': round(tempo_medio, 0),
        'receita_media': round(receita_media, 2),
        'custo_medio': round(custo_medio, 2),
        'lucro_medio': round(lucro_medio, 2),
        'corridas_por_dia': round(corridas_por_dia, 1),
        'percentual_taxa': round(percentual_taxa, 1),
        'percentual_custos': round(percentual_custos, 1),
        'margem_liquida': round(margem_liquida, 1),
        'percentual_gorjetas': round(percentual_gorjetas, 1),
        'custo_por_km': round(custo_por_km, 2),
        'receita_por_km': round(receita_por_km, 2)
    }


def preparar_grafico_plataformas(corridas):
    """Prepara dados para gráfico de receita por plataforma."""
    plataformas = {}
    
    for c in corridas:
        plat = c.platform or 'Outro'
        if plat not in plataformas:
            plataformas[plat] = 0
        plataformas[plat] += c.net_revenue()
    
    labels = list(plataformas.keys())
    dados = [round(v, 2) for v in plataformas.values()]
    
    return labels, dados


def preparar_grafico_dia_semana(corridas, data_inicial):
    """Prepara dados para gráfico de média de corridas por dia da semana."""
    dias_semana = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']

    # Contagem de corridas por dia da semana no período filtrado
    contagem_corridas = [0] * 7
    for c in corridas:
        dia_semana = c.created_at.weekday()  # 0=Segunda, 6=Domingo
        contagem_corridas[dia_semana] += 1

    # Quantidade de dias de cada dia da semana no período (inclui dias sem corrida)
    fim_periodo = datetime.utcnow().date()
    if corridas and data_inicial.year <= 2000:
        inicio_periodo = min(c.created_at.date() for c in corridas)
    else:
        inicio_periodo = data_inicial.date()

    dias_no_periodo = [0] * 7
    dia_atual = inicio_periodo
    while dia_atual <= fim_periodo:
        dias_no_periodo[dia_atual.weekday()] += 1
        dia_atual += timedelta(days=1)

    medias = []
    for i in range(7):
        if dias_no_periodo[i] > 0:
            medias.append(round(contagem_corridas[i] / dias_no_periodo[i], 2))
        else:
            medias.append(0)

    return dias_semana, medias


def preparar_grafico_custos(corridas):
    """Prepara dados para gráfico de distribuição de custos (trimestral+)."""
    totais = {
        'Taxa da Plataforma': 0.0,
        'Combustível': 0.0,
        'Pedágios': 0.0,
        'Estacionamento': 0.0,
        'Outros': 0.0
    }

    for c in corridas:
        totais['Taxa da Plataforma'] += c.platform_fee or 0
        totais['Combustível'] += c.fuel_cost or 0
        totais['Pedágios'] += c.tolls or 0
        totais['Estacionamento'] += c.parking or 0
        totais['Outros'] += c.other_costs or 0

    labels = []
    dados = []
    for nome, valor in totais.items():
        if valor > 0:
            labels.append(nome)
            dados.append(round(valor, 2))

    if not labels:
        labels = list(totais.keys())
        dados = [0, 0, 0, 0, 0]

    return labels, dados


def preparar_grafico_horarios(corridas):
    """Prepara dados para gráfico de receita líquida por faixa de horário (anual)."""
    faixas = ['00h-06h', '06h-12h', '12h-18h', '18h-24h']
    receita_por_faixa = [0.0, 0.0, 0.0, 0.0]

    for c in corridas:
        referencia = c.start_time or c.created_at
        if not referencia:
            continue

        hora = referencia.hour
        if 0 <= hora < 6:
            idx = 0
        elif 6 <= hora < 12:
            idx = 1
        elif 12 <= hora < 18:
            idx = 2
        else:
            idx = 3

        receita_por_faixa[idx] += c.net_revenue()

    return faixas, [round(v, 2) for v in receita_por_faixa]


def calcular_analise_comparativa(periodo, platform):
    """Compara o período atual com o período imediatamente anterior (trimestral+)."""
    agora = datetime.utcnow()
    if periodo == 'all':
        return None

    dias = int(periodo)
    atual_inicio = agora - timedelta(days=dias)
    anterior_inicio = atual_inicio - timedelta(days=dias)

    query_atual = Ride.query.filter(
        Ride.user_id == current_user.id,
        Ride.created_at >= atual_inicio,
        Ride.created_at < agora
    )
    query_anterior = Ride.query.filter(
        Ride.user_id == current_user.id,
        Ride.created_at >= anterior_inicio,
        Ride.created_at < atual_inicio
    )

    if platform != 'all':
        query_atual = query_atual.filter(Ride.platform == platform)
        query_anterior = query_anterior.filter(Ride.platform == platform)

    corridas_atual = query_atual.all()
    corridas_anterior = query_anterior.all()

    receita_atual = sum(c.net_revenue() for c in corridas_atual)
    receita_anterior = sum(c.net_revenue() for c in corridas_anterior)
    qtd_atual = len(corridas_atual)
    qtd_anterior = len(corridas_anterior)

    def variacao_percentual(atual, anterior):
        if anterior == 0:
            return 100.0 if atual > 0 else 0.0
        return ((atual - anterior) / anterior) * 100

    return {
        'dias_comparados': dias,
        'receita_atual': round(receita_atual, 2),
        'receita_anterior': round(receita_anterior, 2),
        'receita_variacao_percentual': round(variacao_percentual(receita_atual, receita_anterior), 1),
        'corridas_atual': qtd_atual,
        'corridas_anterior': qtd_anterior,
        'corridas_variacao_percentual': round(variacao_percentual(qtd_atual, qtd_anterior), 1)
    }


def calcular_insights_avancados(corridas, data_inicial):
    """Gera insights de early-access para plano anual."""
    if not corridas:
        return {
            'projecao_receita_30_dias': 0,
            'dia_mais_lucrativo': '-',
            'receita_media_por_corrida': 0
        }

    receita_total = sum(c.net_revenue() for c in corridas)
    dias_no_periodo = max((datetime.utcnow().date() - data_inicial.date()).days, 1)
    receita_media_diaria = receita_total / dias_no_periodo

    receita_por_dia = {}
    for corrida in corridas:
        nome_dia = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'][corrida.created_at.weekday()]
        receita_por_dia[nome_dia] = receita_por_dia.get(nome_dia, 0) + corrida.net_revenue()

    dia_mais_lucrativo = max(receita_por_dia, key=receita_por_dia.get) if receita_por_dia else '-'

    return {
        'projecao_receita_30_dias': round(receita_media_diaria * 30, 2),
        'dia_mais_lucrativo': dia_mais_lucrativo,
        'receita_media_por_corrida': round(receita_total / len(corridas), 2)
    }



