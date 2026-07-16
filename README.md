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

## Instalação

```powershell
pip install -r requirements.txt
```

## Variáveis de ambiente

Copie `.env.example` para `.env` e ajuste os valores locais. Não coloque segredos reais no repositorio.

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

As migrations serao gerenciadas pelo Alembic. A aplicação não executa `Base.metadata.create_all()` no startup.

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

## Modelo inicial de autenticação

Esta branch define apenas a modelagem ORM e a migration inicial de autenticação. Não ha endpoints de cadastro, login, JWT ou recuperação de senha.

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

Cria, na mesma transacao, o usuário inicial, a organização e o membership ativo com papel `ADMIN`. O cadastro não retorna token e não realiza login automático.

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

- `user_name`: obrigatório, até 255 caracteres, com espacos extras removidos.
- `email`: obrigatório, válido, normalizado para minusculas e unico.
- `password`: entre 8 e 128 caracteres, contendo letras e números.
- `organization_name`: obrigatório, até 255 caracteres, com espacos extras removidos.
- o slug da organização e derivado do nome, normaliza acentos e caracteres especiais, e recebe sufixo numerico em caso de colisao, como `acme`, `acme-2`.

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

- `422 validation_error`: dados inválidos.
- `409 email_already_registered`: e-mail já cadastrado.
- `409 organization_slug_conflict`: não foi possível gerar slug unico.
- `500 registration_persistence_error`: falha de persistencia durante o cadastro.

Campos sensíveis como senha, hash da senha e tokens nunca são retornados.

## Login com JWT

Endpoint:

```text
POST /api/v1/auth/login
```

Formato escolhido: JSON com e-mail e senha. A decisao segue o contrato atual do cadastro e evita expor dois formatos de autenticação sem necessidade nesta fase.

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
- usuário inativo não autentica;
- usuário sem membership ativo não autentica;
- e-mail inexistente e senha incorreta retornam a mesma mensagem genérica;
- o login não cria refresh token e não executa logout.

Response `200 OK`:

```json
{
  "access_token": "jwt.assinado.aqui",
  "token_type": "bearer",
  "expires_in": 1800
}
```

Claims do access token:

- `sub`: identificador estavel do usuário;
- `iat`: timestamp de emissao;
- `exp`: timestamp de expiracao;
- `org`: organização atual usada no login;
- `role`: papel do membership ativo.

O token não inclui senha, hash, e-mail, nome, segredo ou objetos completos. A assinatura usa o algoritmo configurado em `JWT_ALGORITHM`, atualmente suportado como `HS256`, e o segredo vem de `JWT_SECRET_KEY`. A duração vem de `ACCESS_TOKEN_EXPIRE_MINUTES`.

Erros esperados:

- `401 invalid_credentials`: credenciais inválidas, usuário inativo ou ausência de membership ativo.
- `422 validation_error`: payload inválido.

Refresh token e rotacao de sessoes ficam como melhoria futura.

## Usuário autenticado

Endpoint:

```text
GET /api/v1/auth/me
```

Autenticação:

```text
Authorization: Bearer <access_token>
```

O token e validado pela assinatura, expiracao e `sub`. A API busca o usuário no banco, exige usuário ativo e exige membership ativo na organização indicada pelo token.

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

- `401 not_authenticated`: token ausente, malformado, inválido, expirado,
  usuário inexistente/inativo ou membership inexistente.
- `403 membership_inactive`: membership existente, mas inativa na organização atual.

O endpoint não retorna senha, hash de senha, token, segredo ou timestamps desnecessarios.

## Logout

Endpoint:

```text
POST /api/v1/auth/logout
```

Autenticação:

```text
Authorization: Bearer <access_token>
```

Estrategia: JWT stateless. No MVP não existe blacklist, tabela de revogacao, Redis, refresh token ou rotacao de sessoes. Por isso, o endpoint válida a autenticação e retorna sucesso, mas não revoga o token no backend. A responsabilidade do cliente e descartar o token localmente e encerrar a sessão na interface.

Response `200 OK`:

```json
{
  "message": "Logout registrado no cliente. Descarte o token localmente.",
  "token_revoked": false
}
```

Comportamento:

