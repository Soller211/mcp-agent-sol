# MCP GitHub Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Servidor MCP que expone búsqueda de issues/PRs de GitHub + agente (Claude Agent SDK) que lo usa para redactar project updates en Markdown.

**Architecture:** `server.py` (MCP Python SDK 2.x, `MCPServer`, stdio) llama a la API REST de GitHub con `httpx`. `agent.py` lanza `server.py` como subproceso MCP y deja que Claude decida qué herramientas llamar; el informe va a stdout y la traza de herramientas a stderr.

**Tech Stack:** Python ≥3.10, `mcp` 2.x, `claude-agent-sdk` 0.2.x, `httpx`, `pytest`, `uv`.

**Spec:** `docs/superpowers/specs/2026-09-27-mcp-github-agent-design.md`

## Global Constraints

- Python `>=3.10`. Dependencias: `mcp>=2.2`, `claude-agent-sdk>=0.2.160`, `httpx>=0.28`; dev: `pytest>=9`. Ninguna más.
- `mcp` 2.x: la clase es `from mcp.server.mcpserver import MCPServer` (NO `FastMCP`, que no existe en 2.x).
- Errores de herramienta: lanzar `mcp.server.mcpserver.exceptions.ToolError`; una excepción genérica oculta el mensaje al cliente.
- Nada fijado a un repo concreto en el código: repo y periodo vienen de la petición.
- Token: `GITHUB_TOKEN`, si no `gh auth token`, si no error "Falta GITHUB_TOKEN; exporta uno o ejecuta `gh auth login`".
- Agente de solo lectura y aislado: `tools=[]`, `setting_sources=[]`, `skills=[]`, `strict_mcp_config=True`, `allowed_tools` = solo las 2 herramientas MCP.
- Licencia MIT, titular "Soller211".
- Ejecutar todo con `~/.local/bin/uv` (uv está instalado ahí; puede no estar en el PATH).
- Commits terminan con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Nada se publica en GitHub (issues, push) sin confirmación explícita del usuario.

---

### Task 1: Proyecto + servidor MCP (con tests)

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `LICENSE`, `server.py`, `test_server.py`

**Interfaces:**
- Produces: `server.mcp` (instancia `MCPServer` llamada `"github-updates"`), herramientas MCP `search_issues(repo: str, query: str = "", limit: int = 30) -> dict` y `get_issue(repo: str, number: int) -> dict`, `server.gh_get(path: str, params: dict | None = None) -> dict | list`, `server.slim(item: dict) -> dict`. Se ejecuta con `python server.py` (stdio).

- [ ] **Step 1: Crear `pyproject.toml`, `.gitignore`, `LICENSE`**

`pyproject.toml`:
```toml
[project]
name = "mcp-github-agent"
version = "0.1.0"
description = "Servidor MCP + agente que busca issues de GitHub y redacta project updates"
readme = "README.md"
license = "MIT"
requires-python = ">=3.10"
dependencies = ["mcp>=2.2", "claude-agent-sdk>=0.2.160", "httpx>=0.28"]

[dependency-groups]
dev = ["pytest>=9"]

[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
py-modules = ["server", "agent"]
```

`.gitignore`:
```
.venv/
__pycache__/
.pytest_cache/
*.egg-info/
build/
```

`LICENSE`: texto MIT estándar con `Copyright (c) 2026 Soller211`:
```
MIT License

Copyright (c) 2026 Soller211

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

`README.md` se escribe en Task 4; crear uno provisional de una línea (`# mcp-github-agent`) para que `readme =` resuelva.

Run: `~/.local/bin/uv sync`
Expected: crea/actualiza `.venv` y `uv.lock` sin errores.

- [ ] **Step 2: Escribir los tests (fallan porque no existe `server.py`)**

`test_server.py`:
```python
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
```

Run: `~/.local/bin/uv run pytest -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'server'`.

- [ ] **Step 3: Implementar `server.py`**

```python
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
```

- [ ] **Step 4: Ejecutar los tests**

