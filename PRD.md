# PCM — Private Content Manager
## Product Requirements Document (PRD)

**Status:** Draft v1.0  
**Primary interface:** Private Telegram bot using Python + Pyrogram  
**Initial runtime:** Google Colab notebook (bot + worker prototype)  
**Repository:** https://github.com/Telebotfaroff/PCM

## 1. Executive Summary

PCM is a private, modular download and upload manager controlled through Telegram. A user sends one or more URLs; PCM analyzes and normalizes them, resolves supported redirects, identifies the likely website or cloud provider, classifies the content, chooses a matching scraper or extractor, validates the result, and then downloads or transfers the content to configured destinations.

PCM combines URL intelligence, reusable provider plugins, download and media-processing tools, upload adapters, queue management, and worker recovery. Its architecture must let new scrapers and storage providers be added without rewriting the Telegram bot or the core job pipeline.

The initial design separates a Telegram control bot from a Google Colab worker. Colab is temporary and cannot guarantee continuous uptime, so the bot must report worker availability accurately and job state must persist outside Colab's temporary filesystem.

## 2. Vision and Goals

### Vision
One private control point for identifying URLs, retrieving media, processing files, and uploading to one or more destinations.

### Goals
- Detect supported website pages, direct media URLs, redirect/shortener links, and cloud-share links.
- Reuse existing website-specific scraper logic through adapters where practical.
- Select extractors using provider matching, declared capabilities, validation, and bounded fallbacks.
- Support Telegram, GoFile, and additional upload destinations through interchangeable adapters.
- Show download and upload progress separately, including speed and ETA where measurable.
- Prevent disk exhaustion through bounded concurrency, queue backpressure, and cleanup policies.
- Recover or safely retry jobs after worker interruption.
- Keep credentials, session data, and signed URLs out of source control and ordinary logs.
- Make providers independently testable and configurable.

### Non-goals for the first release
- Guaranteed 24/7 operation on Google Colab.
- Guaranteed extraction from every website or unsupported/protected URL.
- A public multi-tenant SaaS service.
- A full web dashboard before the Telegram workflow is stable.
- Bypassing authentication or access controls; providers should use supported access and APIs.

## 3. Users and Core Use Cases

The initial user is the project owner using PCM privately through Telegram.

Core use cases:
1. Send a URL and automatically identify the provider and content type.
2. Submit multiple URLs as a batch.
3. View metadata and select quality/format when options are available.
4. Choose Telegram, GoFile, or both as upload destinations.
5. Monitor separate download and upload progress.
6. Retry an upload without downloading the same file again when the file remains available.
7. View, cancel, retry, and inspect jobs.
8. Add a new scraper or cloud provider without changing the core pipeline.
9. Recover job state after a Colab runtime restart.

## 4. Product Principles

- **Resolver first:** URL analysis is a separate, testable module.
- **Provider plugins:** Site-specific behavior stays out of Telegram command handlers.
- **Validated results:** A provider match is a hypothesis; extracted sources must be checked.
- **Separate stages:** Resolution, download, processing, and upload have distinct states.
- **Bounded work:** Network requests, queues, retries, and fallbacks have explicit limits.
- **Honest status:** Never report success before the relevant operation confirms success.
- **Recoverable state:** Persist job metadata outside temporary worker storage.
- **Secure by default:** Validate URLs and redirects, protect secrets, and constrain resource use.

## 5. Functional Requirements

### 5.1 Telegram Bot and Access Control

- **FR-001 Private access:** First release supports owner-only access via configured Telegram user ID. Unauthorized users cannot submit jobs or use admin commands.
- **FR-002 URL input:** Accept URLs in ordinary messages and extract multiple URLs from one message.
- **FR-003 Commands:** `/start`, `/download URL`, `/queue`, `/status [job_id]`, `/cancel job_id`, `/retry job_id`, `/settings`, `/providers`, and `/help`.
- **FR-004 Interactive choices:** Use inline keyboards for available qualities and destinations. Allow configured defaults for automatic mode.
- **FR-005 Progress:** Report download and upload progress separately, including percentage when measurable, speed, bytes, ETA when calculable, and current stage. Throttle message edits.
- **FR-006 Results:** Return destination links and summarize successes, failures, and skipped destinations.

### 5.2 URL Intelligence and Resolver

- **FR-010 Parsing:** Extract, validate, and normalize URLs while preserving query parameters needed by signed links and share pages.
- **FR-011 Redirects:** Follow redirects with configurable hop/time limits; detect loops, invalid destinations, and unsupported schemes. Redact secrets in diagnostic logs.
- **FR-012 Provider matching:** Match hostname and path against a provider registry. Prefer exact site-specific matches over generic extractors where appropriate.
- **FR-013 Classification:** Support `video_page`, `direct_media`, `direct_file`, `hls_stream`, `dash_stream`, `cloud_share`, `image`, `playlist`, `webpage`, and `unknown`. Include confidence/evidence when uncertain.
- **FR-014 Metadata:** Extract title, thumbnail, duration, file size, MIME type, quality options, and provider name when available. Missing optional metadata must not automatically fail a usable source.
- **FR-015 Strategy planner:** Rank compatible strategies by provider match, capabilities, reliability, authentication requirements, and validation evidence.
- **FR-016 Fallbacks:** Record typed failures and try the next compatible strategy within configured attempt, time, and resource limits. Do not blindly run every extractor.
- **FR-017 Validation:** Check source schemes and plausible media/file characteristics before scheduling transfer. Mark expiring sources as ephemeral.
- **FR-018 Unknown URLs:** Return detected domain, attempted strategies, failure category, and a useful next action.
- **FR-019 Safe requests:** Block loopback, private, link-local, and other prohibited IP ranges; revalidate DNS results and each redirect destination to reduce SSRF risk.

