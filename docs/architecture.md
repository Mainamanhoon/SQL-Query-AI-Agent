# Design notes

## Ownership and dependencies

`create_app` is the composition root. Its lifespan owns the HTTP client, database
service, validator, and compiled graph. Settings come from the environment, and
tests inject a different `LanguageModel` implementation. There is no global model
client or shared SQLite connection in node code.

FastAPI dependencies resolve application-owned services. LangGraph nodes receive
an immutable `AgentDependencies` container through bound function arguments.
Database connections are created inside execution and closed in `finally`, so
worker threads never reuse another request's connection.

## Responsibilities

| Component | Responsibility |
| --- | --- |
| Router | Classify request and detect refusal/clarification routes |
| Scope validator | Apply deterministic out-of-scope and destructive-request checks |
| Schema retrieval | Copy trusted DDL into state before generation |
| Optimization phase | Review validated SQL and prepare safe readability/performance guidance without executing DDL |
| Debug inspector | Validate supplied debug SQL and preserve the original error |
| Generator | Generate or repair a SQL candidate for the chosen intent |
| Validator | Enforce AST shape, identifiers, and supported joins |
| Semantic reviewer | Use a dedicated JSON-only LLM call to compare validated SQL with the request and prior context |
| Executor | Execute already validated SQL through the restricted database service |
| Explainer | Explain the successful query and debugging/optimization details |
| Terminal nodes | Return clarification, refusal, or retry-exhaustion text |
| API | Validate transport input and project safe output |
| React hook | Keep history, previous SQL, request state, and cancellation |

If a provider returns malformed or unsafe explanation JSON after SQL has already
validated and executed, the explainer uses a deterministic result-count fallback.
Provider transport failures still surface as provider errors; valid database work is
never discarded solely because model prose formatting failed.

The frontend uses `/chat/stream` for conversational turns. The stream sends a
processing event and explanation chunks, then emits SQL/results only in the final
event after the graph has completed validation and read-only execution. SQL and CSV
downloads are client-side Blob downloads; no write-capable database endpoint is
introduced. Every successful result also carries a SQLite `EXPLAIN QUERY PLAN`
summary, so cost guidance is deterministic and does not require an LLM claim about
performance.

`AgentState` is defined once in `models/agent.py` and exposed through `agent/state.py`.
`messages` uses LangGraph's `add_messages` reducer. All other fields use ordinary
last-update semantics. A new HTTP turn creates fresh transient state and carries
only conversation history and previous SQL forward.

## Validation details

SQLGlot parses the entire input before any execution. All nested nodes are inspected;
CTEs cannot hide a modifying statement. Identifier qualification uses the real
SQLite schema, expands stars, and resolves aliases and derived columns. Physical
tables are checked by scope so legitimate CTE names are not mistaken for missing
tables. Declared foreign keys are used to validate positive equality join predicates.
Computed-key, arbitrary self, natural, and Cartesian joins are deliberately outside
this assignment implementation's supported join subset.

Canonical SQL is regenerated from the checked AST, rather than executing a different
original string. A failed SQLite statement returns to generation with the canonical
SQL that actually failed. This matters because SQLGlot's accepted syntax is broader
than SQLite's executable syntax.

After AST/schema validation, the production semantic-review node makes a separate
JSON-only LLM call with a dedicated prompt. It can reject a syntactically valid but
meaningfully wrong candidate, such as a California request without a California
predicate. The rejection increments the same bounded retry counter and includes the
reviewer's reason in the next generator context. The reviewer never authorizes SQL,
executes SQL, or replaces the AST and database safety boundary. Test graphs can omit
this injected reviewer to keep deterministic node tests focused on one responsibility.

The metadata connection accepts only application-controlled discovery queries. It
never accepts generated SQL. Runtime query connections are independently read-only
and have an authorizer installed before executing any candidate. A SQLite
primary-key-only read can produce a READ callback with an empty column and no
database name; the callback permits that form only for known application tables.

The public SQL boundary accepts SQLite, PostgreSQL, and MySQL read-only syntax. The
validator checks the requested source dialect first, then SQLGlot-transpiles a valid
candidate to SQLite before the restricted executor sees it. This provides a portable
SQL surface while keeping one hardened execution engine and one trusted schema.

## Retry semantics

`retry_count` counts failures, not generator calls. Both validation and execution
increment it once per failed attempt. Values 1 and 2 loop to generation. Value 3
routes to fallback, clears candidate SQL/results, and returns a controlled error.
The graph recursion limit is an additional safeguard, not the primary stop condition.

Clarification and rejection do not call the generator. Debug requests pass through a
small inspection node first: an invalid supplied query becomes `original_error` and
is then repaired by the generator, so a successful response contains both the fixed
SQL and the diagnosis. Obvious destructive requests
are refused before calling the model. Prompt-based routing is an additional layer;
AST validation and database authorization do not depend on that classification.

## Design patterns

- **Dependency inversion:** nodes depend on a `LanguageModel` protocol; the HTTP
  adapter and scripted test implementation share that contract.
- **Application factory:** startup configuration and resources are explicit and
  testable without global environment mutation.
- **State machine:** conditional graph edges make retries and termination explicit.
- **Adapter:** the provider-specific HTTP format stays in one service.
- **Single responsibility:** model generation and SQL execution have separate nodes
  and separate services.
- **Shared prompt assembly:** policy, schema, conversation, and repair context are
  assembled once and reused by model-backed nodes.

## Deployment shape

Compose runs a non-root Python backend and an unprivileged nginx frontend. The
backend filesystem is read-only. nginx forwards `/api/` requests internally.
The root image instead serves compiled frontend assets through FastAPI and exposes
the same API on `/api/`. Both images seed the sample database at build time; runtime
requests cannot modify it. No persistent database volume is needed for this fixed
sample dataset.
