"""Small MCP stdio adapter over the same runtime used by the CLI."""

from __future__ import annotations

import json
import sys
from typing import Any

from agent_reach.runtime import flow, manage, tools
from agent_reach.runtime.result import BAD_INPUT, DEFAULT_HINTS, ReachError, classify

TOOLS: list[dict] = [
    {"name": "reach_status", "description": "Inspect channel capabilities and local verification state.",
     "inputSchema": {"type": "object", "properties": {"channel": {"type": "string"}}}},
    {"name": "reach_ensure", "description": "Install, reuse an authorized session, and verify one channel. Returns a user step when needed.",
     "inputSchema": {"type": "object", "properties": {
         "channel": {"type": "string"}, "action": {"type": "string"},
         "source_profile": {"type": "string", "description": "Explicit site-scoped consent to import from this connected profile"},
         "verify": {"type": "boolean", "default": True}}, "required": ["channel"]}},
    {"name": "reach_execute", "description": "Prepare a channel and perform a declared read-only action once, including Xiaohongshu comments. Inspect reach_status for parameters. Login returns a resumable user step.",
     "inputSchema": {"type": "object", "properties": {
         "channel": {"type": "string"}, "action": {"type": "string"},
         "params": {"type": "object"}, "timeout": {"type": "number", "default": 60},
         "source_profile": {"type": "string"}}, "required": ["channel", "action", "params"]}},
    {"name": "reach_resume", "description": "Continue a pending query after the user completes a login or verification step.",
     "inputSchema": {"type": "object", "properties": {"operation_id": {"type": "string"}},
                     "required": ["operation_id"]}},
]


def _validate_args(name: str, args: dict) -> None:
    spec = next((t["inputSchema"] for t in TOOLS if t["name"] == name), None)
    if spec is None:
        raise ReachError(BAD_INPUT, "Unknown tool")
    if not isinstance(args, dict):
        raise ReachError(BAD_INPUT, "Tool arguments must be an object")
    missing = set(spec.get("required", [])) - set(args)
    unknown = set(args) - set(spec["properties"])
    if missing or unknown:
        raise ReachError(BAD_INPUT, "Invalid tool arguments: " + "; ".join(
            part for part in (f"missing {', '.join(sorted(missing))}" if missing else "",
                              f"unknown {', '.join(sorted(unknown))}" if unknown else "") if part))
    kinds: dict[str, Any] = {"string": str, "object": dict, "boolean": bool, "number": (int, float)}
    for key, value in args.items():
        kind = spec["properties"][key]["type"]
        if (not isinstance(value, kinds[kind]) or kind == "number" and isinstance(value, bool)
                or kind == "string" and not value.strip()):
            raise ReachError(BAD_INPUT, f"{key} must be a nonempty {kind}")


def _invoke(name: str, args: dict) -> dict:
    _validate_args(name, args)
    if name == "reach_status":
        channel = args.get("channel")
        if channel:
            ch = manage._channel(channel)
            return {"channel": channel, **manage.channel_status(ch, manage.state.load()),
                    "actions": [{"name": a.name, "description": a.help,
                                 "params": [p.name for p in a.params],
                                 "parameters": [{"name": p.name, "required": p.required,
                                                 "default": p.default, "type": p.type.__name__,
                                                 "description": p.help} for p in a.params],
                                 "backends": [b for b, _ in a.backends]} for a in ch.actions]}
        return manage.doctor()
    if name == "reach_ensure":
        return flow.ensure(args["channel"], action=args.get("action"),
                           source_profile=args.get("source_profile"), verify=args.get("verify", True))
    if name == "reach_execute":
        return flow.execute(args["channel"], args["action"], args["params"],
                            timeout=args.get("timeout", 60), source_profile=args.get("source_profile"))
    if name == "reach_resume":
        from agent_reach.runtime.ask import resume
        return resume(args["operation_id"])
    raise ValueError("Unknown tool")


def _reply(request: dict) -> dict | None:
    method = request.get("method")
    ident = request.get("id")
    if ident is None:
        return None
    try:
        result: dict
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                      "serverInfo": {"name": "agent-reach", "version": manage.__version__}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = request.get("params") or {}
            if not isinstance(params, dict):
                raise ValueError("Tool call params must be an object")
            args = params.get("arguments", {})
            try:
                value = _invoke(params.get("name", ""), args)
                failed = value.get("ok") is False and value.get("status") != "needs_user_action"
            except (ReachError, ValueError, KeyError, TypeError) as exc:
                err = classify(exc)
                value = {"ok": False, "status": "failed", "error": {
                    "code": err.code, "message": err.message,
                    "hint": err.hint or DEFAULT_HINTS.get(err.code, "")}}
                failed = True
            result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}],
                      "structuredContent": value, "isError": failed}
        else:
            return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": "Method not found"}}
        return {"jsonrpc": "2.0", "id": ident, "result": result}
    except (TypeError, ValueError, KeyError) as exc:
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32602, "message": str(exc)[:200]}}


def serve() -> int:
    tools.extend_path()
    for line in sys.stdin:
        if len(line) > 1024 * 1024:
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                continue
            reply = _reply(request)
        except ValueError:
            continue
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0
