# Demo recording outline

Target length: 3 minutes 45 seconds. Record the real configured app; do not use the
browser smoke-test fixtures as model output. Keep credentials and account settings
out of the recording. Upload the finished recording and add its link to the README.

| Time | Action and narration |
| --- | --- |
| 0:00–0:25 | Open the public URL. Introduce the ecommerce schema and read-only purpose. Expand Users and Orders to show columns and relationships. |
| 0:25–1:05 | Ask “Show all customers and their states.” Point out SQL, explanation, and six result rows. Follow up with “Only California”; show the three matching users and preserved conversation. |
| 1:05–1:35 | Ask “Show orders with customer names.” Explain the declared foreign-key join. Copy SQL and export the results as CSV. |
| 1:35–2:05 | Submit “Debug: SELECT fullname FROM Users.” Show the corrected column and explanation of the original error. |
| 2:05–2:35 | Optimize a state-filter query. Show equivalent SQL and index suggestions in prose; explain that the app never executes schema changes. |
| 2:35–3:00 | Ask “Show the best customers” to demonstrate clarification, then an unrelated sports question and “Delete all users” to demonstrate refusal. |
| 3:00–3:30 | Briefly show the graph diagram and tests. Explain the exactly-one-SELECT AST rule, schema validation, read-only connection, safe function allowlist, and three-failure repair cap. |
| 3:30–3:45 | Show responsive layout, repository, README, and the public deployment URL. |

If the live model already generates valid SQL, do not invent a self-healing event.
Use the deterministic graph tests to demonstrate repair behavior separately and label
them as tests. Record only after the public deployment and live model checks succeed.
