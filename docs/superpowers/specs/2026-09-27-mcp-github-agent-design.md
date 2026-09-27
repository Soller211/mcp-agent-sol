# MCP GitHub Agent — Diseño

Fecha: 2026-09-27

## Objetivo

Un servidor MCP que expone la API de GitHub como herramientas, y un agente
(Claude Agent SDK) que las usa para buscar issues/PRs y redactar project updates.
Proyecto de aprendizaje, publicado como código libre (MIT) y usable tal cual por
quien haga fork.

## Arquitectura

```
usuario ──▶ agent.py (Claude Agent SDK) ──stdio/MCP──▶ server.py (MCPServer) ──HTTPS──▶ GitHub REST API
```

- `server.py` no sabe nada de Claude: solo sabe acceder a GitHub.
- `agent.py` no sabe hablar con GitHub: solo decide qué herramientas usar.
- Son procesos separados; el agente lanza el servidor como subproceso por stdio.

## Componentes

### server.py

Servidor MCP con `MCPServer` (MCP Python SDK 2.x; en 1.x se llamaba `FastMCP`), transporte stdio, cliente `httpx`.

**`search_issues(repo: str, query: str = "", limit: int = 30)`**
- Llama a `GET /search/issues` con `q = "repo:{repo} {query}"`, `per_page = min(limit, 100)`.
- `query` acepta la sintaxis de búsqueda de GitHub tal cual (`is:pr`, `is:open`,
  `label:bug`, `merged:2022-10-01..2022-10-31`, texto libre, ...).
- Devuelve `{total_count, items: [...]}`; cada item contiene: `number`, `title`,
  `type` (`issue`|`pr`), `state`, `merged` (bool, solo PRs), `author`, `labels`,
  `created_at`, `updated_at`, `closed_at`, `merged_at`, `url`, `body` (primeros ~300 caracteres).
- Solo una página. Marcado con `ponytail:` → paginar cuando un repo lo necesite.

**`get_issue(repo: str, number: int)`**
- Devuelve el issue/PR con cuerpo completo y sus comentarios
  (`GET /repos/{repo}/issues/{number}` + `/comments`).

**Token:** `GITHUB_TOKEN`; si no existe, salida de `gh auth token`; si tampoco,
error: "Falta GITHUB_TOKEN; exporta uno o ejecuta `gh auth login`".

**Errores de GitHub** (404, rate limit, etc.): se lanzan como error de herramienta
con el mensaje de GitHub, para que el modelo lo lea y lo explique. Debe ser `ToolError`:
  una excepción genérica oculta el mensaje al cliente.

### agent.py

- Uso: `python agent.py "<petición en lenguaje natural>"`. Sin flags.
- `ClaudeAgentOptions`:
  - `mcp_servers`: lanza `server.py` por stdio con el mismo intérprete de Python.
  - Solo se permiten `search_issues` y `get_issue`; ninguna herramienta integrada
    (sin Bash, sin escritura de archivos). Agente de solo lectura.
  - Aislado de la configuración local: `tools=[]`, `setting_sources=[]`, `skills=[]`,
    `strict_mcp_config=True`, así se comporta igual en cualquier fork. `max_turns=15`.
  - Prompt de sistema con la fecha de hoy y el procedimiento de abajo.
- Modelo: el por defecto del SDK; configurable con `ANTHROPIC_MODEL`
  (y `ANTHROPIC_BASE_URL` para modelos locales / proxies).

**Procedimiento (prompt de sistema):**
1. Identificar repo y periodo; sin periodo → últimos 7 días.
2. Hecho: PRs mergeados e issues cerrados en el periodo.
3. En curso: PRs abiertos.
4. Pendiente: issues abiertos.
5. Riesgos: `get_issue` solo para lo que parezca bloqueado (labels `blocked`/`bug`,
   o sin actividad > 14 días).
6. Redactar con la plantilla; no inventar; cada punto enlaza su `#número`.
Si la petición es una pregunta y no un informe, responder directamente.

**Plantilla (en el idioma de la petición):**
```markdown
# Update: owner/repo (AAAA-MM-DD → AAAA-MM-DD)
**Resumen:** 2–3 líneas.
## ✅ Hecho
## 🔄 En curso
## 📋 Pendiente
## ⚠️ Riesgos / bloqueos
## 📊 Números
```

**Salida:** informe final → stdout. Llamadas a herramientas (`→ search_issues(...)`),
coste y turnos → stderr.

## Estructura del repo

```
server.py  agent.py  test_server.py  pyproject.toml  README.md  LICENSE  .gitignore
```

Dependencias: `mcp`, `claude-agent-sdk`, `httpx`. Python ≥ 3.10.
Instalación: `uv sync` (alternativa: `python -m venv .venv && pip install -e .`).

## README

1. Qué es (diagrama). 2. Cómo funciona (recorrido de una petición). 3. Instalación
y token. 4. Uso del agente. 5. Usar solo el servidor (Claude Code `claude mcp add`,
Claude Desktop). 6. Modelos locales (LiteLLM + `ANTHROPIC_BASE_URL`, Qwen-Agent;
advertencia sobre modelos pequeños). 7. Límites y siguientes pasos. 8. Licencia MIT.

## Pruebas

- `test_server.py`: valida el formateo de resultados con datos falsos, sin red.
- Manual: MCP Inspector contra `Soller211/customTenisDev`.
- Manual: agente en dos periodos — octubre 2022 (13 PRs mergeados) y semana actual
  (issues de prueba nuevos).

## Datos de prueba

Crear 5–8 issues en `Soller211/customTenisDev`. Requiere confirmación explícita
del usuario antes de crearlos (lo hace el usuario, o Claude con `gh` tras aprobar
la lista).

## Fuera de alcance (por ahora)

Herramientas de escritura, publicar el informe en GitHub, paginación completa,
caché, listar repos, PyPI, Docker, GitHub Enterprise, agente alternativo con
cliente OpenAI para vLLM. Subir el repo a GitHub: al final, con confirmación.
