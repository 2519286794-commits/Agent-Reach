"""Comments must be reachable through the same channel, MCP and one-sentence path."""

import json

import pytest

from agent_reach import mcp_server
from agent_reach.channels.xiaohongshu import XiaoHongShuChannel
from agent_reach.runtime import ask
from agent_reach.runtime.dispatch import run_action

NOTE = "https://www.xiaohongshu.com/explore/abc123?xsec_token=test"


@pytest.mark.parametrize("target,limit", [("https://example.com/explore/abc", 3),
                                         (NOTE, 51), (NOTE, 0)])
def test_invalid_comments_request_never_accesses_browser(monkeypatch, target, limit):
    from agent_reach.backends import cloak
    monkeypatch.setattr(cloak, "call", lambda *a, **k: pytest.fail("unexpected browser"))
    result = run_action(XiaoHongShuChannel(), "comments", {"target": target, "limit": limit},
                        only_backend="cloakbrowser")
    assert result["error"]["code"] == "BAD_INPUT"


def test_opencli_comments_keep_replies_and_explicit_scope(monkeypatch):
    from agent_reach.channels import xiaohongshu
    calls = []
    def command(site, args, **kwargs):
        calls.append(args)
        return [{"author": "A", "text": "parent", "is_reply": False},
                {"author": "B", "text": "reply", "is_reply": True, "reply_to": "A"}]
    monkeypatch.setattr(xiaohongshu, "opencli_call", command)
    result = run_action(XiaoHongShuChannel(), "comments", {"target": NOTE, "limit": 1},
                        only_backend="opencli")
    assert result["ok"]
    assert len(result["items"]) == 2  # limit constrains parents, not replies
    assert result["items"][1]["raw"]["reply_to"] == "A"
    assert all(r["raw"]["exhaustive"] is False for r in result["items"])
    assert calls == [["comments", NOTE, "--limit", "1", "--with-replies", "true"]]


def test_mcp_reports_comments_parameters():
    status = mcp_server._invoke("reach_status", {"channel": "xiaohongshu"})
    action = next(a for a in status["actions"] if a["name"] == "comments")
    assert action["backends"] == ["cloakbrowser", "opencli"]
    assert action["parameters"][0]["required"] is True


@pytest.mark.parametrize("args", [{"channel": "xiaohongshu", "verify": "false"},
                                  {"channel": "xiaohongshu", "surprise": True}, []])
def test_mcp_bad_arguments_cannot_trigger_setup(monkeypatch, args):
    monkeypatch.setattr(mcp_server.flow, "ensure", lambda *a, **k: pytest.fail("unexpected setup"))
    reply = mcp_server._reply({"id": 1, "method": "tools/call", "params": {
        "name": "reach_ensure", "arguments": args}})
    result = reply["result"]
    assert result["isError"]
    assert result["structuredContent"]["error"]["code"] == "BAD_INPUT"


def test_one_sentence_can_select_comments(monkeypatch):
    def model(messages, **kwargs):
        assert '"action": "comments"' in messages[0]["content"]
        return json.dumps({"requests": [{"channel": "xiaohongshu", "action": "comments",
                                         "params": {"target": NOTE, "limit": 20}}]})
    monkeypatch.setattr(ask, "_model", model)
    assert ask._plan("帮我看这个笔记的评论 " + NOTE)[0]["action"] == "comments"


def test_comment_summary_does_not_truncate_to_two_or_reread_note(monkeypatch):
    def model(messages, **kwargs):
        sources = json.loads(messages[1]["content"])["sources"]
        assert len(sources) == 5
        assert sources[4]["text"] == "comment 4"
        assert sources[4]["content_scope"] == "loaded_comments"
        return "评论摘要"
    monkeypatch.setattr(ask, "_model", model)
    monkeypatch.setattr(mcp_server, "_invoke", lambda *a, **k: pytest.fail("unexpected re-query"))
    result = {"channel": "xiaohongshu", "action": "comments", "items": [
        {"url": NOTE, "text": f"comment {i}", "raw": {"content_scope": "loaded_comments"}}
        for i in range(5)]}
    assert "评论摘要" in ask._summarize("总结评论", [result])


