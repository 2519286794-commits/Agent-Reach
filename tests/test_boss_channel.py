# -*- coding: utf-8 -*-
"""Dedicated tests for the ``boss`` channel."""

from agent_reach.channels.boss import BossChannel


def test_can_handle_matches_zhipin_hosts():
    ch = BossChannel()
    for url in [
        "https://www.zhipin.com/job_detail/abc.html",
        "https://zhipin.com/web/geek/job?query=大模型",
    ]:
        assert ch.can_handle(url) is True, url
    for url in [
        "https://example.com",
        "https://zhipin.com.evil.test/job",
        "",
        "https://user@zhipin.com/job",
    ]:
        assert ch.can_handle(url) is False, url