### 5.3 Provider Plugin System

- **FR-020 Contract:** Every provider declares an ID, version, matching rules, supported content types, capabilities, and extraction behavior.
- **FR-021 Categories:** Website scrapers, generic extractors, cloud-share adapters, and upload destination adapters.
- **FR-022 Isolation:** Provider errors must not crash the bot or scheduler. Apply per-provider timeouts and bounded retries.
- **FR-023 Registry:** Providers can be enabled/disabled through configuration; expose status and diagnostics to the owner.
- **FR-024 Existing scrapers:** Wrap existing project code after inspecting its interface, dependencies, and reliability; do not assume it can be imported unchanged.
- **FR-025 Expiring sources:** Do not store signed, IP-bound, cookie-bound, or short-lived media URLs as permanent metadata. Store durable page/share references and reacquire ephemeral URLs when needed.

### 5.4 Download and Media Processing

- **FR-030 Engines:** Provide adapters for `yt-dlp`, `aria2c`, and native HTTP streaming where appropriate.
- **FR-031 Quality:** Offer only qualities actually reported by the extractor; support best-available as a configurable default.
- **FR-032 Streams:** Detect supported HLS/DASH sources and use compatible tools where technically supported.
- **FR-033 FFmpeg:** Support optional merging/remuxing and configured processing; avoid unnecessary transcoding.
- **FR-034 Resume:** Resume downloads when supported; otherwise restart safely and report the limitation.
- **FR-035 Validation:** Check file existence, nonzero size, and expected media/container properties where practical.
- **FR-036 Large files:** Support configurable splitting when a destination requires it and track parts/results independently.

### 5.5 Upload Destinations

- **FR-040 Adapter interface:** Each uploader supports capability checks, upload execution, progress events, result links, and typed errors.
- **FR-041 Initial providers:** Prioritize Telegram and GoFile. Add Streamtape and Doodstream after verifying current APIs, credentials, and limits.
- **FR-042 Modes:** Support `telegram_only`, `gofile_only`, and `both`.
- **FR-043 Partial success:** Track each destination independently; one failed upload must not erase another destination's success.
- **FR-044 Retry:** Retry a failed destination without repeating a successful download when the file remains available.
- **FR-045 Direct transfer:** Prefer remote-to-remote transfer only when supported and verifiable; otherwise download locally then upload.
- **FR-046 Telegram:** Support configured target chats/channels and the selected Telegram library. Keep bot-token and user-session modes explicit.
- **FR-047 Link verification:** Save a result link only after the provider confirms completion and returns a usable result.

### 5.6 Queue, Concurrency, and Storage

- **FR-050 Queue states:** Track pending, active, completed, failed, cancelled, and recovery-needed jobs.
- **FR-051 Concurrency:** Configure download and upload concurrency independently. Initial suggested defaults: two downloads and two uploads, subject to worker capacity.
- **FR-052 Backpressure:** Stop scheduling downloads when the upload queue or temporary storage reaches configured limits.
- **FR-053 Disk limits:** Monitor free space and file size; defer or reject jobs that exceed safety limits.
- **FR-054 Cleanup:** Delete temporary files only after required uploads succeed or after a configured retention period and failure policy. Never remove files used by active uploads.
- **FR-055 Duplicates:** Detect duplicates using normalized source identity and, where available, file hashes. Signed URLs for the same page should not automatically count as separate content.
- **FR-056 Cancellation:** Stop work cooperatively, terminate child processes safely, and preserve completed destination results.

### 5.7 Persistence and Colab Worker

- **FR-060 Persistence:** Store job state, stage, attempt count, destination results, timestamps, and error summaries outside Colab's temporary disk.
- **FR-061 Heartbeat:** Worker periodically reports health, capacity, active jobs, and version. Bot distinguishes offline, idle, busy, and unhealthy states.
- **FR-062 Job claiming:** Use atomic claims or leases to prevent duplicate processing across workers.
- **FR-063 Recovery:** Reconcile interrupted jobs at startup. Resume supported operations, retry safe operations, and flag ambiguous operations rather than blindly duplicating uploads.
- **FR-064 Offline behavior:** The bot remains responsive when Colab is offline and labels jobs as waiting, not running.
- **FR-065 Communication:** Use an authenticated job API or explicit protocol. Avoid unsynchronized writes to a shared JSON file.

## 6. Non-Functional Requirements