Run: `~/.local/bin/uv run pytest -q`
Expected: `4 passed`.

- [ ] **Step 5: Prueba real contra GitHub (sin agente)**

Run:
```bash
~/.local/bin/uv run python -c "
import server, json
r = server.search_issues('Soller211/customTenisDev', 'is:pr is:merged merged:2022-10-01..2022-10-31')
print(r['total_count'], [i['number'] for i in r['items']])
print(json.dumps(server.get_issue('Soller211/customTenisDev', 13), ensure_ascii=False)[:300])
"
```
Expected: `13 [...]` con los 13 números de PR, y el JSON del PR #13 con `"merged": true`.

- [ ] **Step 6: Prueba del protocolo por stdio (lo que hará el agente)**

Run:
```bash
~/.local/bin/uv run python -c "
import asyncio, sys
from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters
async def main():
    async with Client(StdioServerParameters(command=sys.executable, args=['server.py'])) as c:
        print([t.name for t in (await c.list_tools()).tools])
        r = await c.call_tool('search_issues', {'repo': 'Soller211/customTenisDev', 'query': 'is:pr', 'limit': 2})
        print(r.is_error, r.content[0].text[:200])
asyncio.run(main())
"
```
Expected: `['search_issues', 'get_issue']` y `False {...`. Si la firma de `Client`/`StdioServerParameters` difiere, revisar `mcp/client/client.py` (docstring de `class Client`) y ajustar solo este comando.

Opcional (manual, interactivo, para el usuario): `npx @modelcontextprotocol/inspector ~/.local/bin/uv run python server.py`.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock .gitignore LICENSE README.md server.py test_server.py
git commit -m "feat: add GitHub MCP server with search_issues and get_issue

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Agente

**Files:**
- Create: `agent.py`

**Interfaces:**
- Consumes: `server.py` ejecutable por stdio; herramientas expuestas al agente como `mcp__github__search_issues` y `mcp__github__get_issue` (prefijo `mcp__<nombre del servidor>__`).
- Produces: CLI `python agent.py "<petición>"` → informe en stdout, traza en stderr, código de salida ≠ 0 si falla.

- [ ] **Step 1: Implementar `agent.py`**

```python
"""Agente que prepara project updates de GitHub usando el servidor MCP de server.py."""
import asyncio
import sys
from datetime import date
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, ToolUseBlock, query

SERVER = Path(__file__).with_name("server.py")
TOOLS = ["mcp__github__search_issues", "mcp__github__get_issue"]

SYSTEM_PROMPT = f"""Eres un asistente que prepara project updates de repositorios de GitHub.
Hoy es {date.today().isoformat()}. Solo tienes herramientas de lectura: search_issues y get_issue.

Si te piden un update o informe:
1. Identifica el repo (owner/nombre) y el periodo. Si no se indica periodo, usa los últimos 7 días.
2. Hecho: PRs mergeados (is:pr is:merged merged:INICIO..FIN) e issues cerrados (is:issue closed:INICIO..FIN).
3. En curso: PRs abiertos (is:pr is:open).
4. Pendiente: issues abiertos (is:issue is:open).
5. Riesgos: usa get_issue solo con lo que parezca bloqueado (labels como blocked o bug, o updated_at de hace más de 14 días).
6. Redacta el informe con esta plantilla, en el idioma de la petición:

# Update: owner/repo (AAAA-MM-DD → AAAA-MM-DD)
**Resumen:** 2–3 líneas.
## ✅ Hecho
## 🔄 En curso
## 📋 Pendiente
## ⚠️ Riesgos / bloqueos
## 📊 Números

Cada punto enlaza su número con formato [#N](url). Si una sección no tiene nada, escribe "Nada.".
No inventes nada que no venga de las herramientas.

Si la petición es una pregunta y no un informe, respóndela directamente, sin plantilla.
Tu respuesta final es solo el resultado, sin comentarios sobre el proceso."""


async def main(prompt: str) -> None:
    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"github": {"command": sys.executable, "args": [str(SERVER)]}},
        strict_mcp_config=True,
        tools=[],  # sin herramientas integradas (Bash, Edit...): solo lectura vía MCP
        allowed_tools=TOOLS,
        setting_sources=[],  # no cargar ~/.claude ni .claude/ del proyecto: mismo comportamiento en cualquier fork
        skills=[],
        max_turns=15,
    )
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, ToolUseBlock):
                    print(f"→ {block.name.removeprefix('mcp__github__')}({block.input})", file=sys.stderr)
        elif isinstance(msg, ResultMessage):
            print(f"[{msg.num_turns} turnos · ${msg.total_cost_usd or 0:.4f}]", file=sys.stderr)
            if msg.is_error:
                sys.exit(f"Error: {msg.result or msg.subtype}")
            print(msg.result)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit('Uso: python agent.py "update de owner/repo de la última semana"')
    asyncio.run(main(sys.argv[1]))
```

