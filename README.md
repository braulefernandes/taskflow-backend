# TaskFlow Backend

Backend do TaskFlow, iniciado com FastAPI para servir a API HTTP do produto.

## Tecnologias

- Python 3.12+
- FastAPI
- Pydantic Settings
- SQLAlchemy 2
- PostgreSQL
- Alembic
- Pytest

## Pre-requisitos

- Python instalado
- PostgreSQL em execucao
- Ambiente virtual Python

## Ambiente virtual

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## Instalacao

```powershell
pip install -r requirements.txt
```

## Variaveis de ambiente

Copie `.env.example` para `.env` e ajuste os valores locais. Nao coloque segredos reais no repositorio.

Configuracoes principais:

- `APP_NAME`
- `APP_VERSION`
- `APP_ENV`
- `APP_DEBUG`
- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `JWT_ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `FRONTEND_URL`
- `BACKEND_CORS_ORIGINS`
- `API_V1_PREFIX`

## PostgreSQL

Crie um banco local e configure `DATABASE_URL` usando o driver `psycopg`:

```text
postgresql+psycopg://taskflow:taskflow_dev_password@localhost:5432/taskflow_dev
```

As migrations serao gerenciadas pelo Alembic. A aplicacao nao executa `Base.metadata.create_all()` no startup.

## Executar API

```powershell
uvicorn app.main:app --reload
```

Por padrao, a API fica em `http://127.0.0.1:8000`.

## Health check

```text
GET /health
GET /api/v1/health
```

Resposta esperada:

```json
{
  "status": "ok",
  "service": "TaskFlow API",
  "version": "0.1.0"
}
```

## Documentacao interativa

- Swagger: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## Alembic

Validar configuracao:

```powershell
alembic current
```

Criar migrations futuras com autogenerate:

```powershell
alembic revision --autogenerate -m "mensagem"
```

## Testes

```powershell
pytest
```

Os testes carregam configuracoes de ambiente de teste e nao devem usar banco de producao.

## Estrutura inicial

```text
app/
  api/
    v1/
  core/
  db/
  models/
  repositories/
  schemas/
  services/
alembic/
  versions/
tests/
```