- Reliability: one provider failure must not crash unrelated jobs.
- Observability: structured logs include job ID, provider, stage, duration, and error category.
- Security: secrets are stored in environment variables or a secret manager, never committed.
- Privacy: restrict access and minimize retention of sensitive URLs, cookies, tokens, and media.
- Performance: use streaming I/O where practical; do not load large files fully into memory.
- Resource control: enforce timeouts, queue limits, concurrency caps, and disk thresholds.
- Maintainability: typed interfaces, modular adapters, and provider-specific tests.
- Portability: worker runs in Colab initially and can later move to a VPS or persistent worker.
- Transparency: distinguish unsupported content from temporary failures and show accurate progress.

## 7. Proposed Architecture — Python First

### Initial MVP runtime
- Python 3.11+ (verify compatibility of pinned dependencies during implementation).
- Pyrogram for Telegram bot updates, commands, callbacks, message handling, and Telegram media operations.
- A Google Colab notebook runs the initial private bot and worker in one prototype runtime to minimize deployment complexity.
- Async-first design using `asyncio`; use bounded subprocess wrappers for tools such as `yt-dlp`, `aria2c`, and FFmpeg.
- Keep bot handlers thin: they validate input and create jobs; provider resolution and transfers run in separate modules/tasks.
- Use environment variables or Colab Secrets for credentials. Never commit bot tokens, API hashes, session strings, cookies, or provider keys.

### Future deployment boundary
The first prototype may run both bot and worker in Colab. Colab runtimes can disconnect or be reclaimed, so this is not a 24/7 guarantee. Keep the control logic, worker loop, and persistence interfaces separable so a later always-on host can run the bot/API while Colab or a persistent worker handles heavy transfers. Do not claim jobs are actively processing when the Colab runtime is offline.

### Python processing plane
- `yt-dlp` for supported media extraction and downloads.
- `aria2c` for supported HTTP downloads where segmented downloading is appropriate.
- FFmpeg for optional merge/remux and media validation.
- `httpx` or `aiohttp` for HTTP requests and streaming, selected consistently.
- Pyrogram upload adapter for configured Telegram chats/channels.
- GoFile adapter as the initial external cloud destination; other destinations are added after API and limit verification.
- Bounded queues, independent download/upload concurrency, disk backpressure, retry policies, and cleanup.

### Core modules
- URL parser/normalizer and safe redirect resolver.
- Content classifier and strategy planner.
- Provider registry with typed capabilities/errors.
- Download engine and upload destination adapters.
- Job scheduler, progress events, persistence interface, recovery, and health status.
- Pyrogram handlers and inline keyboards.

### Persistence decision
Do not use GitHub JSON as a concurrent live queue shared by independent processes. It may hold provider manifests, configuration snapshots, or backups. The first prototype may use SQLite for local development/testing, but Colab's local disk is ephemeral; production-like job state must live in durable remote storage before recovery can be trusted. Choose a remote transactional store before implementing cross-runtime job claims and leases. Avoid introducing MongoDB or Redis unless explicitly chosen; the storage decision remains open.

## 8. Proposed Python Repository Structure

```text
PCM/
├── pcm/
│   ├── bot/                 # Pyrogram handlers, callbacks, keyboards
│   ├── core/                # Config, schemas, typed errors, logging
│   ├── resolver/            # URL parsing, redirects, classification
│   ├── providers/           # Provider contracts and registry
│   ├── downloads/            # yt-dlp, aria2c, HTTP adapters
│   ├── uploads/              # Telegram, GoFile and future adapters
│   ├── jobs/                 # Queue, lifecycle, retries, recovery
│   └── storage/              # Persistence interface and implementations
├── providers/
│   ├── websites/
│   ├── generic_extractors/
│   ├── cloud_links/
│   └── destinations/
├── colab/
│   └── PCM_Worker.ipynb     # Initial run/setup notebook
├── tests/
│   ├── resolver/
│   ├── providers/
│   ├── jobs/
│   └── integration/
├── config/
├── docs/
├── .env.example
├── requirements.txt
├── pyproject.toml
├── README.md
└── PRD.md
```

This is a proposed target structure; files should be added incrementally as each phase is implemented. The Colab notebook should bootstrap from the repository rather than become the only source of truth for application code.

## 9. Telegram UX and Job Lifecycle

### Example flow
1. User sends one or more URLs.
2. PCM validates URLs and creates resolution jobs.
3. Resolver identifies provider candidates and classifies content.
4. PCM presents metadata, quality choices, and destinations when needed.
5. User confirms or configured defaults apply.
6. PCM queues download or direct transfer.
7. Worker reports download progress.
8. PCM validates the file and begins uploads.
9. Each destination reports independent progress and completion.
10. PCM returns result links and cleans up according to policy.

### Job states
Primary flow: `received → resolving → awaiting_selection → queued → downloading → validating → uploading → completed`.

Other states: `failed`, `cancelled`, `waiting_for_worker`, `retry_wait`, `recovery_needed`, and `partial_success`.

Each destination has its own upload state. Overall success is derived from configured required destinations, not one global boolean.

## 10. Proposed Environment Variables

