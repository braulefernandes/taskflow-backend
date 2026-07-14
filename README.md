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
- `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`
- `FRONTEND_URL`
- `EMAIL_BACKEND`
- `EMAIL_FROM_ADDRESS`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_USE_TLS`
- `SMTP_TIMEOUT_SECONDS`
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

## Solicitacoes

Endpoints desta entrega:

```text
POST  /api/v1/tickets
GET   /api/v1/tickets?page=1&page_size=20
GET   /api/v1/tickets/{id}
PATCH /api/v1/tickets/{id}
PATCH /api/v1/tickets/{id}/assignee
PATCH /api/v1/tickets/{id}/status
```

Na criacao, o cliente envia somente `title`, `description`, `category_id`,
`priority` e `due_date` opcional. Organizacao e solicitante vem da sessao; o
status inicial e `PENDING`, o responsavel e as datas internas comecam nulos.
A categoria deve estar ativa e pertencer a organizacao, e o prazo, quando
informado, deve estar no futuro.

Exemplo:

```json
{
  "title": "Acesso ao sistema financeiro",
  "description": "Liberar acesso para fechamento mensal.",
  "category_id": "02d895ee-095c-4fc6-a043-34e71bd0a2d1",
  "priority": "HIGH",
  "due_date": "2026-07-20T18:00:00Z"
}
```

A resposta publica inclui organizacao, categoria, solicitante e responsavel em
formatos resumidos e nunca expoe senha ou hash. A listagem retorna `page`,
`page_size`, `total` e `items`, ordenados por criacao decrescente. O tamanho
aceito e de 1 a 100, com padrao 20.

Permissoes:

- `ADMIN` e `MANAGER` criam, visualizam e editam qualquer solicitacao da organizacao;
- `AGENT` cria e visualiza as que criou ou que estao atribuidas a ele, mas nao edita dados gerais;
- `REQUESTER` cria e visualiza somente as proprias, podendo editar enquanto estiverem `PENDING` e sem responsavel.

IDs externos ou fora do escopo do papel retornam `404 resource_not_found`, sem
revelar a existencia do registro. Payloads de criacao e edicao rejeitam campos
internos, incluindo status, organizacao, solicitante, responsavel e datas
operacionais.

A atribuicao usa o contrato abaixo; `null` remove o responsavel:

```json
{
  "assignee_id": "b9cb341a-5503-47d9-aea3-fc20d33f1cbc"
}
```

Somente `ADMIN` e `MANAGER` podem atribuir, trocar ou remover. O responsavel
deve possuir membership ativa na mesma organizacao, usuario ativo e papel
`ADMIN`, `MANAGER` ou `AGENT`. `REQUESTER` nao pode ser responsavel. Repetir a
mesma atribuicao e idempotente. Remocao e permitida nos estados nao terminais.
Tickets `COMPLETED` ou `CANCELLED` rejeitam qualquer alteracao de responsavel
com `409`; a operacao nunca altera o status automaticamente.

Erros especificos de atribuicao incluem `assignee_membership_inactive`,
`assignee_user_inactive`, `assignee_role_not_allowed`,
`cancelled_ticket_assignment` e `completed_ticket_assignment`. Responsavel ou
ticket inexistente/externo retorna `404 resource_not_found`.

### Status, prioridade e prazo

A mudanca de status recebe somente o novo status:

```json
{
  "status": "IN_PROGRESS"
}
```

Maquina de estados permitida:

```text
PENDING     -> IN_PROGRESS | WAITING
IN_PROGRESS -> WAITING | COMPLETED
WAITING     -> IN_PROGRESS | COMPLETED
COMPLETED   -> IN_PROGRESS
CANCELLED   -> nenhuma transicao nesta entrega
```

`ADMIN` e `MANAGER` alteram o status de qualquer ticket da organizacao.
`AGENT` altera apenas tickets atribuidos a ele. `REQUESTER` nao altera status
operacional. `IN_PROGRESS`, `WAITING` e `COMPLETED` exigem responsavel; o status
`PENDING` pode permanecer sem responsavel.

A primeira entrada em `IN_PROGRESS` preenche `started_at` em UTC e entradas
posteriores preservam o valor original. A entrada em `COMPLETED` preenche
`completed_at`; a reabertura controlada para `IN_PROGRESS` limpa
`completed_at`. `cancelled_at` nao e modificado.

Prioridade e prazo continuam no `PATCH /api/v1/tickets/{id}`:

```json
{
  "priority": "URGENT",
  "due_date": "2026-07-25T18:00:00Z"
}
```

Somente `ADMIN` e `MANAGER` podem alterar prioridade ou prazo. O prazo deve
estar no futuro e pode ser removido com `null`. Tickets `COMPLETED` e
`CANCELLED` bloqueiam ambas as alteracoes ate eventual reabertura. Valores de
prioridade fora de `LOW`, `MEDIUM`, `HIGH` e `URGENT` sao rejeitados.

Erros principais: `invalid_status_transition`, `assignee_required_for_status`,
`terminal_ticket_planning_update`, `due_date_in_past` e `insufficient_role`.
Nenhuma operacao desta entrega cancela tickets ou calcula atraso.

Esta entrega nao implementa cancelamento, comentarios, historico, atraso ou
filtros avancados.

## Recuperacao de senha

Endpoints:

```text
POST /api/v1/auth/forgot-password
POST /api/v1/auth/reset-password
```

Solicitacao:

```json
{
  "email": "ana@example.com"
}
```

E-mails sao normalizados. A resposta e sempre `200` com a mesma mensagem,
independentemente de o e-mail existir, estar inativo ou nao estar cadastrado:

```json
{
  "message": "Se o e-mail estiver cadastrado, enviaremos instrucoes para redefinir a senha."
}
```

Para usuarios ativos, a API gera 32 bytes aleatorios com
`secrets.token_urlsafe`, armazena somente o SHA-256 hexadecimal e monta a URL
`FRONTEND_URL/redefinir-senha?token=...`. A validade e configurada por
`PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`. Uma nova solicitacao invalida tokens
anteriores ainda nao usados.

Redefinicao:

```json
{
  "token": "token-recebido-por-email",
  "new_password": "NovaSenha123"
}
```

O backend calcula o hash do token recebido, bloqueia o registro durante a
transacao e valida expiracao, `used_at` e usuario ativo. Senha e `used_at` sao
atualizados na mesma transacao. O token nao autentica o usuario e nao pode ser
reutilizado. Token invalido, expirado, usado ou associado a usuario inativo
retorna o mesmo erro `400 invalid_reset_token`.

### Envio de e-mail

`EMAIL_BACKEND=development` usa um adapter seguro que nao envia mensagens e nao
registra destinatario, URL ou token. `EMAIL_BACKEND=smtp` habilita o adapter
SMTP real. Host, porta, usuario, senha, remetente, TLS e timeout sao definidos
somente por variaveis de ambiente; nao existem credenciais hardcoded.

Para testes, `EmailSender` pode ser substituido por um fake por dependency
override. O fake captura a mensagem em memoria sem acessar rede.

O envio ocorre antes do commit do token para permitir rollback quando o adapter
falha. Existe uma pequena janela em que o SMTP pode aceitar a mensagem e o
commit posterior falhar; eliminar essa janela exige um outbox transacional, que
fica fora do MVP. Falhas sao registradas apenas com mensagem generica, sem
destinatario, URL, token ou credenciais.

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
