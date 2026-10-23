# QueryDesk

A conversational, read-only SQL assistant for a small ecommerce database.

## Development

Requires Python 3.10+ and Node.js 22.12+.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e "./backend[dev]"
Copy-Item .env.example .env
.\.venv\Scripts\python backend/seed_db.py
.\.venv\Scripts\python -m pytest backend/tests
```

On macOS/Linux, use `.venv/bin/python` instead. The seed script creates
`ecommerce.db` in the current directory and preserves an existing sample database.
It creates 6 users, 6 products, 6 orders, and 10 order items. Money is stored as
integer cents; dates use ISO format. All data is fictional.

## Database boundary

The application uses `mode=ro` connections and an authorizer that permits only
`SQLITE_SELECT` and reads from known application tables. Extension loading is
disabled. Query execution has a deadline and results have a configurable row cap.
Schema discovery uses fixed internal queries on a separate read-only connection.
The seed script is the only database writer.

The strict authorizer currently rejects all SQL functions, including `COUNT`,
`SUM`, and `LOWER`. This follows the requested two-action allowlist; supporting
analytics requires an explicitly approved safe-function allowlist.

## Structure

- `backend/app/api`: HTTP routes and dependency injection.
- `backend/app/agent`: graph, state imports, nodes, and prompts.
- `backend/app/services`: database, schema, validation, and LLM integrations.
- `backend/app/models`: Pydantic contracts and the shared TypedDict state.
- `backend/tests`: database, validator, graph, and API tests.

Implementation is in progress. Public deployment and demo video are not yet available.