```dotenv
# Telegram bot identity and API access
TELEGRAM_BOT_TOKEN=
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_OWNER_ID=
TELEGRAM_TARGET_CHAT_ID=

# Optional user-session mode only if explicitly required for a feature.
# Treat the session string/file as a high-sensitivity credential.
TELEGRAM_SESSION_STRING=

# Persistence/coordination (final remote store to be selected)
PCM_DATABASE_URL=
PCM_WORKER_SHARED_SECRET=

MAX_CONCURRENT_DOWNLOADS=2
MAX_CONCURRENT_UPLOADS=2
MAX_QUEUE_SIZE=50
MIN_FREE_DISK_MB=2048
MAX_REDIRECT_HOPS=8
PROVIDER_TIMEOUT_SECONDS=60
MAX_FALLBACK_ATTEMPTS=3

DEFAULT_QUALITY=best
DEFAULT_DESTINATION=telegram
TEMP_DIR=/content/pcm
LOG_LEVEL=INFO

# Optional provider credentials, only when needed
GOFILE_TOKEN=
STREAMTAPE_LOGIN=
STREAMTAPE_KEY=
DOODSTREAM_API_KEY=
```

These names are proposals and should be validated during implementation. In Colab, prefer Colab Secrets for credentials rather than notebook literals. Keep `.env` and Pyrogram session files out of Git. A bot token and a user session are different access modes; default to bot-token mode unless a specific feature requires user authorization. Never log session strings, bot tokens, API hashes, cookies, or signed URLs.

## 11. Testing and Acceptance Criteria

### Resolver
- Recognizes direct media URLs, known provider pages, supported cloud shares, redirects, and unknown domains.
- Preserves required query parameters.
- Detects redirect loops and enforces hop/time limits.
- Blocks prohibited private-network requests and validates redirect destinations.
- Prefers exact provider matches when appropriate.
- Returns typed errors and useful diagnostics when no strategy succeeds.

### Plugins
- Each provider tests matching, success, malformed responses, timeouts, expired sources, and authentication failures.
- Provider failure does not crash the worker.
- Providers can be enabled/disabled through configuration.

### Pipeline
- Download and upload progress are independently visible.
- Failed upload can be retried without repeating a successful download when the file remains available.
- Multi-destination jobs preserve partial success.
- Backpressure prevents uncontrolled disk growth.
- Cleanup never deletes files required by active jobs.

### Worker and Telegram
- Bot reports worker offline after missed heartbeats.
- Jobs remain waiting while the worker is offline.
- Recovery avoids blindly duplicating completed uploads.
- Multiple workers cannot claim the same job without an expired/released lease.
- Only authorized users control the private bot.
- Commands handle invalid job IDs and report accurate state.
- Progress updates are throttled; sensitive signed URLs and secrets are not logged.

## 12. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Colab stops unexpectedly | Persistent state, heartbeat, restart reconciliation |
| Website changes break extraction | Provider isolation, fixture tests, diagnostics |
| Signed URL expires | Keep it ephemeral and reacquire before transfer |
| Disk fills during parallel work | Disk thresholds, backpressure, cleanup |
| Upload acknowledgement is lost | Idempotency where available; reconcile before retry |
| SSRF through URLs/redirects | Scheme/host checks, DNS/IP validation, redirect revalidation |
| Provider API changes | Separate adapters and capability checks |
| Shared-state races | Transactional storage or atomic leases |

## 13. Delivery Phases

1. **Python foundation:** Create `pyproject.toml`, pinned `requirements.txt`, config loading, structured logging, typed models/errors, URL parsing/normalization, redirect policy, and resolver unit tests.
2. **Pyrogram bot skeleton:** Implement owner-only access, `/start`, `/help`, URL intake, `/queue`, `/status`, `/cancel`, `/retry`, and `/settings`; add callback handling and test authorization.
3. **Resolver MVP:** Implement direct-media/direct-file detection, generic HTTP inspection, yt-dlp integration, provider registry, classification, safe fallback planning, and clear unsupported-URL diagnostics.
4. **Transfer pipeline:** Add bounded download/upload queues, separate progress events, speed/ETA reporting, disk backpressure, retries, validation, cleanup, and Telegram + GoFile adapters. Preserve per-destination partial success.
5. **Colab notebook:** Provide one-click setup/run instructions, secret loading, dependency checks, FFmpeg/aria2c availability checks, runtime heartbeat, resumable configuration, and safe shutdown/restart reconciliation. Notebook code should import modules from the repository.
6. **Durable persistence and recovery:** Select a remote transactional store before cross-runtime processing. Implement atomic job claims/leases, idempotency/reconciliation, worker heartbeats, and recovery tests.
7. **Provider expansion and hardening:** Wrap the first existing scraper after inspection, add cloud-share providers incrementally, verify third-party upload APIs, and expand integration/security tests.
8. **Deployment portability:** Document the Colab limitations and a path to run the Pyrogram control bot on an always-on host while processing runs on a worker.

## 14. Open Decisions

1. Which existing provider/repository should be wrapped first? Candidate: `Telebotfaroff/whbot`; inspect its current code before reusing anything.
2. Which durable remote store should hold jobs and coordinate recovery?
3. For the first prototype, bot and worker run together in Colab; when should they be split onto separate runtimes?
4. Are Telegram and GoFile the only required first-release destinations?
5. Confirm owner-only access for the MVP (recommended).
6. Which existing scraper integrations are stable enough to reuse?
7. Should Telegram uploads use bot-token mode only, or is a user session required for a clearly identified use case? Default recommendation: bot-token mode.

