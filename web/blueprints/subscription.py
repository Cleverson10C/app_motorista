"""Blueprint de Assinaturas - Planos, ativação e cancelamento."""
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from models import db, Subscription, SupportTicket
from datetime import datetime, timedelta
import requests
import qrcode
import io
import base64
import crcmod
import logging

subscription_bp = Blueprint('subscription', __name__, url_prefix='/assinatura')
logger = logging.getLogger(__name__)


def obter_nivel_suporte_disponivel(user):
    """Retorna o maior nível de suporte permitido pelo plano atual."""
    if user.can_access_feature('vip_support_24_7'):
        return 'vip'
    if user.can_access_feature('priority_support'):
        return 'priority'
    if user.can_access_feature('email_support'):
        return 'email'
    return None

def calcular_crc16(payload):
    """Calcula o CRC16 CCITT para validação do código PIX."""
    crc16 = crcmod.predefined.mkCrcFun('xmodem')
    return format(crc16(payload.encode('utf-8')), '04X')


def criar_cliente_asaas(user):
    """Cria um cliente no Asaas."""
    if not current_app.config.get('ASAAS_API_KEY'):
        return None
    
    headers = {
        'access_token': current_app.config['ASAAS_API_KEY'],
        'Content-Type': 'application/json'
    }
    
    data = {
        'name': user.name,
        'email': user.email,
        'cpfCnpj': user.cpf if user.cpf else None,
        'mobilePhone': user.phone if user.phone else None
    }
    
    try:
        response = requests.post(
            f"{current_app.config['ASAAS_API_URL']}/customers",
            headers=headers,
            json=data
        )
        
        if response.status_code == 200:
            return response.json()['id']
        else:
            logger.error("Erro ao criar cliente Asaas: %s", response.text)
            return None
    except Exception as e:
        logger.exception("Erro na requisição Asaas: %s", str(e))
        return None