- token ausente, malformado, inválido ou expirado retorna `401 not_authenticated`;
- chamadas repetidas com o mesmo token válido retornam sucesso;
- o token continua tecnicamente válido até sua expiracao natural;
- riscos e limitações: se um token for copiado antes do logout, ele pode ser usado até expirar;
- evolucao futura: refresh token com rotacao e revogacao persistente.

## Gerenciamento de membros

Todos os endpoints exigem JWT válido e papel `ADMIN`. A organização e obtida do
contexto autenticado; a API não aceita `organization_id` no payload.

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
da membership, ID do usuário, nome, e-mail, papel, status e datas da membership.

Para criar um membro, envie nome, e-mail, papel e `temporary_password`. O e-mail
e normalizado. Se o usuário já existir, ele e associado sem alterar seus dados
ou senha; se não existir, um usuário ativo e criado com hash seguro. Senhas e
hashes nunca são retornados.

Exemplo de criação:

```json
{
  "name": "Maria Souza",
  "email": "maria@example.com",
  "role": "AGENT",
  "temporary_password": "Temporaria123"
}
```

Alteração de papel usa `{ "role": "MANAGER" }`. Alteração de status usa
`{ "is_active": false }`. A API rejeita membership duplicada e impede desativar
ou remover o papel do ultimo administrador ativo. IDs de outra organização
retornam `404 resource_not_found`, sem revelar a existencia do recurso.

Erros de negocio:

- `403 insufficient_role`: o usuário não e administrador;
- `404 resource_not_found`: membro inexistente ou de outra organização;
- `409 membership_already_exists`: usuário já associado;
- `409 last_active_admin`: a operacao deixaria a organização sem administrador
  ativo.

## Perfil do usuário autenticado

Endpoint:

```text
PATCH /api/v1/users/me
```

A rota exige JWT válido e atualiza somente o usuário do contexto autenticado.
O payload e parcial e aceita apenas `name` e `avatar_url`:

```json
{
  "name": "Ana Silva",
  "avatar_url": "https://example.com/avatar.png"
}
```

O nome tem entre 1 e 255 caracteres e espacos repetidos são normalizados. A URL
do avatar deve usar HTTP ou HTTPS, ter no máximo 2048 caracteres e pode receber
`null` para remover o avatar atual.

E-mail, status, senha ou hash, papel, organização, membership, IDs e timestamps
são rejeitados com `422 validation_error`. A resposta possui somente `id`,
`name`, `email`, `avatar_url` e `is_active`; senha e hash nunca são retornados.
O endpoint `GET /api/v1/auth/me` reflete os dados atualizados.

## Categorias

Categorias pertencem sempre a organização do contexto autenticado. Não existe
endpoint de exclusão física: a desativacao preserva o registro e seu histórico.

Endpoints:

```text
GET   /api/v1/categories
POST  /api/v1/categories
GET   /api/v1/categories/{id}
PATCH /api/v1/categories/{id}
PATCH /api/v1/categories/{id}/status
```

`ADMIN` cria, edita, ativa e desativa. Qualquer usuário autenticado pode listar
as categorias ativas para formulários. A listagem administrativa usa
`include_inactive=true` e e exclusiva de `ADMIN`.

Exemplo de criação:

```json
{
  "name": "Suporte Técnico",
  "description": "Demandas de suporte e infraestrutura"
}
```

O nome e obrigatório, possui até 255 caracteres e tem espacos externos e
repetidos normalizados. A unicidade ignora maiusculas e minusculas dentro da
mesma organização: `Financeiro` e `FINANCEIRO` são o mesmo nome. A grafia de
exibicao e preservada em `name`; a chave interna `normalized_name` usa
`casefold()` e não e exposta pela API. Acentos continuam significativos.

Constraint principal:

```text
UNIQUE (organization_id, normalized_name)
```

O mesmo nome pode existir em organizacoes diferentes. Consultas por ID e
listagens sempre filtram pela organização autenticada. Um ID externo retorna
`404 resource_not_found`.

Exemplo de edição parcial:

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
- `404 resource_not_found`: categoria inexistente ou de outra organização;
- `409 category_already_exists`: nome normalizado duplicado na organização;
- `422 validation_error`: payload ou nome inválido.

