# App Motoristas

Sistema web para motoristas de aplicativo gerenciarem corridas, receita e assinatura.

## Funcionalidades

- Autenticação de usuários (cadastro, login, logout e recuperação de senha em modo demo)
- CRUD completo de corridas com cálculo automático de receita líquida
- Dashboard com métricas e gráficos por período e plataforma
- Planos de assinatura (mensal, trimestral, anual)
- Pagamento via PIX com Asaas (e fallback de simulação)
- Exportação de relatório CSV (por nível de plano)

## Stack

- Python + Flask
- SQLAlchemy + Flask-Migrate
- Flask-Login
- Bootstrap + Chart.js
- SQLite (desenvolvimento) / PostgreSQL (produção, via `psycopg`)

## Requisitos

- Python `3.13` (compatível)
- `pip`

Observação: as dependências já foram atualizadas para compatibilidade com Python 3.13.

## Como rodar localmente

1. Criar e ativar ambiente virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Instalar dependências:

```powershell
pip install -r requirements.txt
```

3. Criar `.env` (base no `.env.example`):

```env
SECRET_KEY=sua_chave_secreta
DATABASE_URL=sqlite:///motoristas.db
ASAAS_API_KEY=
ASAAS_WALLET_ID=
ASAAS_API_URL=https://sandbox.asaas.com/api/v3
PASSWORD_RESET_DEMO=false
```

4. Executar:

```powershell
python web/app.py
```

App disponível em `http://localhost:5000`.

## Estrutura

```text
web/
  app.py
  config.py
  models.py
  blueprints/
  templates/
  static/
```

## Segurança

- Senhas com hash (Werkzeug)
- Controle de sessão com Flask-Login
- Variáveis sensíveis via `.env`
- `.gitignore` preparado para evitar versionamento de segredos e banco local