- [ ] **Step 2: Comprobar el mensaje de uso**

Run: `~/.local/bin/uv run python agent.py; echo "exit=$?"`
Expected: `Uso: python agent.py "..."` y `exit=1`.

- [ ] **Step 3: Ejecución real — periodo histórico**

Run: `~/.local/bin/uv run python agent.py "update de Soller211/customTenisDev de octubre 2022" > /tmp/claude-1000/update-2022.md; cat /tmp/claude-1000/update-2022.md`
Expected:
- stderr muestra `→ search_issues({...merged:2022-10-01..2022-10-31...})` y una línea `[N turnos · $X]`.
- El informe tiene la plantilla, "Hecho" lista los 13 PRs con enlaces `[#N](url)`, "📊 Números" dice 13 PRs mergeados.
- Si falla la autenticación de Claude: el SDK usa las credenciales de Claude Code (`~/.claude/.credentials.json`) o `ANTHROPIC_API_KEY`. Reportar el error exacto al usuario; no cambiar el código para esquivarlo.

- [ ] **Step 4: Ejecución real — pregunta directa**

Run: `~/.local/bin/uv run python agent.py "¿cuántos PRs tiene Soller211/customTenisDev y quién los hizo?"`
Expected: respuesta directa sin plantilla, basada en `search_issues`.

- [ ] **Step 5: Commit**

