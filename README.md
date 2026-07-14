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
  1:N categories

organization_members
  N:1 users
  N:1 organizations
  role: ADMIN | MANAGER | AGENT | REQUESTER

categories
  N:1 organizations
  unique: organization_id + normalized_name
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
- o login nao cria refresh token e nao executa logout.

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

## Usuario autenticado

Endpoint:

```text
GET /api/v1/auth/me
```

Autenticacao:

```text
Authorization: Bearer <access_token>
```

O token e validado pela assinatura, expiracao e `sub`. A API busca o usuario no banco, exige usuario ativo e exige membership ativo na organizacao indicada pelo token.

Exemplo de resposta `200 OK`:

```json
{
  "user": {
    "id": "00000000-0000-0000-0000-000000000000",
    "name": "Ana Silva",
    "email": "ana@example.com",
    "avatar_url": null,
    "is_active": true
  },
  "organization": {
    "id": "00000000-0000-0000-0000-000000000000",
    "name": "Acme Suporte",
    "slug": "acme-suporte"
  },
  "membership": {
    "id": "00000000-0000-0000-0000-000000000000",
    "role": "ADMIN",
    "is_active": true
  }
}
```

Erros esperados:

- `401 not_authenticated`: token ausente, malformado, invalido, expirado,
  usuario inexistente/inativo ou membership inexistente.
- `403 membership_inactive`: membership existente, mas inativa na organizacao atual.

O endpoint nao retorna senha, hash de senha, token, segredo ou timestamps desnecessarios.

## Logout

Endpoint:

```text
POST /api/v1/auth/logout
```

Autenticacao:

```text
Authorization: Bearer <access_token>
```

Estrategia: JWT stateless. No MVP nao existe blacklist, tabela de revogacao, Redis, refresh token ou rotacao de sessoes. Por isso, o endpoint valida a autenticacao e retorna sucesso, mas nao revoga o token no backend. A responsabilidade do cliente e descartar o token localmente e encerrar a sessao na interface.

Response `200 OK`:

```json
{
  "message": "Logout registrado no cliente. Descarte o token localmente.",
  "token_revoked": false
}
```

Comportamento:

- token ausente, malformado, invalido ou expirado retorna `401 not_authenticated`;
- chamadas repetidas com o mesmo token valido retornam sucesso;
- o token continua tecnicamente valido ate sua expiracao natural;
- riscos e limitacoes: se um token for copiado antes do logout, ele pode ser usado ate expirar;
- evolucao futura: refresh token com rotacao e revogacao persistente.

## Gerenciamento de membros

Todos os endpoints exigem JWT valido e papel `ADMIN`. A organizacao e obtida do
contexto autenticado; a API nao aceita `organization_id` no payload.

Endpoints:

```text
GET   /api/v1/members
POST  /api/v1/members
GET   /api/v1/members/{id}
PATCH /api/v1/members/{id}
PATCH /api/v1/members/{id}/status
```

A listagem aceita `search`, `role`, `is_active`, `page` e `page_size`. O retorno
contem `items`, `total`, `page` e `page_size`. Cada item apresenta somente o ID
da membership, ID do usuario, nome, e-mail, papel, status e datas da membership.

Para criar um membro, envie nome, e-mail, papel e `temporary_password`. O e-mail
e normalizado. Se o usuario ja existir, ele e associado sem alterar seus dados
ou senha; se nao existir, um usuario ativo e criado com hash seguro. Senhas e
hashes nunca sao retornados.

Exemplo de criacao:

```json
{
  "name": "Maria Souza",
  "email": "maria@example.com",
  "role": "AGENT",
  "temporary_password": "Temporaria123"
}
```

Alteracao de papel usa `{ "role": "MANAGER" }`. Alteracao de status usa
`{ "is_active": false }`. A API rejeita membership duplicada e impede desativar
ou remover o papel do ultimo administrador ativo. IDs de outra organizacao
retornam `404 resource_not_found`, sem revelar a existencia do recurso.