## Solicitações

Endpoints desta entrega:

```text
POST  /api/v1/tickets
GET   /api/v1/tickets?page=1&page_size=20
GET   /api/v1/tickets/{id}
PATCH /api/v1/tickets/{id}
PATCH /api/v1/tickets/{id}/assignee
PATCH /api/v1/tickets/{id}/status
POST  /api/v1/tickets/{id}/cancel
```

Na criação, o cliente envia somente `title`, `description`, `category_id`,
`priority` e `due_date` opcional. Organização e solicitante vem da sessão; o
status inicial e `PENDING`, o responsável e as datas internas comecam nulos.
A categoria deve estar ativa e pertencer a organização, e o prazo, quando
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

A resposta pública inclui organização, categoria, solicitante e responsável em
formatos resumidos e nunca expoe senha ou hash. A listagem retorna `page`,
`page_size`, `total`, `total_pages` e `items`. O tamanho aceito e de 1 a 100,
com padrao 20.

### Pesquisa, filtros, ordenação e paginação

`GET /api/v1/tickets` aceita:

| Parâmetro | Regra |
|---|---|
| `search` | trecho do título, sem diferenciar maiusculas e minusculas; recebe trim |
| `status` | `PENDING`, `IN_PROGRESS`, `WAITING`, `COMPLETED` ou `CANCELLED` |
| `priority` | `LOW`, `MEDIUM`, `HIGH` ou `URGENT` |
| `category_id` | UUID da categoria |
| `assignee_id` | UUID do responsável |
| `created_from`, `created_to` | intervalo inclusivo de criação |
| `due_from`, `due_to` | intervalo inclusivo de prazo |
| `overdue` | `true` para atrasadas e `false` para não atrasadas |
| `sort_by` | `created_at` ou `due_date` |
| `sort_order` | `asc` ou `desc` |
| `page` | página a partir de 1; padrao 1 |
| `page_size` | de 1 a 100; padrao 20 |

Todos os filtros podem ser combinados e são aplicados junto ao isolamento da
organização e ao escopo do papel. O `total` usa os mesmos filtros dos itens,
antes de `offset` e `limit`. Exemplo:

```text
GET /api/v1/tickets?search=financeiro&status=IN_PROGRESS&priority=HIGH&overdue=true&sort_by=due_date&sort_order=asc&page=1&page_size=20
```

Datas sem timezone são interpretadas como UTC; datas com offset são convertidas
para UTC. Os limites `from` e `to` são inclusivos. Um limite inicial posterior
ao final retorna `422`. A ordenação padrao e `created_at desc`; empates usam o
UUID na mesma direcao para manter páginas estaveis. Prazos nulos ficam ao final.
Campos de ordenação arbitrarios são rejeitados.

Uma solicitação e atrasada quando possui `due_date` anterior ao instante da
consulta e seu status não e `COMPLETED` nem `CANCELLED`. O filtro e calculado na
consulta e não depende de coluna persistida. `overdue=false` inclui prazos
futuros, tickets sem prazo e tickets em estado terminal.

Permissões:

- `ADMIN` e `MANAGER` criam, visualizam e editam qualquer solicitação da organização;
- `AGENT` cria e visualiza as que criou ou que estao atribuidas a ele, mas não edita dados gerais;
- `REQUESTER` cria e visualiza somente as próprias, podendo editar enquanto estiverem `PENDING` e sem responsável.

IDs externos ou fora do escopo do papel retornam `404 resource_not_found`, sem
revelar a existencia do registro. Payloads de criação e edição rejeitam campos
internos, incluindo status, organização, solicitante, responsável e datas
operacionais.

A atribuição usa o contrato abaixo; `null` remove o responsável:

```json
{
  "assignee_id": "b9cb341a-5503-47d9-aea3-fc20d33f1cbc"
}
```

Somente `ADMIN` e `MANAGER` podem atribuir, trocar ou remover. O responsável
deve possuir membership ativa na mesma organização, usuário ativo e papel
`ADMIN`, `MANAGER` ou `AGENT`. `REQUESTER` não pode ser responsável. Repetir a
mesma atribuição e idempotente. Remoção e permitida nos estados não terminais.
Tickets `COMPLETED` ou `CANCELLED` rejeitam qualquer alteração de responsável
com `409`; a operacao nunca altera o status automaticamente.

