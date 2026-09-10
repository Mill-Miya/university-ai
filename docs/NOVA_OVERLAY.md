# N.O.V.A. Overlay Integration v1 / v2

N.O.V.A. is an optional state display and, in v2, an entry point for fixed existing actions. Existing QMessageBox answers, Tray, Windows Toast/fallback, OCR storage and LlmService behavior remain the application interface. No answers, OCR text, prompts or notification bodies are sent to the overlay. Full HUD answer rendering, RAG and indexing are out of scope.

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

## Integration v2 — Core commands

Core → narrow Electron preload/main → existing authenticated localhost socket → Python daemon → `ApplicationCommandDispatcher.requested` with `Qt.QueuedConnection` → decorated main-thread slot → fixed `ApplicationCommand` handler map. Tray invokes that same dispatcher and the same existing handlers.

| Command | Existing UI/controller |
|---|---|
| `ask_ai` | AiQuestionDialog |
| `ask_region` | ScreenCaptureController.select_region_and_ask |
| `open_documents` | DocumentsDialog |
| `open_settings` | SettingsDialog |

No document-question or notification-history UI exists in this base, so those entries are absent. No Core quit, arbitrary method dispatch, shell, file/URL payload or business logic is added. Dialogs use retained asynchronous `open()` instead of a blocking `exec()`; duplicate invocation raises the existing dialog and returns `busy`.

The descriptor advertises `capabilities:["commands-v1"]`. Python registers its fixed command list only with a capable Overlay; old v1 Overlays continue receiving state packets unchanged. An old Python peer can connect to the new Overlay without registering commands.

```json
{"v":1,"op":"register_commands","token":"<credential>","commands":["ask_ai","ask_region","open_documents","open_settings"]}
{"v":1,"op":"command","token":"<credential>","request_id":1,"command":"ask_ai"}
{"v":1,"op":"command_result","token":"<credential>","request_id":1,"command":"ask_ai","ok":true}
{"v":1,"op":"command_result","token":"<credential>","request_id":2,"command":"ask_region","ok":false,"error":"unavailable"}
```

`command` travels Electron → Python; registration/results travel Python → Electron and receive the existing v1 acknowledgement. The daemon demultiplexes commands and acknowledgements. All frames retain token authentication, strict schemas and the 4096-byte buffer bound. IDs are increasing integers 1..2147483647 per connection. Fixed errors are `unavailable`, `busy`, `invalid`, `failed`, `timeout`, `disconnected`, `duplicate`. No prompt, answer, OCR text, path, URL, executable or traceback crosses this boundary.

One command is in flight; the sender and shared dispatcher debounce for 400 ms. Only one queued Qt delivery can exist even across reconnects. The receiver records IDs before dispatch; duplicate/overlapping frames close the connection. Queued work checks session liveness and a three-second deadline before executing. Electron times out after four seconds and closes the socket. It routes commands only when exactly one fresh registered peer exists. No command is automatically retried: after a lost reply execution may be uncertain. State heartbeats can be resent and reconnect re-advertises availability, but old intents/results never move to the new session.

`ok:true` means the existing action was opened/started, not that an LLM request succeeded. Ollama/OCR failures retain existing Qt reporting and Error state. Menu interaction never chooses processing states; question and region actions use the v1 mapping above. Selecting an item closes the menu and releases Electron focus before Qt opens its UI. Idle remains click-through. Esc closes the Core menu first, then returns to Idle; outside click/focus loss/disconnect also closes it. A separate MOVE grip allows repositioning. The browser nine-state API and browser assets are unchanged.

Additional tests: `tests/test_commands.py` covers fixed dispatch, malformed packets, queued Qt-thread handoff, duplicates, session invalidation, reconnect/no replay and shared handlers. Run `python tools/native_core_acceptance.py --overlay-dir C:\path\to\nova-visual-playground\overlay-prototype` for actual Core interaction against isolated data. Its test hotkey is Ctrl+Alt+Shift+Space to preserve an existing independent Overlay; summary output contains booleans/state names, never answers or credentials. Human final visual acceptance, mixed DPI, multiple monitors and long-run resources remain separate.

The paired Overlay's `overlay-prototype/INTEGRATION_V2.md` specifies native UX and the complete wire contract. Qt threading reference: [queued connections](https://doc.qt.io/qtforpython-6/overviews/qtdoc-threads-qobject.html).

Verified on Windows, 2026-09-10: **105 tests passed**, paired Overlay check/native passed, and real Qt/Capture/Tesseract/Ollama/IPC/Electron integration passed. Actual desktop Core input opened AI質問, 範囲AI and 資料; real answers stayed in Qt. Core-menu Esc used desktop keyboard input; region Esc passed the native Qt event test (Qt Tool windows were absent from the desktop automation inventory). Forced Overlay exit preserved the app/Tray/LLM, reconnection worked, and graceful shutdown preserved independently restarted Overlay. Final human visual quality, mixed DPI, multiple monitors, long-duration resource profiling and Toast appearance remain unaccepted. Status: **Integration v2 implementation complete, final acceptance incomplete**.
