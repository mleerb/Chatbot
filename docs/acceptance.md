# Final acceptance — 05/11

The four approved completion phases are finished, with the limitations below. This is acceptance for a trusted local/SSH workspace, not a public-service security certification or a claim that every optional provider works. No commit was made. No production configuration, provider credentials, Docker healthchecks, accounts or existing snapshots were changed during Phase 4.

## Results and evidence

| Area | Evidence | Result and boundary |
| --- | --- | --- |
| Backend regression | 320 tests run in the existing app image with current tests/scripts mounted read-only; live parser/embedding/tracing credentials disabled | 296 passed, 24 skipped: 23 optional PostgreSQL cases and the explicit recovery integration test. Includes actual backend auth/session/conversation/file/citation isolation, stream/Stop, timeout, capacity and trace tests. Not all database tests were rerun against PostgreSQL in this phase. |
| Frontend | Typecheck, production build, 10 unit tests, all 39 synthetic-backend browser cases | Passed; account/guest flow, files/revisions, escaped citations, previews, streaming/Stop, upload retries, draft preservation and desktop/mobile layouts. The browser backend is synthetic, so backend authorization is independently tested. |
| Running deployment | Desktop/mobile landing → guest workspace → refresh; landing/chat/internal health HTTP checks | Passed; no external browser requests, HTTP/JavaScript errors, paid model calls or production account-history writes. All three services healthy, loopback binding preserved. |
| Provider-backed document behavior | Earlier same-day [document audit](document-audit.md), eight real synthetic chat cases | Vietnamese DOCX, long PDF page retrieval/citations, missing information, conversation isolation, multiple files, corrupt/unsupported files and scanned-PDF OCR passed. Not rerun or billed again in Phase 4; this is sampled evidence, not universal model/OCR accuracy. |
| Storage recovery | [Phase 3](storage.md) live backup restore plus nonempty synthetic integration test | Passed previously; no repeat production backup or existing-snapshot deletion in Phase 4. |
| Langfuse redaction | Newly exported ordinary and streamed Deep Agents turns, real `read_page` tool, deterministic fake model; observations read back through CLI with every metadata key expanded | Passed with `LANGFUSE_TRACE_CONTENT=false` in isolated worker processes; see below. |
| Health tracing | Newly observed 120-second live window with four explicit `/health` requests and normal Docker healthchecks unchanged | Zero observations; synthetic exporter controls visible immediately before/after. Bounded evidence, not a guarantee about future code/config changes. |
| Semantic embeddings | Gateway returned HTTP 400 for the unprefixed `text-embedding-3-small`; disabled by the operator on 09/11; switched on 11/11 with `nano/text-embedding-3-small` | Working since 11/11: probe, large guest upload and synthetic meaning-only searches passed. Phase 4 itself ran with embeddings unavailable. |

## Live Langfuse redaction audit

`tests/audit_tracing.py` is outside unittest discovery and requires an explicit opt-in:

```bash
AUDIT_LIVE_TRACING=1 python3 tests/audit_tracing.py
```

Requires host Python 3.11+, Docker/Compose, Node/npm access to `npx langfuse-cli`, configured live Langfuse credentials in the running backend, and an otherwise idle observation window. It uses the deployed/pinned Langfuse 4.17.0 SDK intentionally to test this installation rather than upgrading dependencies. Current Langfuse best-practices and CLI option documentation were reviewed before testing. The configured web fetch route returned a 402, so public documentation was fetched directly with curl. Querying uses the modern observations API, not deprecated traces endpoints.

The host passes credentials privately through subprocess environment variables; it never prints them, writes them to source, or exposes them to the frontend. Workers run via `docker compose exec` in separate Python processes. They do not start an HTTP server, initialize/query production persistence, use the paid chat model/parser/embedding provider, create workspace upload snapshots or restart the running backend. Synthetic files and sessions live only in worker memory. File ingestion/OCR is covered separately by the earlier document audit; this check covers tracing of the file context/tool path.

Each worker forces content tracing off and disables workspace exports/embeddings in its own process before using the real `answer_question`/`stream_answer`, Deep Agents, `conversation_messages` and session-bound `read_page` tool. A deterministic fake chat model asserts receipt of unique message and file-text sentinels and the file sentinel in the tool response. It returns a synthetic answer marker and file marker, so output masking is tested too. Streaming actually emits text chunks. A guest-equivalent `trace=False` execution yields no trace ID; the CLI session query confirms only the two intended traces exist.

