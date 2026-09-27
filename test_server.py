import asyncio

import httpx
import pytest
from mcp.client.client import Client
from mcp.server.mcpserver.exceptions import ToolError

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


def test_rejects_bad_repo_before_calling_github(monkeypatch):
    monkeypatch.setattr(server, "gh_get", lambda *a, **k: pytest.fail("no debe llamar a GitHub"))
    for repo in ["a/b/../../../user?", "a/..", "../b", "a", "a/b/c", "a/b?x=1", "a b/c", ""]:
        with pytest.raises(ToolError, match="owner/nombre"):
            server.get_issue(repo, 1)
        with pytest.raises(ToolError, match="owner/nombre"):
            server.search_issues(repo)


def test_rejects_query_that_escapes_repo(monkeypatch):
    monkeypatch.setattr(server, "gh_get", lambda *a, **k: pytest.fail("no debe llamar a GitHub"))
    for query in ["repo:octocat/Hello-World", "is:pr (org:github)", "-user:x", "USER:x",
                  "is:issue OR is:pr", "bug AND label:x", "NOT is:open"]:
        with pytest.raises(ToolError, match="query"):
            server.search_issues("o/r", query)


def test_accepts_normal_repo_and_query(monkeypatch):
    monkeypatch.setattr(server, "gh_get", lambda *a, **k: {"total_count": 0, "items": []})
    for repo in ["Soller211/customTenisDev", "my.org-1/repo_name.js"]:
        server.search_issues(repo, "is:pr is:merged merged:2022-10-01..2022-10-31 label:bug myrepo: or")


def test_github_error_reaches_mcp_client(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(404, text='{"message":"Not Found"}'))

    async def call():
        async with Client(server.mcp) as c:
            return await c.call_tool("search_issues", {"repo": "o/no-existe"})

    r = asyncio.run(call())
    assert r.is_error
    assert "GitHub 404" in r.content[0].text
