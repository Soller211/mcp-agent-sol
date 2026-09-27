import asyncio

import httpx
from mcp.client.client import Client

import server

PR = {
    "number": 13, "title": "bannner", "state": "closed",
    "user": {"login": "Soller211"}, "labels": [{"name": "enhancement"}],
    "created_at": "2022-10-26T10:00:00Z", "updated_at": "2022-10-26T12:00:00Z",
    "closed_at": "2022-10-26T12:00:00Z",
    "html_url": "https://github.com/o/r/pull/13", "body": None,
    "pull_request": {"merged_at": "2022-10-26T12:00:00Z"},
}
ISSUE = {
    "number": 20, "title": "Banner roto en móvil", "state": "open",
    "user": {"login": "Soller211"}, "labels": [],
    "created_at": "2026-09-27T10:00:00Z", "updated_at": "2026-09-27T10:00:00Z",
    "closed_at": None, "html_url": "https://github.com/o/r/issues/20", "body": "x" * 1000,
}


def test_slim_pr():
    s = server.slim(PR)
    assert s["type"] == "pr" and s["merged"] is True
    assert s["merged_at"] == "2022-10-26T12:00:00Z"
    assert s["labels"] == ["enhancement"] and s["author"] == "Soller211"
    assert s["body"] == ""


def test_slim_issue_truncates_body():
    s = server.slim(ISSUE)
    assert s["type"] == "issue" and s["merged"] is False and s["merged_at"] is None
    assert len(s["body"]) == server.BODY_CHARS


def test_search_builds_query_and_caps_limit(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        return {"total_count": 250, "items": [PR, ISSUE]}

    monkeypatch.setattr(server, "gh_get", fake_get)
    out = server.search_issues("o/r", "is:pr is:merged", limit=500)
    assert calls == [("/search/issues", {"q": "repo:o/r is:pr is:merged", "per_page": 100})]
    assert out["total_count"] == 250
    assert [i["number"] for i in out["items"]] == [13, 20]


def test_github_error_reaches_mcp_client(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(404, text='{"message":"Not Found"}'))

    async def call():
        async with Client(server.mcp) as c:
            return await c.call_tool("search_issues", {"repo": "o/no-existe"})

    r = asyncio.run(call())
    assert r.is_error
    assert "GitHub 404" in r.content[0].text