def test_search_and_comment_intent_collects_comments_once(monkeypatch):
    calls = []
    def invoke(name, args):
        calls.append(args["action"])
        return {"ok": True, "items": [{"author": "A", "text": "喜欢", "raw": {}}]}
    def model(messages, **kwargs):
        sources = json.loads(messages[1]["content"])["sources"]
        assert sources[0]["comments"][0]["text"] == "喜欢"
        assert "not an exhaustive" in sources[0]["comments_status"]
        return "评论样本摘要"
    monkeypatch.setattr(mcp_server, "_invoke", invoke)
    monkeypatch.setattr(ask, "_model", model)
    ask._summarize("找一篇笔记并总结评论", [{"channel": "xiaohongshu", "action": "search", "items": [
        {"url": NOTE, "title": "笔记", "text": "正文", "raw": {}}]}])
    assert calls == ["comments"]


def test_comments_validate_before_prepare(monkeypatch):
    from agent_reach.runtime import flow
    from agent_reach.runtime.result import ReachError
    monkeypatch.setattr(flow, "prepare", lambda *a, **k: pytest.fail("unexpected setup"))
    with pytest.raises(ReachError) as caught:
        flow.execute("xiaohongshu", "comments", {"target": "invalid", "limit": 999})
    assert caught.value.code == "BAD_INPUT"


def test_empty_comments_are_a_successful_answer(monkeypatch):
    monkeypatch.setattr(ask, "_plan", lambda *a: [{"channel": "xiaohongshu", "action": "comments",
                                                  "params": {"target": NOTE}}])
    monkeypatch.setattr(mcp_server, "_invoke", lambda *a: {
        "ok": True, "channel": "xiaohongshu", "action": "comments", "items": []})
    monkeypatch.setattr(ask, "_model", lambda *a, **k: pytest.fail("empty result needs no model"))
    result = ask.ask("这个笔记有哪些评论 " + NOTE)
    assert result["ok"] and result["status"] == "ready"
    assert result["answer"] == "本次查询未返回结果。"


def test_detail_login_step_is_preserved(monkeypatch):
    monkeypatch.setattr(ask, "_plan", lambda *a: [{"channel": "xiaohongshu", "action": "search",
                                                  "params": {"query": "VLA"}}])
    def invoke(name, args):
        if args["action"] == "search":
            return {"ok": True, "channel": "xiaohongshu", "action": "search",
                    "items": [{"title": "笔记", "url": NOTE}]}
        return {"ok": False, "channel": "xiaohongshu", "status": "needs_user_action",
                "operation_id": "op_read", "required_action": {"type": "login"}}
    monkeypatch.setattr(mcp_server, "_invoke", invoke)
    monkeypatch.setattr(ask, "_model", lambda *a, **k: "已有搜索摘要")
    result = ask.ask("找笔记并总结")
    assert result["status"] == "needs_user_action" and result["answer"].startswith("已有搜索摘要")
    assert result["pending_operations"] == ["op_read"]


def test_resume_keeps_new_comment_login_step(monkeypatch):
    from agent_reach.runtime import flow, state
    ask._remember("op_search", "找笔记并总结评论")
    monkeypatch.setattr(flow, "resume", lambda *a: {
        "ok": True, "status": "ready", "channel": "xiaohongshu", "action": "search",
        "items": [{"title": "笔记", "url": NOTE, "text": "正文"}]})
    monkeypatch.setattr(mcp_server, "_invoke", lambda *a, **k: {
        "ok": False, "channel": "xiaohongshu", "status": "needs_user_action",
        "operation_id": "op_comments", "required_action": {"type": "login"}})
    monkeypatch.setattr(ask, "_model", lambda *a, **k: "评论尚不可读")
    result = ask.resume("op_search")
    assert result["status"] == "needs_user_action"
    assert result["pending_operations"] == ["op_comments"]
    assert state.load()["ask_pending"]["op_comments"]["instruction"] == "找笔记并总结评论"


def test_boss_read_does_not_acquire_search_limit(monkeypatch):
    url = "https://www.zhipin.com/job_detail/abc.html"
    monkeypatch.setattr(ask, "_model", lambda *a, **k: json.dumps({"requests": [
        {"channel": "boss", "action": "read", "params": {"target": url}}]}))
    assert "limit" not in ask._plan("读这个最高薪职位 " + url)[0]["params"]