## 15. MVP Definition of Done

An authorized Telegram user can submit a supported URL; PCM identifies it, resolves or downloads content through a registered provider, uploads it to Telegram or GoFile, reports separate progress, returns a verified result link, and allows job inspection/retry. A worker disconnect does not cause queued work to be falsely reported as active. Resolver and provider tests cover successful, unsupported, and failure paths.

---

## 16. Implementation Plan and Milestones

The implementation should proceed in small, testable commits. Do not attempt to build every scraper or destination before the core job lifecycle works.

### Milestone 0 — Repository and runtime baseline
- Add Python package layout, `pyproject.toml`, `requirements.txt`, `.gitignore`, `.env.example`, and README setup instructions.
- Pin/test Python and library versions in a clean runtime; record known limitations of Pyrogram and Colab.
- Add config validation that fails fast when required settings are missing.
- Ensure secrets, session files, downloaded media, and logs containing private URLs are ignored by Git.

**Acceptance:** the package imports cleanly, configuration validation has tests, and a fresh Colab runtime can install dependencies without manually editing source files.

### Milestone 1 — Safe URL resolver
- Build URL parsing, normalization, scheme/host validation, redirect limits, redirect-loop detection, DNS/IP checks, and redacted diagnostics.
- Add provider contract, registry, content classification, typed failures, and bounded strategy planning.
- Begin with fixture-based tests and a small allowlist of known test URLs; never depend exclusively on live websites in unit tests.

**Acceptance:** unit tests cover valid, malformed, redirected, unsupported, expired, and prohibited-network URLs.

### Milestone 2 — Private Pyrogram control bot
- Add owner-ID authorization before any command or callback performs work.
- Implement `/start`, `/help`, URL intake, `/queue`, `/status`, `/cancel`, `/retry`, `/settings`, and `/providers`.
- Store job IDs and stage transitions through a persistence interface, not in handler-local variables.
- Use inline keyboards for quality and destination selection when more than one option exists.

**Acceptance:** unauthorized users cannot create or control jobs; invalid job IDs and callback inputs return safe errors; basic commands work without a download provider installed.

### Milestone 3 — Download and upload vertical slice
- Integrate yt-dlp for supported pages and native HTTP streaming for validated direct media/files.
- Add file validation and a single-download/single-upload pipeline first.
- Add Telegram destination, then GoFile, with independently tracked results.
- Add separate download/upload progress, speed/ETA where available, throttled Telegram edits, cancellation, retry, and cleanup.
- Expand concurrency only after the single-job path is reliable; start conservatively in Colab and enforce disk backpressure.

**Acceptance:** a supported test URL can be resolved, downloaded, validated, uploaded to the selected destination, and reported with a verified result link. A failed destination does not erase a successful one.

### Milestone 4 — Colab operations and recovery
- Create `colab/PCM_Worker.ipynb` to clone/update the repository, load Colab Secrets, install dependencies, check required binaries, configure temporary storage, and launch PCM.
- Show runtime/worker status and a clear warning that Colab may disconnect and is not guaranteed always-on hosting.
- Checkpoint job transitions in durable storage; reconcile jobs after restart and avoid blindly repeating uploads whose outcome is ambiguous.
- Keep a lightweight SQLite implementation for local tests if useful, but do not treat Colab's local SQLite file as durable across runtime loss.

**Acceptance:** after a simulated worker restart, jobs are reconciled into waiting, retryable, completed, or recovery-needed states without claiming the runtime was continuously available.

### Milestone 5 — Provider expansion and hardening
- Inspect and wrap existing scraper code one provider at a time.
- Add cloud-share adapters and additional destinations only after their APIs, credentials, rate limits, and output-link behavior are verified.
- Add integration tests, concurrency tests, SSRF tests, retry/backoff tests, and storage pressure tests.
- Document environment variables, Colab operation, troubleshooting, and future migration to an always-on control bot plus worker.

**Acceptance:** provider failures are isolated, resource limits are enforced, secrets are not logged, and the MVP can be operated from the documented setup.

### First implementation commit scope
The first coding change should establish the Python project skeleton, configuration and logging, URL model/provider interfaces, a minimal resolver with tests, and a Colab bootstrap outline. Do not implement speculative support for every site in the first commit.

## 17. Implementation Guardrails

- Keep Pyrogram handlers thin and use asynchronous I/O for network-bound work.
- Use subprocess argument arrays (not shell-concatenated user input) when invoking external tools.
- Never fetch arbitrary URLs without SSRF protection; validate every redirect and resolved address.
- Never log bot tokens, API hashes, session strings, cookies, or complete signed URLs.
- Use finite timeouts, retry caps, queue bounds, disk thresholds, and provider-specific limits.
- Do not claim Colab is always-on; show worker offline/waiting status honestly.
- Treat upload acknowledgements carefully and reconcile ambiguous outcomes before retrying.
- Do not add unrelated databases or services without a deliberate decision.

---
## 18. v1.2 Enhancements — Queue Intelligence, Recovery, and Operations