Erros de negocio:

- `403 insufficient_role`: o usuario nao e administrador;
- `404 resource_not_found`: membro inexistente ou de outra organizacao;
- `409 membership_already_exists`: usuario ja associado;
- `409 last_active_admin`: a operacao deixaria a organizacao sem administrador
  ativo.

## Perfil do usuario autenticado

Endpoint:

```text
PATCH /api/v1/users/me
```

A rota exige JWT valido e atualiza somente o usuario do contexto autenticado.
O payload e parcial e aceita apenas `name` e `avatar_url`:

```json
{
  "name": "Ana Silva",
  "avatar_url": "https://example.com/avatar.png"
}
```

O nome tem entre 1 e 255 caracteres e espacos repetidos sao normalizados. A URL
do avatar deve usar HTTP ou HTTPS, ter no maximo 2048 caracteres e pode receber
`null` para remover o avatar atual.

E-mail, status, senha ou hash, papel, organizacao, membership, IDs e timestamps
sao rejeitados com `422 validation_error`. A resposta possui somente `id`,
`name`, `email`, `avatar_url` e `is_active`; senha e hash nunca sao retornados.
O endpoint `GET /api/v1/auth/me` reflete os dados atualizados.

## Categorias

Categorias pertencem sempre a organizacao do contexto autenticado. Nao existe
endpoint de exclusao fisica: a desativacao preserva o registro e seu historico.

Endpoints:

```text
GET   /api/v1/categories
POST  /api/v1/categories
GET   /api/v1/categories/{id}
PATCH /api/v1/categories/{id}
PATCH /api/v1/categories/{id}/status
```

`ADMIN` cria, edita, ativa e desativa. Qualquer usuario autenticado pode listar
as categorias ativas para formularios. A listagem administrativa usa
`include_inactive=true` e e exclusiva de `ADMIN`.

Exemplo de criacao:

```json
{
  "name": "Suporte Tecnico",
  "description": "Demandas de suporte e infraestrutura"
}
```

O nome e obrigatorio, possui ate 255 caracteres e tem espacos externos e
repetidos normalizados. A unicidade ignora maiusculas e minusculas dentro da
mesma organizacao: `Financeiro` e `FINANCEIRO` sao o mesmo nome. A grafia de
exibicao e preservada em `name`; a chave interna `normalized_name` usa
`casefold()` e nao e exposta pela API. Acentos continuam significativos.

Constraint principal:

```text
UNIQUE (organization_id, normalized_name)
```

O mesmo nome pode existir em organizacoes diferentes. Consultas por ID e
listagens sempre filtram pela organizacao autenticada. Um ID externo retorna
`404 resource_not_found`.

Exemplo de edicao parcial:

```json
{
  "name": "Infraestrutura",
  "description": null
}
```

Exemplo de desativacao:

```json
{
  "is_active": false
}
```

Erros principais:

- `403 insufficient_role`: operacao administrativa sem papel `ADMIN`;
- `404 resource_not_found`: categoria inexistente ou de outra organizacao;
- `409 category_already_exists`: nome normalizado duplicado na organizacao;
- `422 validation_error`: payload ou nome invalido.

## Testes

```powershell
pytest
```

Os testes carregam configuracoes de ambiente de teste e nao devem usar banco de producao. A suite rapida usa SQLite em memoria para isolar dados por teste e manter repetibilidade. Essa escolha cobre os fluxos HTTP e regras de negocio, mas pode mascarar diferencas de PostgreSQL em tipos, enum e DDL.

Para validar migrations em PostgreSQL, configure uma URL explicita de teste:

```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg://taskflow_test:taskflow_test_password@localhost:5432/taskflow_test"
python scripts/validate_migrations.py
```

O script recusa URLs que nao sejam PostgreSQL ou que nao parecam apontar para banco de teste. O procedimento executa `upgrade head`, `downgrade base` e novo `upgrade head`.

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