```bash
git add agent.py
git commit -m "feat: add project update agent using the GitHub MCP server

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Issues de prueba en `Soller211/customTenisDev`

**⚠️ Publica contenido en GitHub. Antes del Step 2, mostrar la lista al usuario y esperar su "sí" explícito. Si prefiere crearlos él, saltar al Step 3.**

**Files:** ninguno.

**Interfaces:**
- Produces: issues abiertos (incl. uno con label `blocked` y un comentario) y al menos un issue cerrado hoy, para que el update de la semana actual tenga contenido en todas las secciones.

- [ ] **Step 1: Mostrar al usuario la lista propuesta**

| # | Título | Label | Estado final |
|---|--------|-------|--------------|
| 1 | El banner no se adapta en pantallas móviles | bug | abierto |
| 2 | Traducción incompleta al inglés en la página de productos | bug | abierto |
| 3 | Añadir selector de color para las suelas | enhancement | abierto |
| 4 | Galería de modelos personalizados por clientes | enhancement | abierto |
| 5 | Integrar pasarela de pago | blocked | abierto + comentario "Esperando credenciales del proveedor de pagos." |
| 6 | Actualizar README con capturas y cómo ejecutar el proyecto | documentation | cerrado hoy |

- [ ] **Step 2: Crearlos (solo tras el "sí")**

```bash
R=Soller211/customTenisDev
gh label create blocked -R $R --color B60205 --description "Bloqueado por una dependencia externa" 2>/dev/null || true
gh issue create -R $R -t "El banner no se adapta en pantallas móviles" -b "En anchos < 480px el banner se corta y el texto se sale del contenedor." -l bug
gh issue create -R $R -t "Traducción incompleta al inglés en la página de productos" -b "Al cambiar a inglés, las descripciones de productos siguen en español." -l bug
gh issue create -R $R -t "Añadir selector de color para las suelas" -b "Permitir elegir el color de la suela en el personalizador." -l enhancement
gh issue create -R $R -t "Galería de modelos personalizados por clientes" -b "Sección con fotos de tenis personalizados por clientes." -l enhancement
P=$(gh issue create -R $R -t "Integrar pasarela de pago" -b "Añadir checkout con pago en línea." -l blocked)
gh issue comment "$P" -b "Esperando credenciales del proveedor de pagos."
D=$(gh issue create -R $R -t "Actualizar README con capturas y cómo ejecutar el proyecto" -b "El README no explica cómo ver el proyecto en local." -l documentation)
gh issue close "$D" -c "Hecho."
gh issue list -R $R --state all
```
Expected: 6 issues listados (5 OPEN, 1 CLOSED).

- [ ] **Step 3: Ejecución real — semana actual**

Run: `~/.local/bin/uv run python agent.py "update semanal de Soller211/customTenisDev"`
Expected: periodo = últimos 7 días; "Hecho" incluye el issue del README; "Pendiente" los 4 abiertos; "Riesgos" menciona la pasarela de pago y su comentario (stderr muestra al menos un `→ get_issue(...)`).

Sin commit (no hay cambios en el repo).

---

### Task 4: README

**Files:**
- Modify: `README.md` (reemplazar el provisional)

- [ ] **Step 1: Escribir `README.md`**

Sustituir `<SALIDA REAL>` por la salida real (recortada a ~15 líneas) del Step 3 de la Task 2 antes de guardar; es el único hueco y se rellena con datos, no con texto inventado.

````markdown
# mcp-github-agent

Un **servidor MCP** que da a una IA acceso de lectura a los issues y pull requests de GitHub, y un **agente** (Claude Agent SDK) que lo usa para redactar *project updates* automáticamente.

```
 "update de owner/repo de octubre"
            │
            ▼
 ┌──────────────────────┐   herramientas MCP   ┌─────────────────────┐   HTTPS   ┌────────────┐
 │  agent.py            │ ───────────────────▶ │  server.py          │ ────────▶ │ GitHub API │
 │  Claude Agent SDK    │ ◀─────────────────── │  MCP Python SDK     │ ◀──────── │            │
 │  decide y redacta    │       JSON           │  search_issues      │           └────────────┘
 └──────────────────────┘                      │  get_issue          │
                                               └─────────────────────┘
```

## Cómo funciona

1. `agent.py` arranca `server.py` como **subproceso** y se conecta a él por **stdio** usando el protocolo MCP.
2. El servidor anuncia sus herramientas (nombre, descripción, parámetros). Claude las ve como cualquier otra herramienta.
3. Claude lee tu petición y decide qué buscar, por ejemplo `search_issues(repo, "is:pr is:merged merged:2022-10-01..2022-10-31")`.
4. El servidor traduce la llamada a la API REST de GitHub, recorta la respuesta a los campos útiles y la devuelve como JSON.
5. Claude repite los pasos 3–4 las veces que haga falta (hecho, en curso, pendiente, riesgos) y redacta el informe.

La separación es la idea clave: **el servidor sabe *cómo* acceder a GitHub; el agente decide *qué* hacer**. Por eso el servidor sirve también para otros clientes (Claude Code, Claude Desktop, modelos locales).

## Instalación

Requisitos: Python ≥ 3.10 y un token de GitHub.

```bash
git clone https://github.com/Soller211/mcp-github-agent && cd mcp-github-agent
uv sync                                   # o: python -m venv .venv && .venv/bin/pip install -e .
```

**Token de GitHub:** se usa `GITHUB_TOKEN`; si no existe, el de la CLI `gh` (`gh auth login`). Para repos públicos basta un token sin permisos; para privados, permiso de lectura de issues y PRs.

**Claude:** el agente usa tu sesión de Claude Code o la variable `ANTHROPIC_API_KEY`. Cada informe consume tokens.

## Uso del agente

```bash
uv run python agent.py "update de Soller211/customTenisDev de octubre 2022"
uv run python agent.py "update semanal de owner/repo" > update.md
uv run python agent.py "¿qué bugs abiertos tiene owner/repo?"
```

El informe sale por stdout; las llamadas a herramientas y el coste, por stderr:

```
<SALIDA REAL>
```

Cambiar de modelo: `ANTHROPIC_MODEL=claude-sonnet-5 uv run python agent.py "..."`.

## Usar solo el servidor MCP

**Claude Code:**
```bash
claude mcp add github-updates -- /ruta/absoluta/.venv/bin/python /ruta/absoluta/server.py
```

**Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "github-updates": {
      "command": "/ruta/absoluta/.venv/bin/python",
      "args": ["/ruta/absoluta/server.py"]
    }
  }
}
```

