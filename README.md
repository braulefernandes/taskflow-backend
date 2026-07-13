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

## Modelo inicial de autenticacao

Esta branch define apenas a modelagem ORM e a migration inicial de autenticacao. Nao ha endpoints de cadastro, login, JWT ou recuperacao de senha.

Diagrama textual:

```text
users
  1:N organization_members
  1:N password_reset_tokens

organizations
  1:N organization_members

organization_members
  N:1 users
  N:1 organizations
  role: ADMIN | MANAGER | AGENT | REQUESTER
```

## Cadastro inicial

Endpoint:

```text
POST /api/v1/auth/register
```

Cria, na mesma transacao, o usuario inicial, a organizacao e o membership ativo com papel `ADMIN`. O cadastro nao retorna token e nao realiza login automatico.

Request:

```json
{
  "user_name": "Ana Silva",
  "email": "ana@example.com",
  "password": "Senha123",
  "organization_name": "Acme Suporte"
}
```

Regras:

- `user_name`: obrigatorio, ate 255 caracteres, com espacos extras removidos.
- `email`: obrigatorio, valido, normalizado para minusculas e unico.
- `password`: entre 8 e 128 caracteres, contendo letras e numeros.
- `organization_name`: obrigatorio, ate 255 caracteres, com espacos extras removidos.
- o slug da organizacao e derivado do nome, normaliza acentos e caracteres especiais, e recebe sufixo numerico em caso de colisao, como `acme`, `acme-2`.

Response `201 Created`:

```json
{
  "user": {
    "id": "00000000-0000-0000-0000-000000000000",
    "name": "Ana Silva",
    "email": "ana@example.com",
    "avatar_url": null,
    "is_active": true,
    "created_at": "2026-07-13T09:00:00Z"
  },
  "organization": {
    "id": "00000000-0000-0000-0000-000000000000",
    "name": "Acme Suporte",
    "slug": "acme-suporte",
    "created_at": "2026-07-13T09:00:00Z"
  },
  "membership": {
    "id": "00000000-0000-0000-0000-000000000000",
    "role": "ADMIN",
    "is_active": true,
    "created_at": "2026-07-13T09:00:00Z"
  }
}
```

Erros esperados:

- `422 validation_error`: dados invalidos.
- `409 email_already_registered`: e-mail ja cadastrado.
- `409 organization_slug_conflict`: nao foi possivel gerar slug unico.
- `500 registration_persistence_error`: falha de persistencia durante o cadastro.

Campos sensiveis como senha, hash da senha e tokens nunca sao retornados.

## Login com JWT

Endpoint:

```text
POST /api/v1/auth/login
```

Formato escolhido: JSON com e-mail e senha. A decisao segue o contrato atual do cadastro e evita expor dois formatos de autenticacao sem necessidade nesta fase.

Request:

```json
{
  "email": "ana@example.com",
  "password": "Senha123"
}
```

Regras:

- o e-mail e normalizado para minusculas antes da busca;
- senha e comparada com o hash centralizado;
- usuario inativo nao autentica;
- usuario sem membership ativo nao autentica;
- e-mail inexistente e senha incorreta retornam a mesma mensagem generica;
- o login nao cria refresh token, nao executa logout e nao implementa `/auth/me`.

Response `200 OK`:

```json
{
  "access_token": "jwt.assinado.aqui",
  "token_type": "bearer",
  "expires_in": 1800
}
```

Claims do access token:

- `sub`: identificador estavel do usuario;
- `iat`: timestamp de emissao;
- `exp`: timestamp de expiracao;
- `org`: organizacao atual usada no login;
- `role`: papel do membership ativo.

O token nao inclui senha, hash, e-mail, nome, segredo ou objetos completos. A assinatura usa o algoritmo configurado em `JWT_ALGORITHM`, atualmente suportado como `HS256`, e o segredo vem de `JWT_SECRET_KEY`. A duracao vem de `ACCESS_TOKEN_EXPIRE_MINUTES`.

Erros esperados:

- `401 invalid_credentials`: credenciais invalidas, usuario inativo ou ausencia de membership ativo.
- `422 validation_error`: payload invalido.

Refresh token e rotacao de sessoes ficam como melhoria futura.

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