Erros especificos de atribuição incluem `assignee_membership_inactive`,
`assignee_user_inactive`, `assignee_role_not_allowed`,
`cancelled_ticket_assignment` e `completed_ticket_assignment`. Responsável ou
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
CANCELLED   -> nenhuma transição nesta entrega
```

`ADMIN` e `MANAGER` alteram o status de qualquer ticket da organização.
`AGENT` altera apenas tickets atribuídos a ele. `REQUESTER` não altera status
operacional. `IN_PROGRESS`, `WAITING` e `COMPLETED` exigem responsável; o status
`PENDING` pode permanecer sem responsável.

A primeira entrada em `IN_PROGRESS` preenche `started_at` em UTC e entradas
posteriores preservam o valor original. A entrada em `COMPLETED` preenche
`completed_at`; a reabertura controlada para `IN_PROGRESS` limpa
`completed_at`. `cancelled_at` não e modificado.

Prioridade e prazo continuam no `PATCH /api/v1/tickets/{id}`:

```json
{
  "priority": "URGENT",
  "due_date": "2026-07-25T18:00:00Z"
}
```

Somente `ADMIN` e `MANAGER` podem alterar prioridade ou prazo. O prazo deve
estar no futuro e pode ser removido com `null`. Tickets `COMPLETED` e
`CANCELLED` bloqueiam ambas as alterações até eventual reabertura. Valores de
prioridade fora de `LOW`, `MEDIUM`, `HIGH` e `URGENT` são rejeitados.

Erros principais: `invalid_status_transition`, `assignee_required_for_status`,
`terminal_ticket_planning_update`, `due_date_in_past` e `insufficient_role`.
Nenhuma operacao desta entrega calcula ou persiste um novo status de atraso.

### Cancelamento e atraso

O cancelamento usa `POST /api/v1/tickets/{id}/cancel`, sem corpo e sem motivo,
pois ainda não existe campo de motivo modelado. Ele e logico: o registro e
preservado, o status muda para `CANCELLED`, `cancelled_at` recebe o instante UTC
e `completed_at` permanece nulo. Repetir o cancelamento retorna o mesmo ticket
sem substituir `cancelled_at`.

`ADMIN` e `MANAGER` cancelam qualquer ticket da organização. `REQUESTER` pode
cancelar somente um ticket próprio enquanto `PENDING`. `AGENT` não cancela.
Tickets concluídos retornam `409 completed_ticket_cancellation`. Tickets
cancelados não podem ser editados, receber responsável ou mudar pelo endpoint
comum de status. Não existe endpoint de exclusão física.

Toda resposta pública de ticket, inclusive listagem, possui:

```json
{
  "is_overdue": true,
  "overdue_seconds": 5400
}
```

O atraso e calculado no momento da resposta, em segundos inteiros e UTC. Um
ticket e atrasado quando possui `due_date` anterior ao instante atual e não está
`COMPLETED` nem `CANCELLED`. Nos demais casos, `is_overdue` e falso e
`overdue_seconds` e zero. Esses campos não existem na tabela e não são
persistidos. Datetimes sem timezone vindos de bancos de teste são tratados como
UTC defensivamente.

Esta entrega não implementa motivo de cancelamento, exclusão física, filtros de
atraso, histórico automático, dashboard ou filtros avancados.

## Comentários de solicitações

Endpoints autenticados:

```text
POST /api/v1/tickets/{id}/comments
GET  /api/v1/tickets/{id}/comments
```

A criação recebe exclusivamente `content`, com trim nas extremidades e tamanho
entre 1 e 5000 caracteres:

```json
{
  "content": "Informação adicional para o atendimento."
}
```

A resposta `201 Created` e cada item da listagem possuem somente dados publicos:

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "ticket_id": "00000000-0000-0000-0000-000000000000",
  "content": "Informação adicional para o atendimento.",
  "author": {
    "id": "00000000-0000-0000-0000-000000000000",
    "name": "Ana Silva",
    "avatar_url": null
  },
  "created_at": "2026-07-15T15:00:00Z",
  "updated_at": "2026-07-15T15:00:00Z"
}
```

