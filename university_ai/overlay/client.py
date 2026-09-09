from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time

LOGGER = logging.getLogger(__name__)
PRIORITY = {"idle": 0, "active": 1, "notification": 2, "speaking": 3,
            "thinking": 4, "scanning": 5, "error": 6}


def default_endpoint() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return Path(os.environ.get("NOVA_OVERLAY_ENDPOINT", base / "UniversityAI" / "nova-overlay.json"))


class NovaOverlayClient:
    """Thread-safe activity arbitration; socket/process work runs only on a daemon.

    begin/finish tokens represent independent operations. set_state is a legacy
    single activity slot and cannot clear other operations. No work queue grows
    during an outage: reconnect sends only the currently effective state.
    """

    def __init__(self, endpoint: Path | None = None, *, command: list[str] | None = None,
                 clock=time.monotonic, notification_seconds=2.0, error_seconds=3.0):
        self.endpoint = endpoint or default_endpoint()
        self.command = command
        self._clock = clock
        self._notification_seconds = notification_seconds
        self._error_seconds = error_seconds
        self._lock = threading.RLock()
        self._activities: dict[str, tuple[str, float | None]] = {}
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self._process = None
        self._owner = secrets.token_hex(32)
        self._launched = False

    @classmethod
    def from_environment(cls):
        command = None
        try:
            raw = os.environ.get("NOVA_OVERLAY_COMMAND")
            if raw:
                command = json.loads(raw)
                if not isinstance(command, list) or not command or not all(isinstance(s, str) and s for s in command):
                    raise ValueError("NOVA_OVERLAY_COMMAND must be a JSON argv array")
            elif os.environ.get("NOVA_OVERLAY_DIR"):
                directory = Path(os.environ["NOVA_OVERLAY_DIR"]).resolve()
                binary = directory / "node_modules" / "electron" / "dist" / ("electron.exe" if os.name == "nt" else "electron")
                if binary.is_file() and (directory / "main.cjs").is_file():
                    command = [str(binary), str(directory)]
                else:
                    LOGGER.warning("NOVA_OVERLAY_DIR has no installed Electron; connect-only mode")
        except Exception:
            LOGGER.warning("Invalid NOVA launch configuration; connect-only mode")
            command = None
        return cls(command=command)

    def start(self):
        with self._lock:
            if self._thread is not None or self._stop.is_set():
                return
            self._thread = threading.Thread(target=self._run, name="nova-overlay", daemon=True)
            self._thread.start()

    def begin(self, state: str) -> str | None:
        if state not in PRIORITY or state == "idle":
            return None
        token = secrets.token_hex(12)
        with self._lock:
            if self._stop.is_set():
                return None
            self._activities[token] = (state, None)
        self._wake.set()
        return token

    def finish(self, token: str | None, outcome: str | None = None):
        with self._lock:
            self._activities.pop(token, None)
            if outcome in ("notification", "error"):
                self._pulse(outcome)
        self._wake.set()

    def _pulse(self, state):
        duration = self._error_seconds if state == "error" else self._notification_seconds
        # One expiring slot per outcome; bursts cannot grow memory without bound.
        self._activities["pulse:" + state] = (state, self._clock() + duration)

    def set_state(self, state: str):
        if state not in PRIORITY:
            return
        with self._lock:
            if state == "idle":
                self._activities.pop("manual", None)
            elif state in ("notification", "error"):
                self._pulse(state)
            else:
                self._activities["manual"] = (state, None)
        self._wake.set()

    def idle(self): self.set_state("idle")
    def active(self): self.set_state("active")
    def scanning(self): self.set_state("scanning")
    def thinking(self): self.set_state("thinking")
    def speaking(self): self.set_state("speaking")
    def notification(self, message: str | None = None): self.set_state("notification")
    def error(self, message: str | None = None): self.set_state("error")

    def current_state(self):
        with self._lock:
            now = self._clock()
            self._activities = {k: v for k, v in self._activities.items() if v[1] is None or v[1] > now}
            return max((state for state, _ in self._activities.values()), key=PRIORITY.get, default="idle")

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)

    def _connect(self):
        # Never accept a hostname from the discovery file; only IPv4 loopback.
        with self.endpoint.open("r", encoding="utf-8") as handle:
            descriptor = json.loads(handle.read(4097))
        port, token = descriptor["port"], descriptor["token"]
        if descriptor.get("v") != 1 or type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Invalid local overlay endpoint")
        if not isinstance(token, str) or len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
            raise ValueError("Invalid local overlay credential")
        sock = socket.create_connection(("127.0.0.1", port), timeout=0.25)
        return sock, token

    @staticmethod
    def _send(sock, packet):
        sock.sendall((json.dumps(packet, separators=(",", ":")) + "\n").encode("utf-8"))
        response = bytearray()
        while b"\n" not in response:
            chunk = sock.recv(128)
            if not chunk or len(response) + len(chunk) > 256:
                raise ConnectionError("NOVA acknowledgement unavailable")
            response.extend(chunk)
        if json.loads(response) != {"v": 1, "ok": True}:
            raise ConnectionError("NOVA acknowledgement invalid")

    def _launch(self):
        if self._launched or not self.command or self._stop.is_set():
            return
        self._launched = True
        env = {**os.environ, "NOVA_OVERLAY_ENDPOINT": str(self.endpoint), "NOVA_OVERLAY_OWNER_TOKEN": self._owner}
        env.pop("ELECTRON_RUN_AS_NODE", None)
        self._process = subprocess.Popen(self.command, env=env, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    def _run(self):
        sock = None
        token = None
        last_state = None
        sent_at = 0.0
        last_log = -float("inf")
        retry_at = 0.0
        try:
            while not self._stop.is_set():
                try:
                    now = time.monotonic()
                    if sock is None and now >= retry_at:
                        sock, token = self._connect()
                        last_state = None
                        LOGGER.info("NOVA Overlay connected")
                    state = self.current_state()
                    if sock is not None and (state != last_state or now - sent_at >= 1.0):
                        self._send(sock, {"v": 1, "op": "state", "token": token, "state": state})
                        last_state, sent_at = state, now
                except Exception:
                    if sock is not None:
                        sock.close()
                    sock = None
                    retry_at = time.monotonic() + 1.0
                    if time.monotonic() - last_log >= 30:
                        LOGGER.warning("NOVA Overlay unavailable; University AI continues")
                        last_log = time.monotonic()
                    try:
                        self._launch()
                    except Exception:
                        LOGGER.warning("NOVA Overlay launch failed; University AI continues")
                self._wake.wait(0.1)
                self._wake.clear()
        finally:
            if sock is not None:
                try:
                    self._send(sock, {"v": 1, "op": "shutdown", "token": token,
                                      "owner": self._owner if self._process is not None else None})
                except Exception:
                    pass
                sock.close()
            # Only the exact child we spawned can be terminated; never discover/kill by name or PID file.
            if self._process is not None:
                try:
                    self._process.wait(timeout=0.6)
                except subprocess.TimeoutExpired:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=0.3)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                except OSError:
                    LOGGER.warning("NOVA child cleanup failed")


class NovaOverlayAdapter:
    """Fail-open boundary, including injected or future client implementations."""
    def __init__(self, client=None):
        self.client = client

    def _call(self, method, *args):
        if self.client is None:
            return None
        try:
            return getattr(self.client, method)(*args)
        except Exception:
            LOGGER.warning("NOVA adapter %s failed; operation continues", method)
            return None

    def start(self): return self._call("start")
    def stop(self): return self._call("stop")
    def begin(self, state): return self._call("begin", state)
    def finish(self, token, outcome=None): return self._call("finish", token, outcome)
    def set_state(self, state): return self._call("set_state", state)
    def idle(self): return self.set_state("idle")
    def active(self): return self.set_state("active")
    def scanning(self): return self.set_state("scanning")
    def thinking(self): return self.set_state("thinking")
    def speaking(self): return self.set_state("speaking")
    def notification(self, message=None): return self.set_state("notification")
    def error(self, message=None): return self.set_state("error")
