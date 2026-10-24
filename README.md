# QueryDesk

A conversational SQL assistant for a small ecommerce database. Ask a question,
refine it in a follow-up, or paste a query for debugging or optimization. Generated
SQL is checked with SQLGlot and executed through an independently restricted SQLite
connection before it is returned to the browser.

Source, tests, and Docker images are included. No model responses are simulated in
the application.

## Setup and run

The project runs as a Docker Compose stack or a single Docker image. The backend owns
the model key; the frontend never receives it.

### 1. Configure the model

Create a local environment file and set a model supported by your OpenAI-compatible
provider. For OpenRouter, for example:

PowerShell:

```powershell
Copy-Item .env.example .env
notepad .env
```

macOS/Linux:

```sh
cp .env.example .env
nano .env
```

```dotenv
LLM_API_KEY=your-provider-key
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=moonshotai/kimi-k3.1-pro
LLM_MAX_TOKENS=1000
```

### 2. Run with Docker Compose

Requires Docker Desktop or Docker Engine with Compose. From the repository root:

```sh
docker compose up --build -d
```

Compose starts the backend on port 8000 and the Vite frontend on port 8080. Open
`http://localhost:8080`; API docs remain at `http://localhost:8000/docs`.
The backend image seeds its own database during the image build, so no database
server or migration command is required. View logs or stop the stack with:

```sh
docker compose logs -f
docker compose down
```

### 3. Build the combined production image

The root `Dockerfile` builds the frontend and serves it from FastAPI. This is useful
for a single-service deployment:

```sh
docker build -t querydesk .
docker run --rm -p 8080:8000 --env-file .env querydesk
```

Open `http://localhost:8080`. The container honors the platform `PORT` variable and
also exposes `/health`, `/schema`, `/chat`, and `/docs` under the same origin.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_API_KEY` | empty | Backend-only model credential; never sent to the frontend |
| `LLM_MODEL` | empty | Model ID from your chosen provider |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible chat-completions base URL |
| `LLM_TIMEOUT_SECONDS` | `30` | Deadline for each provider request |
| `LLM_MAX_TOKENS` | `1000` | Maximum completion budget per model call |
| `DATABASE_PATH` | `./ecommerce.db` | Existing SQLite file; containers set their own absolute path |
| `QUERY_TIMEOUT_SECONDS` | `2` | SQLite progress-handler deadline |
| `QUERY_ROW_LIMIT` | `200` | Returned row cap, with visible truncation status |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | JSON array of allowed frontend origins |
| `FRONTEND_DIST` | unset | Optional static frontend directory for single-service deployment |

The provider must support `/chat/completions`, JSON-object response mode, and
`max_tokens`. The adapter is replaceable through the `LanguageModel` protocol;
nodes do not depend on a vendor SDK. Conversation and schema context are sent to
the configured provider; result rows are not sent for explanation.

## Architecture

```mermaid
flowchart LR
    UI[React + TypeScript + Tailwind] --> API[FastAPI /chat]
    API --> G[LangGraph workflow]
    G --> M[Injected language model]
    G --> V[SQLGlot AST + schema validator]
    V --> DB[Read-only SQLite service]
    DB --> DATA[(ecommerce.db)]
    S[Trusted schema extraction] --> V
    S --> M
```

```text
backend/
  app/api/        Routes and dependency resolution
  app/agent/      State import, graph, single-purpose nodes, prompts
  app/services/   SQL validation, schema extraction, database execution, LLM adapter
  app/models/     Pydantic input/output schemas and AgentState TypedDict
  tests/          Validator, database, graph, and HTTP tests
  seed_db.py      Separate sample-data writer
frontend/
  src/components/ ChatWindow, SQLPanel, ExplanationBox, ResultsTable
  src/hooks/      Conversation state and request cancellation
  src/services/   Typed API client and safe CSV export
docs/             Schema, workflow/design notes, demo script, evaluation checklist
```

### LangGraph validation loop

```mermaid
flowchart TD
    A[Router: query / debug / optimize / clarify / out of scope] -->|Destructive or unrelated| R[Refuse]
    A -->|Missing information| C[Ask for clarification]
    A -->|Query, debug, optimize| G[Generate using history and previous_sql]
    G --> V[Validate AST, identifiers, and joins]
    V -->|Valid| E[Execute through restricted SQLite]
    V -->|Invalid| F[Increment retry_count]
    E -->|Database error| F
    F -->|Count below 3| G
    F -->|Count reaches 3| X[Graceful fallback]
    E -->|Success| P[Explain query and task-specific changes]
