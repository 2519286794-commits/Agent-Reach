# -*- coding: utf-8 -*-
"""Dedicated tests for Reddit's read-only multi-backend health check."""

from unittest.mock import Mock

from agent_reach.channels.reddit import RedditChannel


def test_can_handle_matches_reddit_hosts():
    channel = RedditChannel()
    for url in [
        "https://reddit.com/r/python",
        "https://www.reddit.com/r/python/comments/abc/title/",
        "https://old.reddit.com/r/python",
        "https://redd.it/abc123",
        "HTTPS://REDDIT.COM/r/Python",
    ]:
        assert channel.can_handle(url) is True, url


def test_can_handle_rejects_non_reddit():
    channel = RedditChannel()
    for url in ["https://example.com/r/python", "https://twitter.com/u", ""]:
        assert channel.can_handle(url) is False, url
















def _opencli(installed=True, broken=False, ready=True, hint=""):
    return Mock(installed=installed, broken=broken, ready=ready, hint=hint)
