This section extends existing requirements without removing the Python + Pyrogram + Google Colab initial stack or existing resolver, provider, download, upload, and security requirements. Where requirements overlap, use the more specific acceptance criteria below.

### 18.1 Smart Queue Controls

- **FR-070 Pause and resume:** Add /pause JOB_ID and /resume JOB_ID. Pause is cooperative and stage-aware: stop scheduling new work immediately, ask supported download processes to pause, and defer upload-stage pauses when the destination API cannot safely pause. Report when a pause is requested but not yet safe.
- **FR-071 Priority and ordering:** Support normal and high priority for owner-submitted jobs, with FIFO ordering within each priority. Prevent starvation by periodically allowing older normal-priority jobs to run.
- **FR-072 Stage-specific retry:** Retry only the failed stage where possible. A failed GoFile upload must not trigger another download if the verified artifact is still available.
- **FR-073 Retry policy:** Use capped exponential backoff with jitter for transient failures; do not automatically retry invalid input, unsupported media, permanent authentication failures, or prohibited URLs.
- **FR-074 Queue visibility:** /queue shows position, stage, elapsed time, retry count, and destination status. Batch jobs have a parent batch ID and independent child job IDs.
- **FR-075 Concurrency configuration:** Configure download and upload concurrency separately. Concurrency is a maximum, not a promise: the resource manager may lower it when memory, disk, network, or provider limits require.
- **FR-076 Fairness and backpressure:** Do not start new downloads if the upload backlog, reserved disk requirement, or memory pressure exceeds configured thresholds.

### 18.2 Persistent Job History and Restart Recovery

- **FR-080 Job event history:** Persist job creation, stage changes, pause/resume/cancel requests, retries, destination outcomes, and sanitized error summaries with timestamps.
- **FR-081 Artifact manifest:** Record safe artifact metadata such as path or remote storage key, byte size, checksum when available, MIME/container information, creation time, and retention expiry. Never treat an ephemeral signed media URL as a durable artifact.
- **FR-082 Durable store:** Job records and leases must survive a Colab VM reset. Select and configure a remote transactional database before relying on cross-runtime recovery. Local SQLite may be used for development/tests only unless its durability is explicitly provided elsewhere.
- **FR-083 Recovery reconciliation:** On startup, compare persisted job state with actual available artifacts and destination confirmations. Mark ambiguous upload outcomes as recovery_needed and reconcile before retrying to avoid duplicate uploads where possible.
- **FR-084 Lease ownership:** Job claims use atomic leases with expiry and worker identity. Heartbeats renew leases. A stale worker cannot continue to mutate a job after losing its lease.
- **FR-085 History retention:** Configure retention separately for job metadata, logs, temporary files, and media artifacts. Provide an owner-triggered cleanup command or documented cleanup task; preserve job outcomes without keeping media indefinitely.
- **FR-086 Recovery guarantee wording:** Promise best-effort recovery based on persisted state and destination capabilities, not exactly-once execution when a third-party upload API cannot prove whether an operation completed.

### 18.3 Batch URLs and Duplicate Detection

- **FR-090 Batch intake:** Parse multiple URLs from one message and create a parent batch with one child job per normalized URL. Return a concise summary and allow per-child inspection, cancellation, and retry.
- **FR-091 Batch limits:** Enforce configurable maximum URLs per message and maximum queued jobs per user. Reject or ask for confirmation before accepting oversized batches.
- **FR-092 Canonical identity:** Normalize scheme/host casing and safe URL components; remove only known tracking parameters. Preserve query parameters required for signed links, access, variants, or share identifiers.
- **FR-093 Two-layer deduplication:** First detect likely duplicates by canonical source identity; when files are available, optionally compare size and cryptographic hash. Do not merge jobs solely because titles or file sizes match.
- **FR-094 Duplicate policy:** Support configurable skip, attach-to-existing-job, or force-separate-job behavior. Default to attaching to an active/completed job only when source identity and permissions make that safe.
- **FR-095 Cache separation:** Keep short-lived resolver metadata caches separate from durable job history. Apply TTLs and never reuse expired signed URLs, cookies, or IP-bound media sources.
- **FR-096 Batch reporting:** Report completed, failed, skipped, cancelled, and partial-success counts, plus a command to inspect child jobs.

### 18.4 Provider Health Scoring and Fallback

- **FR-100 Provider telemetry:** Track attempts, successful resolutions, validated sources, successful downloads, timeout rates, typed failure categories, and recent latency per provider and strategy.
- **FR-101 Bounded health score:** Calculate a configurable rolling health score from recent outcomes, sample size, latency, and failure severity. Do not permanently penalize a provider based on one failure or treat a tiny sample as statistically conclusive.
- **FR-102 Strategy ranking:** Rank candidates using exact provider match, declared capabilities, recent health, expected compatibility, authentication availability, and previous validation evidence. Health scoring must not override compatibility or security requirements.
- **FR-103 Circuit breaker:** Temporarily deprioritize or open a provider circuit after a configurable run of transient failures; allow controlled half-open probes and restore normal ranking after recovery.
- **FR-104 Typed fallback:** Record each attempt's provider, strategy, duration, and sanitized failure category. Try only compatible alternatives within a maximum attempts/time/resource budget.
- **FR-105 Owner diagnostics:** /providers and /health show enabled status, recent success rate, recent latency, circuit state, and last error category without exposing credentials or private URLs.
- **FR-106 Manual controls:** Allow the owner to enable/disable a provider and reset its circuit/health history. Manual disable always takes precedence over automated ranking.