```

One initial attempt and two repair attempts are permitted. Every failed validation
or execution increments the same counter exactly once. The next generator call gets
the failed SQL and explicit error, alongside the original request. A separate graph
recursion limit guards unexpected control-flow bugs. Provider failures return a 503
instead of pretending that a SQL correction can repair model availability.

Generation uses intent-specific instructions for ordinary questions, debugging,
and optimization. Every resulting candidate goes through the same validation and
execution path. Debugging includes an explanation of the original error; optimization
provides prose suggestions without index-creation DDL. See the actual
[prompts](backend/app/agent/prompts.py) and [design notes](docs/architecture.md).

### Safety controls and deliberate limits

1. Parse all statements with `sqlglot.parse(..., read="sqlite")`; require exactly one
   statement whose root is `Select`. Reject writes, commands, external sources, and
   nested DML/DDL. A successful parse alone is not treated as proof of executable SQL.
2. Resolve aliases, CTEs, subqueries, and columns against the extracted schema. Joins
   must connect sources through declared foreign-key equalities. Cartesian joins,
   recursive CTEs, and unsupported relationship patterns are rejected.
3. Execute with a fresh `mode=ro` connection, extension loading disabled, and a
   deny-by-default authorizer. Only `SQLITE_SELECT` and application-table
   `SQLITE_READ` actions are allowed. System tables and attached databases are blocked.
4. Use a progress-handler deadline and fetch at most one row beyond the display cap.
   The response reports truncation. Connection lock timeout is configured separately
   from the execution progress check.
5. Return SQL only after validation and execution succeed. Rejected candidates stay
   internal. Client messages cannot supply a system role; history and previous SQL
   remain untrusted context. CSV exports escape formulas and quoted cells.

**The requested two-action authorizer blocks SQL functions**, including `COUNT`,
`SUM`, `AVG`, date functions, and `LOWER`. Such requests cannot currently produce
successful analytics results. Enabling them requires explicit approval for a small
`SQLITE_FUNCTION` allowlist. The application does not silently relax this requirement.
Top-level `UNION`, `INTERSECT`, `EXCEPT`, and `EXPLAIN` are also rejected by the
SELECT-root rule. These are intentional supported-language limits, not claims that
those operations are inherently destructive.

Guardrails prevent writes; they do not prove that every LLM interpretation matches
business intent. Live model accuracy must be checked with the evaluation cases below.

## Database

The deterministic seed contains 28 fictional rows: 6 users, 6 products, 6 orders,
and 10 order items. `Users.state` supports the California follow-up example.
`Orders.user_id`, `OrderItems.order_id`, and `OrderItems.product_id` declare relationships.
Prices use integer cents; timestamps use ISO date strings. Current product prices
and historical item prices are separate fields.

The seed script preserves an existing sample database and refuses to overwrite an
unexpected schema. See [sample DDL](docs/schema.sql). The generated `.db` file is
ignored by Git and reproduced locally or during the image build.

## API

`POST /chat` accepts:

```json
{
  "message": "Only California",
  "history": [
    {"role": "user", "content": "Show all customers"},
    {"role": "assistant", "content": "Here are the customers.", "sql": "SELECT name, state FROM Users"}
  ],
  "previous_sql": "SELECT name, state FROM Users"
}
```

Responses include `status`, `intent`, `generated_sql`, `is_valid`, `retry_count`,
`explanation`, `original_error`, `optimization_tips`, and positional `query_results`.
Status is `success`, `clarification`, `rejected`, or `error`. SQL is null for
unsuccessful responses. `/schema` exposes the sample schema; `/health` reports
database readiness and model configuration presence. `/api/*` aliases support the
single-service image. Model configuration presence is not a live-provider health test.

Conversation history lives in browser memory and is sent with each turn. This avoids
shared server conversation state and cross-user leakage; a page refresh starts a new
conversation. Selecting an older result only changes the displayed result, not the
latest conversational query. New conversation aborts pending client requests.

## Verification

```powershell
.\.venv\Scripts\python -m pytest backend/tests -q
.\.venv\Scripts\python -m ruff check backend
cd frontend
npm run build
npm test
```

Current checks: **70 backend tests and 7 frontend tests**. Backend tests use the real
seeded SQLite database and a scripted model, including repair after AST/schema and
SQLite errors. Frontend tests exercise the actual HTTP client with controlled
responses. These tests do not establish live LLM accuracy.

With the API and frontend running, `node scripts/browser-smoke.mjs` from `frontend/`
checks desktop/mobile layout, schema loading, results, refusal, reset, and overflow.
It uses installed Microsoft Edge by default; set `BROWSER_CHANNEL=chrome` if needed.
Chat responses in that browser test are explicitly HTTP fixtures. Screenshots go to
the ignored `artifacts/browser/` directory. CI runs backend tests and frontend build/tests.

See [evaluation cases](docs/evaluation.md) for live model acceptance checks.

## Assumptions

- The assignment PDF supplies no concrete schema, so the requested four-table
  ecommerce schema is the source of truth. “Customers” means rows in `Users`.
- This is a sample-data assignment app, not an authenticated multi-tenant product.
- SQLite is the only supported SQL dialect. Streaming and multiple dialects were
  not added because correctness and the required guardrails take priority.
- Optimization recommendations are not presented as measured performance gains.
- The strict function restriction remains in place until explicitly changed.