`ADMIN` e `MANAGER` acessam os comentários de qualquer ticket da organização.
`AGENT` acessa tickets criados por ele ou atribuídos a ele. `REQUESTER` acessa
somente os tickets próprios. Tickets externos ou fora desse escopo retornam
`404 resource_not_found`, sem revelar sua existencia.

Tickets concluídos continuam aceitando comentários para permitir complementos
e esclarecimentos posteriores. Tickets cancelados bloqueiam novos comentários
para todos os papeis com `409 cancelled_ticket_comment`; comentários existentes
continuam disponíveis para leitura. A listagem retorna um array, sem paginação,
em ordem cronologica crescente por `created_at`, usando `id` como desempate.

Conteudo ausente, vazio, composto apenas por espacos ou acima do limite retorna
`422 validation_error`. Falhas de persistencia retornam
`500 comment_persistence_error`. A API nunca retorna senha ou hash do autor.

## Histórico de solicitações

Endpoint autenticado:

```text
GET /api/v1/tickets/{id}/history
```

A timeline registra `CREATED`, `TITLE_CHANGED`, `DESCRIPTION_CHANGED`,
`CATEGORY_CHANGED`, `PRIORITY_CHANGED`, `DUE_DATE_CHANGED`, `ASSIGNED`,
`ASSIGNEE_CHANGED`, `ASSIGNEE_REMOVED`, `STATUS_CHANGED`, `COMPLETED`,
`REOPENED` e `CANCELLED`. Conclusao, reabertura e cancelamento usam somente a
ação específica, sem um segundo evento genérico de status. Repetir atribuição,
cancelamento ou edição com o mesmo valor não cria evento.

Cada item retorna ID, ação, campo alterado quando aplicavel, valores anterior e
novo, autor público e data:

```json
{
  "id": "00000000-0000-0000-0000-000000000000",
  "action": "PRIORITY_CHANGED",
  "field_name": "priority",
  "old_value": "MEDIUM",
  "new_value": "HIGH",
  "author": {
    "id": "00000000-0000-0000-0000-000000000000",
    "name": "Ana Silva",
    "avatar_url": null
  },
  "created_at": "2026-07-15T16:00:00Z"
}
```

Status e prioridades usam seus códigos estaveis. Datas usam ISO 8601 em UTC.
Categoria e responsável usam `ID | nome`; ausência de valor e representada por
`null`. Valores contendo termos associados a senha, hash, token ou segredo são
substituidos por `[REDACTED]`, e nenhum dado de autenticação integra a resposta.

Eventos são adicionados pelo service antes do mesmo `commit` da alteração do
ticket. Uma falha ao persistir o histórico executa rollback da alteração
principal, evitando estado parcialmente auditado. Repositories não executam
commits.

A listagem segue exatamente a visibilidade do ticket: `ADMIN` e `MANAGER`
visualizam qualquer ticket da organização; `AGENT`, somente tickets criados por
ele ou atribuídos a ele; `REQUESTER`, somente tickets próprios. Recursos
externos ou fora do escopo retornam `404`. A ordem e cronologica crescente por
`created_at`, adequada para timeline, com `id` como desempate.

## Dashboard gerencial

Endpoints exclusivos de `ADMIN` e `MANAGER`:

```text
GET /api/v1/dashboard/summary
GET /api/v1/dashboard/status-distribution
GET /api/v1/dashboard/priority-distribution
GET /api/v1/dashboard/recent?limit=5
GET /api/v1/dashboard/overdue?limit=5
```

`AGENT` e `REQUESTER` recebem `403 insufficient_role`; suas areas iniciais
simplificadas ficam fora desta entrega. Todas as consultas filtram diretamente
por `organization_id` da sessão e nunca aceitam organização por parâmetro.

O summary inclui todos os tickets não excluidos fisicamente, inclusive
cancelados, e retorna cada status separadamente:

```json
{
  "total": 12,
  "pending": 3,
  "in_progress": 2,
  "waiting": 1,
  "completed": 5,
  "cancelled": 1,
  "overdue": 2,
  "average_resolution_hours": 6.25
}
```