### 18.5 Destination Profiles and Per-Job Settings

- **FR-110 Named profiles:** Allow the owner to define, edit, list, and select profiles such as telegram, gofile, and both. Profiles may include destination set, default quality, filename template, upload target, and retention policy.
- **FR-111 Per-job overrides:** Each job can override quality, destination set, filename, and supported processing options without changing the saved profile.
- **FR-112 Settings precedence:** Effective settings follow this order: explicit per-job choice > selected profile > global default > provider default. Display the effective destination and quality before a costly transfer when confirmation is enabled.
- **FR-113 Secret references:** Profiles may reference credential names/configuration keys but must never store raw tokens, API keys, session strings, or cookies in profile JSON or job history.
- **FR-114 Validation:** Validate profile values against provider capabilities before queueing. If a requested destination cannot accept the file or a setting is unsupported, explain the limitation and offer valid choices.
- **FR-115 Profile persistence:** Persist profile definitions outside the Colab runtime and version changes so a job in progress retains a snapshot of its settings when created.
- **FR-116 Destination independence:** Keep per-destination state, progress, attempts, and verified result links independent. A profile targeting multiple destinations must preserve partial success.

### 18.6 Disk, Memory, and Bandwidth Manager

- **FR-120 Resource sampling:** Periodically measure free disk space, process/system memory where available, active transfers, temporary artifact sizes, and recent throughput. Handle unavailable metrics gracefully.
- **FR-121 Disk reservations:** Before starting a download, estimate/reserve required temporary space where possible. Reject, defer, or stream jobs that exceed configured capacity; do not start work that predictably exhausts disk.
- **FR-122 Watermarks:** Define configurable low/high disk watermarks. Below the low watermark, stop new downloads and prioritize draining uploads/cleaning eligible artifacts; resume only after crossing the high watermark.
- **FR-123 Memory protection:** Bound in-memory queues and buffers; stream large files rather than reading them fully into memory. Reduce concurrency or pause scheduling under sustained memory pressure.
- **FR-124 Bandwidth policy:** Support optional global and per-transfer throughput limits where the underlying tool supports them. Do not promise exact rate limiting for providers/tools that do not expose it.
- **FR-125 Adaptive concurrency:** Start from configured concurrency, then lower it on sustained resource pressure or repeated provider rate limits. Increase cautiously after a stable interval, within the configured maximum.
- **FR-126 Temporary artifact lifecycle:** Associate each artifact with active jobs and upload consumers. Delete only when no active stage needs it and retention/partial-success policies allow cleanup.
- **FR-127 Runtime budget:** Keep a configurable shutdown margin for Colab: stop accepting new heavy work when the operator initiates shutdown, checkpoint safely, and report jobs that cannot finish before the runtime ends. Do not depend on predicting Colab's actual termination time.
- **FR-128 Resource telemetry:** /health reports free disk, memory status, active/pending downloads and uploads, throughput, and whether the scheduler is throttled. Do not expose system details to unauthorized users.

### 18.7 Security and Privacy Hardening

- **FR-130 Owner authorization:** Validate owner identity on every command, callback, and job mutation; never rely only on hidden buttons or an initial /start check.
- **FR-131 SSRF defense:** Allow only explicitly supported URL schemes; reject loopback, private, link-local, multicast, and reserved IPs; resolve and validate DNS before requests and revalidate every redirect. Defend against DNS rebinding and IP-literal tricks.
- **FR-132 Egress and size controls:** Apply connection/read timeouts, redirect limits, response-size limits, maximum file size, decompression safeguards, and bounded concurrency. Do not fetch arbitrary local files or cloud metadata endpoints.
- **FR-133 Safe subprocesses:** Invoke external programs with argument arrays, fixed executable paths where practical, controlled environments, and timeouts. Never concatenate user-supplied URLs, filenames, or options into a shell command.
- **FR-134 Secret hygiene:** Load secrets from Colab Secrets or environment variables. Redact tokens, session strings, cookies, signed query parameters, and authorization headers from logs, exceptions, job history, and Telegram replies.
- **FR-135 Session protection:** Prefer Telegram bot-token mode. If user-session mode is explicitly needed, treat the Pyrogram session file/string as a credential with access equivalent to the logged-in account; protect it, exclude it from Git, and provide rotation/revocation instructions.
- **FR-136 File safety:** Sanitize output filenames and paths, prevent path traversal, write to controlled temporary directories, and validate expected file type before processing. Do not trust MIME type or extension alone.
- **FR-137 Dependency and configuration security:** Pin dependencies, review updates, avoid executing remote scripts without inspection, keep .env, notebook outputs, session files, cookies, and media out of Git, and validate configuration at startup.
- **FR-138 Privacy controls:** Avoid storing full source URLs longer than needed when they contain tokens or private identifiers. Provide configurable history/log retention and a way to remove stored job metadata where safe.
- **FR-139 Authorized content:** PCM should process only content the user is authorized to access and transfer, and must not attempt to defeat access controls or provider restrictions.