The CLI fetches all observation field groups, follows cursor pagination and re-queries each page with all returned metadata keys explicitly expanded, avoiding the API's default 200-character metadata truncation. Every returned nested field is scanned for every sentinel, not just the root question/answer. The audit requires exactly two named generations and one `read_page` tool per trace, redacted root/model/tool input/output, retained model and usage fields, one root and no dangling parents. Structural LangGraph/model/tools wrappers remain; successful routine middleware noise is absent. Content opt-out intentionally sacrifices prompt/output visibility; metadata, model/timing and token usage remain. This is not anonymization of every identifier, and it says nothing about model-provider retention.

Successful full-metadata run:

- Ordinary tool-use trace: `05be8c1b6e4ffc206ff37e39fc745b89`.
- Streamed tool-use trace: `71832106990fd8022eb44fb5e5e206b6`.
- Each has 8 observations: root `chat-response`, `LangGraph`, two `model` wrappers, two `generate-response` generations, `tools` wrapper and `read_page`.
- All message/file/answer sentinels absent across returned observations; root/model/tool I/O visibly redacted.
- All parents present, model `synthetic-acceptance` retained. Usage is deliberately synthetic: 34 input + 10 output tokens per turn, not a billable provider measurement or pricing check.
- Private summary: the run wrote `.workspace/acceptance/<run-id>/report.json` (directory 0700/file 0600) with IDs/results only, not content markers or raw observations/credentials. The 05/11 report was deleted on 11/11 at the operator's request; the results above are the record.
- Exported synthetic observations remain in the configured Langfuse project; no deletion or retention change was performed. Early fixture/CLI/report-path iterations also created synthetic observations; they must not be mistaken for user turns. The final successful report is authoritative. The fixture initially lacked chunk streaming, the CLI JSON envelope needed `body` handling, and the older audits directory had nonprivate mode, so a new private `acceptance/` directory was used without modifying or deleting existing files.

Unit tests in `tests/test_trace_audit.py` cover incomplete nesting, wrong tool/model/usage, missing I/O masking, a file marker buried in long nested metadata, metadata expansion/pagination, API failures and opt-in gating. They do not make network calls.

## `/health` while tracing is enabled

The final run's idle window was `2026-11-05T04:10:32.986951Z` through `04:12:32.987163Z`. Four explicit internal health requests returned 200, alongside the unchanged 30-second Docker healthcheck schedule. The observations query for that window returned zero rows. A synthetic explicit root observation created from a separate process with the live tracing configuration was visible on both sides (`f5ac6f5539413c71e1941aa998b22815` and `a1ccc306bbd8bb49bb6f6554329dbbf8`); the exporter/project was not simply disabled. Read-back allowed an ingestion grace period. Offline FastAPI tests additionally capture raw/exported spans and verify health/polling create none while a fake-model chat endpoint creates one nested trace.

The read-back controls use the same deployment configuration/SDK/export policy but a separate process; they do not prove delivery from an otherwise idle in-process production SDK. Together with startup initialization, current source-level telemetry disabling and raw-span tests, they provide bounded live evidence without triggering a paid production chat. If unrelated account traffic occurs during a rerun, the strict zero-observation assertion can fail even when health itself is untraced; investigate rather than silently ignore observations.

## Important deployment caveats

1. **Live content tracing is still enabled.** `LANGFUSE_TRACE_CONTENT=true` before and after this audit, unchanged as required. Redaction was proved only when false in isolated workers. Ordinary traced account turns can currently export message, prompt, answer and readable file/tool content to Langfuse. To enable privacy-by-default on this machine, a separately approved configuration change and backend recreation are needed. Guests bypass Langfuse chat callbacks, but AI/parser/search providers still process their inputs under their own policies.
2. **Semantic embeddings were off during Phase 4.** The gateway rejected the unprefixed model name, and the operator disabled embeddings on 09/11. On 11/11 they were switched on with the gateway-prefixed `nano/text-embedding-3-small` and checked with synthetic meaning-only searches; see [setup](setup.md). The multilingual document audit has not been rerun with embeddings on. Paid chat and sampled OCR/file citation paths previously passed; they do not fix embeddings.
3. **Persistent inspection copies are enabled for both accounts and guests.** Extracted text/chunks survive logout, guest cleanup and app-side deletion on this machine, by explicit operator choice. Manual exact-ID cleanup exists; backups may retain further copies. No data was erased during acceptance.
4. **Keep the app local/SSH-only.** Process-local login sessions/rate limits, no password-reset/email verification flow, and no public deployment hardening remain. Original uploads have admission limits, not total disk/decompression/generated-file quotas. Provider timeouts are operation/inactivity limits, not strict whole-turn deadlines. Stop is best-effort at the next received chunk, not guaranteed provider cancellation/refund. Archive restore validation is not a production cutover or browser login rehearsal.

All approved phases have been implemented and checked within these boundaries. Embedding-provider repair, a change to live content tracing, public deployment, automatic retention and any commit remain outside this completed scope.
