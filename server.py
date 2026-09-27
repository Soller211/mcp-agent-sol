"""Servidor MCP que expone la búsqueda de issues y PRs de GitHub como herramientas."""
import os
import subprocess
from functools import cache

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

mcp = MCPServer("github-updates")
API = "https://api.github.com"
BODY_CHARS = 300


@cache
def github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        try:
            token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
        except OSError:  # gh no está instalado
            token = ""
    if not token:
        raise ToolError("Falta GITHUB_TOKEN; exporta uno o ejecuta `gh auth login`")
    return token


def gh_get(path: str, params: dict | None = None) -> dict | list:
    headers = {
        "Authorization": f"Bearer {github_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        r = httpx.get(f"{API}{path}", params=params, headers=headers, timeout=30)
    except httpx.HTTPError as e:
        raise ToolError(f"No se pudo conectar con GitHub: {e}") from None
    if r.is_error:
        raise ToolError(f"GitHub {r.status_code}: {r.text[:500]}")
    return r.json()


def slim(item: dict) -> dict:
    """Deja solo los campos útiles para un informe (ahorra tokens al modelo)."""
    pr = item.get("pull_request")
    return {
        "number": item["number"],
        "title": item["title"],
        "type": "pr" if pr else "issue",
        "state": item["state"],
        "merged": bool(pr and pr.get("merged_at")),
        "author": item["user"]["login"],
        "labels": [label["name"] for label in item["labels"]],
        "created_at": item["created_at"],
        "updated_at": item["updated_at"],
        "closed_at": item["closed_at"],
        "merged_at": pr.get("merged_at") if pr else None,
        "url": item["html_url"],
        "body": (item.get("body") or "")[:BODY_CHARS],
    }


@mcp.tool()
def search_issues(repo: str, query: str = "", limit: int = 30) -> dict:
    """Busca issues y pull requests de un repo con la sintaxis de búsqueda de GitHub.

    repo: "owner/nombre".
    query: filtros de GitHub tal cual. Ejemplos: "is:pr is:merged merged:2022-10-01..2022-10-31",
    "is:issue is:open", "is:issue closed:>=2026-09-20", "label:bug", texto libre.
    limit: máximo de resultados (tope 100).
    Devuelve total_count (total real en GitHub) e items (como mucho `limit`).
    """
    # ponytail: una sola página (máx. 100 resultados); paginar con `page` si algún repo lo necesita
    params = {"q": f"repo:{repo} {query}".strip(), "per_page": max(1, min(limit, 100))}
    data = gh_get("/search/issues", params)
    return {"total_count": data["total_count"], "items": [slim(i) for i in data["items"]]}


@mcp.tool()
def get_issue(repo: str, number: int) -> dict:
    """Detalle de un issue o pull request: cuerpo completo y comentarios."""
    issue = gh_get(f"/repos/{repo}/issues/{number}")
    comments = gh_get(f"/repos/{repo}/issues/{number}/comments", {"per_page": 100})
    return {
        **slim(issue),
        "body": issue.get("body") or "",
        "comments": [
            {"author": c["user"]["login"], "created_at": c["created_at"], "body": c["body"]}
            for c in comments
        ],
    }


if __name__ == "__main__":
    mcp.run()
