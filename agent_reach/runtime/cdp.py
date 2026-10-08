"""Minimal Chrome DevTools Protocol client for the Agent Reach browser (127.0.0.1 only).

Only used against the dedicated browser, never the user's own Chrome.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import urllib.request
from typing import List, Optional
from urllib.parse import urlparse

from .browser import CDP_URL

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_TIMEOUT = 5


def _json(path: str):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # loopback: never proxy
    try:
        with opener.open(f"{CDP_URL}{path}", timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception:  # noqa: BLE001
        return None


def _read_frame(sock: socket.socket, buf: bytes):
    while True:
        while len(buf) < 2:
            chunk = sock.recv(4096)
            if not chunk:
                return None, buf
            buf += chunk
        opcode, length, head = buf[0] & 0x0F, buf[1] & 0x7F, 2
        if length in (126, 127):
            need = 2 if length == 126 else 8
            while len(buf) < head + need:
                chunk = sock.recv(4096)
                if not chunk:
                    return None, buf
                buf += chunk
            length = struct.unpack(">H" if need == 2 else ">Q", buf[head:head + need])[0]
            head += need
        while len(buf) < head + length:
            chunk = sock.recv(65536)
            if not chunk:
                return None, buf
            buf += chunk
        payload, buf = buf[head:head + length], buf[head + length:]
        if opcode == 0x8:
            return None, buf
        if opcode in (0x0, 0x1, 0x2):
            return payload, buf


def _send(sock: socket.socket, text: str) -> None:
    payload = text.encode("utf-8")
    mask = os.urandom(4)
    n = len(payload)
    head = bytes([0x81]) + (
        bytes([0x80 | n]) if n < 126
        else bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536
        else bytes([0x80 | 127]) + struct.pack(">Q", n)
    )
    sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))


def call(method: str, params: Optional[dict] = None) -> Optional[dict]:
    """One browser-level CDP call; returns `result` or None if unreachable."""
    ws = (_json("/json/version") or {}).get("webSocketDebuggerUrl")
    if not ws:
        return None
    u = urlparse(ws)
    host, port = u.hostname or "127.0.0.1", u.port or 80
    try:
        with socket.create_connection((host, port), timeout=_TIMEOUT) as sock:
            sock.settimeout(_TIMEOUT)
            key = base64.b64encode(os.urandom(16)).decode()
            sock.sendall(
                (f"GET {u.path or '/'} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
                 f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode()
            )
            resp = b""
            while b"\r\n\r\n" not in resp:
                chunk = sock.recv(4096)
                if not chunk:
                    return None
                resp += chunk
            head, _, buf = resp.partition(b"\r\n\r\n")
            accept = base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()
            if head.split(b"\r\n", 1)[0].split()[1:2] != [b"101"] or accept not in head.decode("latin-1"):
                return None
            _send(sock, json.dumps({"id": 1, "method": method, "params": params or {}}))
            for _ in range(32):
                payload, buf = _read_frame(sock, buf)
                if payload is None:
                    return None
                msg = json.loads(payload.decode("utf-8"))
                if msg.get("id") == 1:
                    return msg.get("result")
    except Exception:  # noqa: BLE001
        return None
    return None


def cookies(domain: str) -> List[dict]:
    """Cookies the dedicated browser holds for `domain` (and its subdomains)."""
    result = call("Storage.getCookies") or {}
    d = domain.lstrip(".")
    return [c for c in result.get("cookies", []) if c.get("domain", "").lstrip(".").endswith(d)]