`WAITING` não integra `in_progress`; ambos possuem contagens independentes. Uma
solicitação e atrasada quando possui prazo anterior ao instante UTC da consulta
e não está `COMPLETED` nem `CANCELLED`. A metrica não usa coluna persistida.

O tempo medio de resolucao usa somente tickets `COMPLETED` com
`completed_at`, conforme a formula:

```text
media((completed_at - created_at) em segundos) / 3600
```

O resultado e expresso em horas, arredondado para duas casas. Sem tickets
concluídos, retorna `null`. Os calculos usam timestamps UTC.

As distribuicoes retornam todos os valores de status e prioridade, inclusive
os que possuem contagem zero. Recentes são ordenados por `created_at desc` e
UUID decrescente. Maiores atrasos incluem somente tickets realmente atrasados,
ordenados pela duração decrescente, com `due_date` e `overdue_seconds`.

`recent` e `overdue` aceitam `limit` entre 1 e 50, com padrao 5. As respostas
usam dados resumidos de ticket, categoria e responsável, sem descrição ou dados
sensíveis. Agregacoes e medias são calculadas no banco; listas são limitadas e
carregam categoria e responsável na mesma query para evitar N+1.

## Recuperação de senha

Endpoints:

```text
POST /api/v1/auth/forgot-password
POST /api/v1/auth/reset-password
```

Solicitação:

```json
{
  "email": "ana@example.com"
}
```

E-mails são normalizados. A resposta e sempre `200` com a mesma mensagem,
independentemente de o e-mail existir, estar inativo ou não estar cadastrado:

```json
{
  "message": "Se o e-mail estiver cadastrado, enviaremos instrucoes para redefinir a senha."
}
```

Para usuários ativos, a API gera 32 bytes aleatorios com
`secrets.token_urlsafe`, armazena somente o SHA-256 hexadecimal e monta a URL
`FRONTEND_URL/redefinir-senha?token=...`. A validade e configurada por
`PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`. Uma nova solicitação inválida tokens
anteriores ainda não usados.

Redefinição:

```json
{
  "token": "token-recebido-por-email",
  "new_password": "NovaSenha123"
}
```

O backend calcula o hash do token recebido, bloqueia o registro durante a
transacao e válida expiracao, `used_at` e usuário ativo. Senha e `used_at` são
atualizados na mesma transacao. O token não autentica o usuário e não pode ser
reutilizado. Token inválido, expirado, usado ou associado a usuário inativo
retorna o mesmo erro `400 invalid_reset_token`.

### Envio de e-mail

`EMAIL_BACKEND=development` usa um adapter seguro que não envia mensagens e não
registra destinatario, URL ou token. `EMAIL_BACKEND=smtp` habilita o adapter
SMTP real. Host, porta, usuário, senha, remetente, TLS e timeout são definidos
somente por variáveis de ambiente; não existem credenciais hardcoded.

Para testes, `EmailSender` pode ser substituido por um fake por dependency
override. O fake captura a mensagem em memoria sem acessar rede.

O envio ocorre antes do commit do token para permitir rollback quando o adapter
falha. Existe uma pequena janela em que o SMTP pode aceitar a mensagem e o
commit posterior falhar; eliminar essa janela exige um outbox transacional, que
fica fora do MVP. Falhas são registradas apenas com mensagem genérica, sem
destinatario, URL, token ou credenciais.

## Testes

```powershell
pytest
```

Os testes carregam configuracoes de ambiente de teste e não devem usar banco de producao. A suite rapida usa SQLite em memoria para isolar dados por teste e manter repetibilidade. Essa escolha cobre os fluxos HTTP e regras de negocio, mas pode mascarar diferencas de PostgreSQL em tipos, enum e DDL.

Para validar migrations em PostgreSQL, configure uma URL explicita de teste:

```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg://taskflow_test:taskflow_test_password@localhost:5432/taskflow_test"
python scripts/validate_migrations.py
```

O script recusa URLs que não sejam PostgreSQL ou que não parecam apontar para banco de teste. O procedimento executa `upgrade head`, `downgrade base` e novo `upgrade head`.

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
