"""
Configuração da aplicação Flask.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega variáveis da raiz do projeto para evitar diferenças de execução.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / '.env')

class Config:
    """Configurações da aplicação."""
    
    # Chave secreta para sessões
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Banco de dados
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///motoristas.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Asaas (Gateway de Pagamento)
    ASAAS_API_KEY = os.getenv('ASAAS_API_KEY')
    ASAAS_WALLET_ID = os.getenv('ASAAS_WALLET_ID')
    ASAAS_API_URL = os.getenv('ASAAS_API_URL', 'https://sandbox.asaas.com/api/v3')  # sandbox ou production

    # Recuperação de senha
    # Em produção, mantenha como False e implemente envio de token por email.
    PASSWORD_RESET_DEMO = os.getenv('PASSWORD_RESET_DEMO', 'false').lower() == 'true'
    PASSWORD_RESET_DEMO_PASSWORD = os.getenv('PASSWORD_RESET_DEMO_PASSWORD', '123456')

    # Preview local para desenvolvimento: permite acessar gráficos sem assinatura ativa.
    ALLOW_GRAPH_PREVIEW_WITHOUT_SUBSCRIPTION = (
        os.getenv('ALLOW_GRAPH_PREVIEW_WITHOUT_SUBSCRIPTION', 'false').lower() == 'true'
    )
    
    # Preços (em centavos)
    PRICE_MONTHLY = int(os.getenv('PRICE_MONTHLY', 1190))    # R$ 11,90/mês
    PRICE_QUARTERLY = int(os.getenv('PRICE_QUARTERLY', 3490))  # R$ 34,90/trimestre
    PRICE_ANNUAL = int(os.getenv('PRICE_ANNUAL', 9990))      # R$ 99,90/ano