### 18.8 Automated Test Strategy

- **FR-140 Unit tests:** Test URL normalization, scheme/host/IP validation, redirect policy, provider matching, strategy ranking, typed errors, profile precedence, duplicate identity, and job state transitions.
- **FR-141 Fixture-based provider tests:** Use saved, sanitized HTML/JSON fixtures and mocked HTTP responses for deterministic tests. Keep live-site checks optional and isolated from normal CI.
- **FR-142 Pipeline tests:** Simulate download success/failure, interrupted downloads, upload success/failure, partial destination success, cancellation, retry, cleanup, and ambiguous upload acknowledgements.
- **FR-143 Concurrency tests:** Verify bounded queue size, no duplicate active job claims, lease expiry, fairness, backpressure, and race-free job transitions.
- **FR-144 Resource tests:** Test disk low/high watermarks, estimated file size over limits, memory-pressure throttling, and safe cleanup while uploads are active.
- **FR-145 Security tests:** Include SSRF/private IP and redirect cases, DNS rebinding-oriented validation cases, malicious filenames, shell metacharacters, secret redaction, and unauthorized callback attempts.
- **FR-146 Recovery tests:** Simulate worker process termination at each stage, restart with persisted records, stale leases, missing artifacts, and ambiguous destination completion.
- **FR-147 CI baseline:** Run formatting/linting and tests on every pull request/commit using a supported Python version. Use a maintainable toolchain such as pytest plus Ruff; select exact versions during implementation.
- **FR-148 Acceptance gate:** A change to a provider, queue, persistence adapter, or uploader must include tests for its success path and at least one failure/recovery path. No secrets or real private URLs may be included in test fixtures.

## 19. Updated Acceptance Criteria

The enhanced MVP is accepted only when all of the following are demonstrated:

1. One Telegram message containing multiple URLs creates a parent batch and individually inspectable child jobs.
2. Duplicate policy works for canonical source identities without incorrectly stripping required signed-link parameters.
3. Owner can pause/resume supported work, cancel a job, retry a failed stage, and inspect job history.
4. Download and upload stages have independent progress, retry counters, and destination outcomes.
5. Provider ranking uses compatibility and recent health, while fallback attempts remain bounded and observable.
6. Destination profiles and per-job overrides resolve with the documented precedence and are persisted as a job settings snapshot.
7. Disk watermarks and queue backpressure prevent new downloads from exhausting temporary storage.
8. Resource pressure can lower concurrency, and /health reports when the scheduler is throttled.
9. A Colab restart recovers from durable job state and does not blindly repeat a destination operation with an ambiguous result.
10. SSRF, subprocess, filename, secret-redaction, owner-authorization, and state-transition tests pass.
11. The worker reports offline/waiting honestly when Colab is disconnected; no always-on guarantee is implied.

## 20. Updated Implementation Order

1. **Foundation and safety:** Python package/config/logging, schemas, typed errors, secret redaction, safe URL model, test/lint setup.
2. **Resolver and provider registry:** Canonicalization, SSRF-safe redirects, classification, provider contracts, strategy ranking, deterministic tests.
3. **Job lifecycle and durable storage:** Job/event schema, lease interface, state machine, history, idempotency/reconciliation design, persistence integration.
4. **Pyrogram control surface:** Owner-only commands, batch intake, queue/status/pause/resume/cancel/retry, inline destination and quality selection.
5. **Single-job transfer vertical slice:** One supported resolver, download validation, Telegram upload, then GoFile upload, independent progress and partial-success handling.
6. **Resource-aware queue:** Disk watermarks, memory/buffer limits, concurrency caps, backpressure, bandwidth settings, safe cleanup.
7. **Profiles, deduplication, and provider health:** Add after core lifecycle and persistence are reliable.
8. **Colab operations:** Bootstrap notebook, secrets, dependency checks, heartbeat, graceful stop/checkpoint, restart reconciliation.
9. **Hardening and provider expansion:** Add adapters incrementally with fixtures, failure tests, security review, and documentation.

The order intentionally prioritizes state correctness and safety before adaptive scoring or a large number of provider integrations. Features that require durable cross-runtime state must not be marked complete while state exists only on Colab's ephemeral disk.

## 21. Updated Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Duplicate batch inputs create redundant work | Canonical identity, configurable duplicate policy, optional content hashes |
| Provider health score overreacts to sparse data | Minimum sample thresholds, rolling windows, confidence-aware ranking |
| Pause/cancel cannot interrupt every third-party operation | Stage-aware cooperative controls and explicit pending state |
| Runtime pressure exhausts disk or memory | Reservations, watermarks, bounded buffers, adaptive concurrency |
| Restart causes duplicate upload | Durable events, leases, destination reconciliation, recovery-needed state |
| Sensitive signed URLs leak in logs | Central redaction and tests that assert secret removal |
| Automated fallback causes excessive requests | Strict attempts, timeout, host, and total resource budgets |
| Colab runtime disappears mid-job | Durable external state, checkpointing, honest offline status; no uptime promise |

---

**End of PRD — Draft v1.2 (Python + Pyrogram + Colab, enhanced operations)**
