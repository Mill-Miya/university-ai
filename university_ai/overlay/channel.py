"""Bounded duplex transport; command intents are never retried."""
import json
import queue
import secrets
import select
import threading
import time

from university_ai.app.commands import ApplicationCommand, CommandIntent


class CommandChannel:
    def __init__(self, sock, token, dispatcher):
        self.sock, self.token, self.dispatcher = sock, token, dispatcher
        self.buffer = bytearray()
        self.connected = threading.Event()
        self.connected.set()
        self.last_id = 0
        self.results = queue.Queue(maxsize=1)
        self.pending = False

    def close(self):
        self.connected.clear()

    def _receive(self):
        while b"\n" not in self.buffer:
            data = self.sock.recv(4096)
            if not data or len(self.buffer) + len(data) > 4096:
                raise ConnectionError("Invalid overlay frame")
            self.buffer.extend(data)
        line, _, rest = self.buffer.partition(b"\n")
        self.buffer = bytearray(rest)
        return json.loads(line)

    def _command(self, packet):
        if (not isinstance(packet, dict) or set(packet) != {"v", "op", "token", "request_id", "command"}
                or type(packet["v"]) is not int or packet["v"] != 1 or packet["op"] != "command"
                or not isinstance(packet["token"], str)
                or not secrets.compare_digest(packet["token"], self.token)
                or type(packet["request_id"]) is not int or not 1 <= packet["request_id"] <= 2147483647):
            raise ConnectionError("Invalid overlay command")
        try:
            command = ApplicationCommand(packet["command"])
        except (ValueError, TypeError):
            raise ConnectionError("Unknown overlay command") from None
        request_id = packet["request_id"]
        if request_id <= self.last_id or self.pending:
            # Close rather than queue an unbounded sequence of duplicate replies.
            raise ConnectionError("Duplicate or overlapping overlay command")
        self.last_id, self.pending = request_id, True

        def respond(error):
            if not self.connected.is_set():
                return
            result = {"v": 1, "op": "command_result", "token": self.token,
                      "request_id": request_id, "command": command.value, "ok": error is None}
            if error is not None:
                result["error"] = error
            self.results.put_nowait(result)

        self.dispatcher.submit(CommandIntent(command, self.connected, time.monotonic() + 3, respond))

    def exchange(self, packet):
        self.sock.sendall((json.dumps(packet, separators=(",", ":")) + "\n").encode())
        while True:
            response = self._receive()
            if response == {"v": 1, "ok": True}:
                return
            self._command(response)

    def pump(self):
        if self.buffer or select.select([self.sock], [], [], 0)[0]:
            self._command(self._receive())
        try:
            result = self.results.get_nowait()
        except queue.Empty:
            return
        self.exchange(result)
        self.pending = False