**Probarlo a mano** con el MCP Inspector: `npx @modelcontextprotocol/inspector .venv/bin/python server.py`.

### Herramientas

| Herramienta | Parámetros | Devuelve |
|---|---|---|
| `search_issues` | `repo`, `query` (sintaxis de búsqueda de GitHub), `limit` (≤100) | `total_count` + lista compacta de issues/PRs |
| `get_issue` | `repo`, `number` | cuerpo completo + comentarios |

## Modelos locales (Qwen, vLLM, Ollama)

> No probado en este repo todavía; son las vías conocidas.

**El servidor** es independiente del modelo: cualquier cliente MCP lo puede usar. Ejemplo con [Qwen-Agent](https://github.com/QwenLM/Qwen-Agent) y un vLLM local:

```python
from qwen_agent.agents import Assistant

bot = Assistant(
    llm={"model": "Qwen/Qwen3-30B-A3B", "model_server": "http://localhost:8000/v1", "api_key": "EMPTY"},
    function_list=[{"mcpServers": {"github": {"command": ".venv/bin/python", "args": ["server.py"]}}}],
)
```

**El agente** habla el formato de la API de Anthropic. Para usarlo con un modelo local, pon delante un proxy que lo traduzca, como [LiteLLM](https://docs.litellm.ai/):

```bash
litellm --model hosted_vllm/Qwen/Qwen3-30B-A3B --api_base http://localhost:8000/v1 --port 4000
export ANTHROPIC_BASE_URL=http://localhost:4000 ANTHROPIC_API_KEY=local ANTHROPIC_MODEL=hosted_vllm/Qwen/Qwen3-30B-A3B
uv run python agent.py "update semanal de owner/repo"
```

Modelos pequeños (7B–14B) suelen fallar al encadenar llamadas a herramientas; usa uno de ~30B o más con buen *tool calling*.

## Límites y siguientes pasos

- Una sola página de búsqueda (máx. 100 resultados por consulta). Siguiente paso: paginación.
- La búsqueda de GitHub permite ~30 peticiones/minuto con token. Siguiente paso si se usa a escala: caché.
- Solo lectura. Siguiente paso posible: herramienta para publicar el informe como comentario en un issue.

## Desarrollo

```bash
uv run pytest -q
```

## Licencia

[MIT](LICENSE)
````

- [ ] **Step 2: Comprobar que no queda el hueco**

Run: `grep -c "<SALIDA REAL>" README.md`
Expected: `0`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Publicar en GitHub (solo con confirmación)

- [ ] **Step 1: Preguntar al usuario** si quiere crear el repo público `Soller211/mcp-github-agent`. Si dice que no, terminar aquí.
- [ ] **Step 2:** `gh repo create Soller211/mcp-github-agent --public --source . --push --description "Servidor MCP + agente que busca issues de GitHub y redacta project updates"`
- [ ] **Step 3:** `gh repo view Soller211/mcp-github-agent` muestra el repo con el README.