def criar_cobranca_asaas(customer_id, plano, metodo='PIX'):
    """Cria uma cobrança no Asaas."""
    if not current_app.config.get('ASAAS_API_KEY'):
        return None
    
    headers = {
        'access_token': current_app.config['ASAAS_API_KEY'],
        'Content-Type': 'application/json'
    }
    
    valores = {
        'monthly': 11.90,
        'quarterly': 34.90,
        'annual': 99.90
    }
    
    descricoes = {
        'monthly': 'Assinatura Mensal - App Motoristas',
        'quarterly': 'Assinatura Trimestral - App Motoristas',
        'annual': 'Assinatura Anual - App Motoristas'
    }
    
    data = {
        'customer': customer_id,
        'billingType': metodo,  # PIX, CREDIT_CARD, BOLETO
        'value': valores[plano],
        'dueDate': datetime.now().strftime('%Y-%m-%d'),
        'description': descricoes[plano]
    }
    
    try:
        response = requests.post(
            f"{current_app.config['ASAAS_API_URL']}/payments",
            headers=headers,
            json=data
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error("Erro ao criar cobrança Asaas: %s", response.text)
            return None
    except Exception as e:
        logger.exception("Erro na requisição Asaas: %s", str(e))
        return None


def verificar_pagamento_asaas(payment_id):
    """Verifica status de um pagamento no Asaas."""
    if not current_app.config.get('ASAAS_API_KEY'):
        return None
    
    headers = {
        'access_token': current_app.config['ASAAS_API_KEY'],
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.get(
            f"{current_app.config['ASAAS_API_URL']}/payments/{payment_id}",
            headers=headers
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        logger.exception("Erro ao verificar pagamento: %s", str(e))
        return None


@subscription_bp.route('/planos')
@login_required
def planos():
    """Página de planos de assinatura."""
    # Verifica se já tem assinatura ativa
    tem_assinatura = current_user.has_active_subscription()
    active_plan = current_user.get_active_plan() or 'free'
    rides_limit = current_user.get_monthly_ride_limit()
    rides_used = current_user.get_monthly_ride_count() if rides_limit else None

    return render_template(
        'subscription/planos.html',
        tem_assinatura=tem_assinatura,
        active_plan=active_plan,
        rides_limit=rides_limit,
        rides_used=rides_used
    )


@subscription_bp.route('/assinar/<plano>', methods=['GET', 'POST'])
@login_required
def assinar(plano):
    """Redireciona para página de pagamento do plano escolhido."""
    planos_validos = ['monthly', 'quarterly', 'annual']
    if plano not in planos_validos:
        flash('Plano inválido!', 'danger')
        return redirect(url_for('subscription.planos'))
    
    # Verifica se já tem assinatura ativa
    if current_user.subscription and current_user.subscription.status == 'active':
        flash('Você já possui uma assinatura ativa!', 'warning')
        return redirect(url_for('subscription.gerenciar'))
    
    # Redireciona para página de pagamento
    return redirect(url_for('subscription.pagamento', plano=plano))


@subscription_bp.route('/pagamento/<plano>')
@login_required
def pagamento(plano):
    """Página de seleção de método de pagamento."""
    planos_validos = ['monthly', 'quarterly', 'annual']
    if plano not in planos_validos:
        flash('Plano inválido!', 'danger')
        return redirect(url_for('subscription.planos'))
    
    # Verifica se já tem assinatura ativa
    if current_user.subscription and current_user.subscription.status == 'active':
        flash('Você já possui uma assinatura ativa!', 'warning')
        return redirect(url_for('subscription.gerenciar'))
    
    # Informações do plano
    planos_info = {
        'monthly': {'nome': 'Mensal', 'preco': 11.90, 'periodo': 'mês'},
        'quarterly': {'nome': 'Trimestral', 'preco': 34.90, 'periodo': 'trimestre'},
        'annual': {'nome': 'Anual', 'preco': 99.90, 'periodo': 'ano'}
    }
    
    info_plano = planos_info[plano]
    info_plano['id'] = plano
    
    return render_template('subscription/pagamento.html', plano=info_plano)


@subscription_bp.route('/processar-pagamento', methods=['POST'])
@login_required
def processar_pagamento():
    """Processa o pagamento e ativa a assinatura."""
    plano = request.form.get('plano')
    metodo_pagamento = request.form.get('metodo_pagamento')
    
    planos_validos = ['monthly', 'quarterly', 'annual']
    if plano not in planos_validos:
        flash('Plano inválido!', 'danger')
        return redirect(url_for('subscription.planos'))
    
    metodos_validos = ['credit_card', 'debit_card', 'pix']
    if metodo_pagamento not in metodos_validos:
        flash('Método de pagamento inválido!', 'danger')
        return redirect(url_for('subscription.pagamento', plano=plano))
    
    # Verifica se já tem assinatura ativa
    if current_user.subscription and current_user.subscription.status == 'active':
        flash('Você já possui uma assinatura ativa!', 'warning')
        return redirect(url_for('subscription.gerenciar'))
    
    # Processa pagamento baseado no método
    if metodo_pagamento == 'pix':
        # Para PIX, gera código e aguarda confirmação
        return redirect(url_for('subscription.pix_pagamento', plano=plano))
    
    # Para cartão (crédito ou débito)
    numero_cartao = request.form.get('numero_cartao', '').replace(' ', '')
    nome_cartao = request.form.get('nome_cartao')
    validade = request.form.get('validade')
    cvv = request.form.get('cvv')
    
    # Validações básicas
    if not all([numero_cartao, nome_cartao, validade, cvv]):
        flash('Preencha todos os dados do cartão!', 'danger')
        return redirect(url_for('subscription.pagamento', plano=plano))
    
    if len(numero_cartao) < 13 or len(cvv) < 3:
        flash('Dados do cartão inválidos!', 'danger')
        return redirect(url_for('subscription.pagamento', plano=plano))
    
    # Aqui integraria com gateway real (Stripe, Asaas, etc)
    # Por enquanto, simula pagamento aprovado
    
    # Calcula data de fim do período
    dias_map = {
        'monthly': 30,
        'quarterly': 90,
        'annual': 365
    }
    periodo_fim = datetime.utcnow() + timedelta(days=dias_map[plano])
    
    # Cria ou atualiza assinatura
    if current_user.subscription:
        subscription = current_user.subscription
        subscription.plan = plano
        subscription.status = 'active'
        subscription.current_period_end = periodo_fim
        subscription.cancel_at_period_end = False
        subscription.canceled_at = None
        subscription.gateway = 'simulacao'
        subscription.updated_at = datetime.utcnow()
    else:
        subscription = Subscription(
            user_id=current_user.id,
            plan=plano,
            status='active',
            current_period_end=periodo_fim,
            gateway='simulacao'
        )
        db.session.add(subscription)
    
    db.session.commit()
    
    flash(f'Pagamento aprovado! Assinatura {plano} ativada com sucesso!', 'success')
    return redirect(url_for('dashboard.home'))


@subscription_bp.route('/pix/<plano>')
@login_required
def pix_pagamento(plano):
    """Página de pagamento via PIX usando Asaas."""
    planos_validos = ['monthly', 'quarterly', 'annual']
    if plano not in planos_validos:
        flash('Plano inválido!', 'danger')
        return redirect(url_for('subscription.planos'))
    
    # Informações do plano
    planos_info = {
        'monthly': {'nome': 'Mensal', 'preco': 11.90},
        'quarterly': {'nome': 'Trimestral', 'preco': 34.90},
        'annual': {'nome': 'Anual', 'preco': 99.90}
    }
    
    info_plano = planos_info[plano]
    info_plano['id'] = plano
    
    # Se tiver API do Asaas configurada, usa integração real
    if current_app.config.get('ASAAS_API_KEY'):
        from flask import session
        
        # Verifica se já existe uma cobrança pendente para este usuário
        payment_id = session.get('asaas_payment_id')
        plano_sessao = session.get('plano_selecionado')
        
        # Se já tem cobrança pendente do mesmo plano, reutiliza
        if payment_id and plano_sessao == plano:
            pagamento = verificar_pagamento_asaas(payment_id)
            
            if pagamento and pagamento.get('status') in ['PENDING', 'CONFIRMED']:
                # Usa a cobrança existente
                codigo_pix = pagamento.get('pixCopyAndPaste', '')
                qr_code_img = pagamento.get('pixQrCode', '')
                
                return render_template('subscription/pix.html', 
                                     plano=info_plano, 
                                     codigo_pix=codigo_pix,
                                     qr_code_img=qr_code_img,
                                     usando_asaas=True)
        
        # Cria nova cobrança apenas se não existir ou expirou
        customer_id = criar_cliente_asaas(current_user)
        
        if customer_id:
            # Cria cobrança PIX
            cobranca = criar_cobranca_asaas(customer_id, plano, 'PIX')
            
            if cobranca and 'pixQrCode' in cobranca:
                # Usa QR Code do Asaas
                codigo_pix = cobranca['pixCopyAndPaste']
                qr_code_img = cobranca['pixQrCode']  # Asaas já retorna base64
                
                # Salva ID da cobrança na sessão para verificação posterior
                session['asaas_payment_id'] = cobranca['id']
                session['plano_selecionado'] = plano
                
                return render_template('subscription/pix.html', 
                                     plano=info_plano, 
                                     codigo_pix=codigo_pix,
                                     qr_code_img=qr_code_img,
                                     usando_asaas=True)
    
    # Fallback: Gera QR Code manual (modo demonstração)
    chave_pix = 'clevercleverpassos@gmail.com'
    valor = f"{info_plano['preco']:.2f}"
    
    # Merchant Account Information (ID 26)
    merchant_account = f"0014br.gov.bcb.pix01{len(chave_pix):02d}{chave_pix}"
    
    # Nome do comerciante
    nome_comerciante = 'App Motorista'
    
    # Cidade
    cidade = 'Curitiba'
    
    # Monta payload sem CRC
    payload_sem_crc = (
        '00020101'  # Payload Format Indicator
        '26' + f"{len(merchant_account):02d}" + merchant_account +  # Merchant Account
        '52040000'  # Merchant Category Code
        '5303986'   # Currency Code (BRL)
        '54' + f"{len(valor):02d}" + valor +  # Transaction Amount
        '5802BR'    # Country Code
        '59' + f"{len(nome_comerciante):02d}" + nome_comerciante +  # Merchant Name
        '60' + f"{len(cidade):02d}" + cidade +  # Merchant City
        '6304'      # CRC placeholder
    )
    
    # Calcula CRC16
    crc16 = calcular_crc16(payload_sem_crc)
    
    # Código PIX completo
    codigo_pix = payload_sem_crc + crc16
    
    # Gera QR Code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(codigo_pix)
    qr.make(fit=True)
    
    # Converte QR Code para imagem base64
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    
    return render_template('subscription/pix.html', 
                         plano=info_plano, 
                         codigo_pix=codigo_pix,
                         qr_code_img=img_base64)


@subscription_bp.route('/gerenciar')
@login_required
def gerenciar():
    """Página de gerenciamento da assinatura."""
    if not current_user.subscription:
        flash('Você não possui uma assinatura ativa.', 'info')
        return redirect(url_for('subscription.planos'))
    
    subscription = current_user.subscription
    
    # Calcula dias restantes
    if subscription.current_period_end:
        dias_restantes = (subscription.current_period_end - datetime.utcnow()).days
        data_fim_formatada = subscription.current_period_end.strftime('%d/%m/%Y')
    else:
        dias_restantes = 0
        data_fim_formatada = 'N/A'
    
    recursos_plano = {
        'exportacao_relatorios': current_user.can_access_feature('report_export'),
        'analise_comparativa': current_user.can_access_feature('comparative_analysis'),
        'early_access_features': current_user.can_access_feature('early_access_features'),
        'priority_support': current_user.can_access_feature('priority_support'),
        'vip_support_24_7': current_user.can_access_feature('vip_support_24_7')
    }

    return render_template('subscription/gerenciar.html',
                         subscription=subscription,
                         dias_restantes=dias_restantes,
                         data_fim_formatada=data_fim_formatada,
                         recursos_plano=recursos_plano)


@subscription_bp.route('/suporte', methods=['GET', 'POST'])
@login_required
def suporte():
    """Abertura de chamados com nível de suporte baseado no plano."""
    if not current_user.has_active_subscription():
        flash('Você precisa de uma assinatura ativa para abrir chamados.', 'warning')
        return redirect(url_for('subscription.planos'))

    nivel_disponivel = obter_nivel_suporte_disponivel(current_user)
    if not nivel_disponivel:
        flash('Seu plano atual não possui suporte habilitado.', 'warning')
        return redirect(url_for('subscription.gerenciar'))

    requested_level = request.args.get('nivel', '').strip().lower() or nivel_disponivel
    ordem = {'email': 1, 'priority': 2, 'vip': 3}
    if requested_level not in ordem or ordem[requested_level] > ordem[nivel_disponivel]:
        requested_level = nivel_disponivel

    if request.method == 'POST':
        subject = (request.form.get('subject') or '').strip()
        message = (request.form.get('message') or '').strip()
        form_level = (request.form.get('level') or requested_level).strip().lower()

        if not subject or not message:
            flash('Preencha assunto e descrição do chamado.', 'danger')
            return redirect(url_for('subscription.suporte', nivel=requested_level))

        if form_level not in ordem or ordem[form_level] > ordem[nivel_disponivel]:
            flash('Nível de suporte não permitido para seu plano.', 'danger')
            return redirect(url_for('subscription.suporte', nivel=requested_level))

        ticket = SupportTicket(
            user_id=current_user.id,
            level=form_level,
            subject=subject,
            message=message,
            status='open'
        )
        db.session.add(ticket)
        db.session.commit()

        sla = {
            'email': 'até 48 horas úteis',
            'priority': 'até 24 horas úteis',
            'vip': 'até 4 horas'
        }
        flash(f'Chamado aberto com sucesso. SLA estimado: {sla.get(form_level)}.', 'success')
        return redirect(url_for('subscription.suporte', nivel=form_level))

    tickets = SupportTicket.query.filter_by(user_id=current_user.id).order_by(SupportTicket.created_at.desc()).limit(15).all()

    return render_template(
        'subscription/suporte.html',
        nivel_suporte_disponivel=nivel_disponivel,
        nivel_selecionado=requested_level,
        tickets=tickets
    )


@subscription_bp.route('/cancelar', methods=['POST'])
@login_required
def cancelar():
    """Cancela assinatura no final do período."""
    if not current_user.subscription:
        flash('Você não possui uma assinatura ativa.', 'info')
        return redirect(url_for('subscription.planos'))
    
    subscription = current_user.subscription
    
    if subscription.cancel_at_period_end:
        flash('Sua assinatura já está programada para cancelamento.', 'info')
        return redirect(url_for('subscription.gerenciar'))
    
    # Marca para cancelar no fim do período
    subscription.cancel()
    db.session.commit()
    
    dias_restantes = (subscription.current_period_end - datetime.utcnow()).days if subscription.current_period_end else 0
    flash(f'Cancelamento agendado! Você continuará com acesso total por mais {dias_restantes} dias até {subscription.current_period_end.strftime("%d/%m/%Y")}.', 'warning')
    return redirect(url_for('subscription.gerenciar'))


@subscription_bp.route('/cancelar-imediato', methods=['POST'])
@login_required
def cancelar_imediato():
    """Cancela assinatura imediatamente."""
    if not current_user.subscription:
        flash('Você não possui uma assinatura ativa.', 'info')
        return redirect(url_for('subscription.planos'))
    
    subscription = current_user.subscription
    subscription.cancel_immediately()
    db.session.commit()
    
    flash('Sua assinatura foi cancelada imediatamente.', 'info')
    return redirect(url_for('subscription.planos'))


@subscription_bp.route('/reativar', methods=['POST'])
@login_required
def reativar():
    """Reativa assinatura que estava programada para cancelar."""
    if not current_user.subscription:
        flash('Você não possui uma assinatura.', 'info')
        return redirect(url_for('subscription.planos'))
    
    subscription = current_user.subscription
    
    if not subscription.cancel_at_period_end:
        flash('Sua assinatura não está programada para cancelamento.', 'info')
        return redirect(url_for('subscription.gerenciar'))
    
    subscription.cancel_at_period_end = False
    subscription.canceled_at = None
    subscription.updated_at = datetime.utcnow()
    db.session.commit()
    
    flash('Perfeito! Cancelamento revertido. Sua assinatura continuará renovando automaticamente.', 'success')
    return redirect(url_for('subscription.gerenciar'))


@subscription_bp.route('/webhook/asaas', methods=['POST'])
def webhook_asaas():
    """Webhook do Asaas para processar eventos de pagamento."""
    payload = request.get_json()
    
    if not payload:
        return 'Invalid payload', 400
    
    # Processa eventos do Asaas
    event_type = payload.get('event')
    payment_data = payload.get('payment', {})
    
    if event_type == 'PAYMENT_RECEIVED':
        # Pagamento confirmado - ativar assinatura
        payment_id = payment_data.get('id')
        flash('Pagamento confirmado! Sua assinatura foi ativada.', 'success')
        
    elif event_type == 'PAYMENT_OVERDUE':
        # Pagamento vencido
        pass
        
    elif event_type == 'PAYMENT_DELETED':
        # Pagamento cancelado
        pass
    
    return '', 200


@subscription_bp.route('/verificar-pagamento-pix', methods=['POST'])
@login_required
def verificar_pagamento_pix():
    """Verifica se o pagamento PIX foi confirmado no Asaas."""
    from flask import session, jsonify
    
    payment_id = session.get('asaas_payment_id')
    plano = session.get('plano_selecionado')
    
    if not plano:
        return jsonify({'status': 'error', 'message': 'Nenhum plano selecionado'}), 400
    
    # Se não tem payment_id, está em modo simulação (sem Asaas configurado)
    if not payment_id:
        # Modo simulação - ativa automaticamente
        dias_map = {
            'monthly': 30,
            'quarterly': 90,
            'annual': 365
        }
        periodo_fim = datetime.utcnow() + timedelta(days=dias_map[plano])
        
        if current_user.subscription:
            subscription = current_user.subscription
            subscription.plan = plano
            subscription.status = 'active'
            subscription.current_period_end = periodo_fim
            subscription.cancel_at_period_end = False
            subscription.canceled_at = None
            subscription.gateway = 'simulacao'
            subscription.updated_at = datetime.utcnow()
        else:
            subscription = Subscription(
                user_id=current_user.id,
                plan=plano,
                status='active',
                current_period_end=periodo_fim,
                gateway='simulacao'
            )
            db.session.add(subscription)
        
        db.session.commit()
        session.pop('plano_selecionado', None)
        
        return jsonify({
            'status': 'success',
            'message': 'Pagamento confirmado! (Modo Simulação)',
            'redirect': url_for('dashboard.home')
        })
    
    # Verifica status no Asaas (modo real)
    pagamento = verificar_pagamento_asaas(payment_id)
    
    if pagamento and pagamento.get('status') == 'RECEIVED':
        # Pagamento confirmado - ativa assinatura
        dias_map = {
            'monthly': 30,
            'quarterly': 90,
            'annual': 365
        }
        periodo_fim = datetime.utcnow() + timedelta(days=dias_map[plano])
        
        if current_user.subscription:
            subscription = current_user.subscription
            subscription.plan = plano
            subscription.status = 'active'
            subscription.current_period_end = periodo_fim
            subscription.cancel_at_period_end = False
            subscription.canceled_at = None
            subscription.gateway = 'asaas'
            subscription.gateway_payment_id = payment_id
            subscription.updated_at = datetime.utcnow()
        else:
            subscription = Subscription(
                user_id=current_user.id,
                plan=plano,
                status='active',
                current_period_end=periodo_fim,
                gateway='asaas',
                gateway_payment_id=payment_id
            )
            db.session.add(subscription)
        
        db.session.commit()
        
        # Limpa sessão
        session.pop('asaas_payment_id', None)
        session.pop('plano_selecionado', None)
        
        return jsonify({
            'status': 'success',
            'message': 'Pagamento confirmado!',
            'redirect': url_for('dashboard.home')
        })
    
    return jsonify({
        'status': 'pending',
        'message': 'Aguardando confirmação do pagamento'
    })

