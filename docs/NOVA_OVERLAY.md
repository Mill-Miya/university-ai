# N.O.V.A. Overlay Integration v1

N.O.V.A. is an optional state display. Existing QMessageBox answers, Tray, Windows Toast/fallback, OCR storage and LlmService behavior remain the application interface. No answers, OCR text, prompts or notification bodies are sent to the overlay. Full HUD answer rendering, RAG and indexing are out of scope.

## Start

Install `Mill-Miya/nova-visual-playground`'s `overlay-prototype` dependencies with `npm ci`, then run University AI normally:

```powershell
$env:NOVA_OVERLAY_DIR = 'C:\path\to\nova-visual-playground\overlay-prototype'
python -m university_ai.app.main
```

Without `NOVA_OVERLAY_DIR`, the client connects to an already-running overlay but does not launch one. No installed Overlay is required for University AI to run. `NOVA_OVERLAY_COMMAND` optionally accepts a JSON argv array for a trusted executable; no shell interpolation is used. Invalid launch configuration falls back to connect-only mode. Automatic launch is attempted once per app lifetime, while reconnect is continuous.

Both processes use `%LOCALAPPDATA%\UniversityAI\nova-overlay.json`. `NOVA_OVERLAY_ENDPOINT` overrides this discovery path for testing or a private custom location. The file is a credential: do not share it or store it in a public folder. It contains an ephemeral TCP port and a rotating random token. The client never reads a remote hostname from it; it connects only to 127.0.0.1.

## Architecture and protocol

UI/controllers and NotificationService → `NovaOverlayAdapter` → `NovaOverlayClient` background thread → authenticated local TCP → Electron main → narrow preload bridge → `window.nova.setState`.

The adapter catches client errors, including injected clients. Socket IO, discovery-file reads, connection retry and child-process launch occur only on the daemon thread. UI calls modify an in-memory activity set and signal the thread. During an outage there is no unbounded retry queue; only current state is retained.

NDJSON v1 state packet:

```json
{"v":1,"op":"state","token":"<256-bit hex credential>","state":"thinking"}
```

The receiver acknowledges `{"v":1,"ok":true}`. Packets have a 4096-byte receive-buffer bound. Unknown fields, operations, states, versions, malformed packets and wrong credentials are rejected. Optional message is validated but discarded by Electron in v1; Python deliberately sends no message argument. External allowed states are the seven states in the priority table; the browser's existing nine-state API remains unchanged.

Python connects with a 250 ms socket timeout, sends changes and a heartbeat every second, retries connection once per second, and throttles repeated unavailable logs to once per 30 seconds. Electron removes a connection's state on disconnect and expires it after four seconds without a valid heartbeat. It binds an OS-selected IPv4-loopback port, with at most sixteen connections. The renderer has no socket, arbitrary JavaScript, file or shell execution endpoint.

## State ownership

Priority: **error > scanning > thinking > speaking > notification > active > idle**.

`begin(state)` returns a token; `finish(token, outcome)` releases only that token. The default `set_state`/convenience methods use a separate manual activity slot, so `idle()` does not clear another request's token. Success notifications last two seconds and errors three seconds; independent work resumes after higher-priority transient states expire. Duration is monotonic-time based. Notification bursts share an expiring slot rather than allocating unbounded timers.

| Integration point | Mapping |
|---|---|
| Resident startup / connection | Idle |
| AI question dialog invoke | Active until request or close |
| Capture and region selection | Scanning |
| OCR | Keeps same Scanning token |
| Capture/OCR completed | Release token, Notification |
| LlmWorker starts request | Thinking |
| LlmWorker success/failure | Release token, Notification/Error |
| NotificationService delivered/failed | Notification/Error, existing delivery/status handling retained |
| Selection cancelled | Release token, no notification |
| No activity or transient state remains | Idle |

Overlapping LLM operations and captures do not cancel each other. A short notification cannot replace Thinking. OCR's Scanning token is released before an OCR-to-LLM worker begins Thinking. Question and capture results stay in the existing Qt UI. The question worker is retained by QApplication so closing the dialog does not destroy a running thread.

## Lifecycle and failure handling

The composition root creates the optional adapter, starts the daemon after component construction and registers it with ApplicationLifecycle. Initialization, launch and communication failures are logged without stopping the application. Lifecycle stop is idempotent and runs even if scheduler startup or app execution raises after construction.

On stop, the daemon sends `op:shutdown` with `owner:null` for a standalone overlay. This detaches the client without quitting Electron. A child launched by University AI receives a separate ownership token through its environment. Only a matching token requests app quit. If necessary, cleanup terminates only the exact child Popen handle that this client started, never another process found by name/PID. Stop waiting is bounded. Independently restarted overlays have no matching ownership secret and stay alive.

## Tests

```powershell
python -m pytest -q
python tools/native_overlay_smoke.py --overlay-dir C:\path\to\nova-visual-playground\overlay-prototype
```

`tests/test_overlay.py` covers state priority/expiry, concurrent tokens, LLM success/error, capture/OCR success/error, OCR-to-LLM, cancellation, broken/missing overlay, socket failure/reconnect, launch failure/ownership, notifications, composition and lifecycle. Existing tests continue to run without Overlay.

The opt-in native test uses real Qt, Tesseract (`jpn+eng`), local Ollama (`qwen2.5:3b`) and Electron. It captures a dedicated sample window, preserves user data and Start-menu registration, leaves answers in Qt, and observes actual renderer state through an explicit test-only observer. It also kills its own Overlay child, runs another real LLM request, restarts an independent Overlay and verifies shutdown ownership. Artifacts stay in `.test-artifacts/native-*`; no answer text is written to its summary report.

## Limits

There is no automatic download, persistent OS startup registration or repeated automatic process respawn. Fast operations may coalesce intermediate states. Full-screen captures may include the floating core. Error display timeout does not assert that a failed service itself recovered. Human visual review, mixed DPI, multi-monitor positioning and long-run resource profiling are separate from the automated native test. Windows descriptor protection relies on the private user directory ACL and does not isolate hostile processes running under the same user.

The matching Overlay repository's `overlay-prototype/INTEGRATION_V1.md` specifies the receiver and native security boundary.
