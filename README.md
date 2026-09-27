# mcp-agent-sol

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
git clone https://github.com/Soller211/mcp-agent-sol && cd mcp-agent-sol
uv sync                                   # o: python -m venv .venv && .venv/bin/pip install -e .
```

**Token de GitHub:** se usa `GITHUB_TOKEN`; si no existe, el de la CLI `gh` (`gh auth login`). Recomendado: un token de solo lectura, ver [Seguridad](#seguridad).

**Claude:** el agente usa tu sesión de Claude Code o la variable `ANTHROPIC_API_KEY`. Cada informe consume tokens (unos $0.05–0.10 con el modelo por defecto).

## Uso del agente

```bash
uv run python agent.py "update de Soller211/customTenisDev de octubre 2022"
uv run python agent.py "update semanal de owner/repo" > update.md
uv run python agent.py "¿qué bugs abiertos tiene owner/repo?"
```

El informe sale por stdout; las llamadas a herramientas y el coste, por stderr. Ejemplo real:

```
→ search_issues({'query': 'is:pr is:merged merged:2026-09-20..2026-09-27', ...})
→ search_issues({'query': 'is:issue closed:2026-09-20..2026-09-27', ...})
→ search_issues({'query': 'is:pr is:open', ...})
→ search_issues({'query': 'is:issue is:open', ...})
→ get_issue({'number': 18})
→ get_issue({'number': 15})
→ get_issue({'number': 14})
[8 turnos · $0.0628]
# Update: Soller211/customTenisDev (2026-09-20 → 2026-09-27)
**Resumen:** Esta semana se cerró 1 issue de documentación (README) y no se mergeó ningún PR. No hay PRs abiertos. Quedan 5 issues abiertos: 2 bugs, 2 mejoras y 1 bloqueado, que es la integración de la pasarela de pago y está esperando las credenciales del proveedor.

## ✅ Hecho
- [#19](...) Actualizar README con capturas y cómo ejecutar el proyecto (`documentation`), cerrado el 2026-09-27.
...
## ⚠️ Riesgos / bloqueos
- [#18](...) Pasarela de pago bloqueada: según el último comentario, está "esperando credenciales del proveedor de pagos".
```

El agente solo abre el detalle (`get_issue`) de lo que parece bloqueado o es un bug: el número de llamadas se adapta a los datos.

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

**Probarlo a mano** con el MCP Inspector: `npx @modelcontextprotocol/inspector@0.15.0 .venv/bin/python server.py` (ciérralo con Ctrl+C al terminar: puede lanzar comandos).
En WSL, abre `http://localhost:6274` en el navegador de Windows (con `127.0.0.1` la conexión puede ser rechazada).

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

## Seguridad

La IA decide qué herramientas llamar, pero solo dentro de lo que este código permite:

- **Solo lectura.** El servidor solo hace `GET` a `api.github.com` (sin redirecciones) y el agente solo tiene `search_issues` y `get_issue`: sin Bash, sin escritura de archivos (`tools=[]`).
- **Entradas validadas.** `repo` debe tener formato `owner/nombre` (bloquea rutas como `a/b/../../user`), y `query` no admite `repo:`/`org:`/`user:`, `OR`/`AND`/`NOT` ni paréntesis, que permitirían buscar fuera del repo.
- **Aislado de tu configuración.** `setting_sources=[]` y `strict_mcp_config=True`: el agente ignora `~/.claude`, `.claude/` del proyecto (y sus *hooks*) y otros servidores MCP.
- **Contenido no confiable.** Issues y comentarios los escribe cualquiera y pueden intentar *prompt injection*. El prompt le indica tratarlos como datos; al ser de solo lectura, lo peor posible es un informe engañoso. **Revisa el informe antes de publicarlo.**

**Usa un token de mínimo privilegio.** El token de `gh` suele tener permisos de escritura y administración. Crea un [fine-grained token](https://github.com/settings/personal-access-tokens/new) con acceso solo a los repos que quieras y permisos *Issues: Read* y *Pull requests: Read*, y expórtalo:

```bash
export GITHUB_TOKEN=github_pat_...
```

Así, aunque el código cambiara, GitHub no permitiría escribir ni leer otros repos.

Lo que el agente envía al modelo (títulos, cuerpos y comentarios de issues) sale de tu máquina hacia Anthropic, o hacia el servidor del modelo que configures.

## Límites y siguientes pasos

- Una sola página de búsqueda (máx. 100 resultados por consulta). Siguiente paso: paginación.
- La búsqueda de GitHub permite ~30 peticiones/minuto con token. Siguiente paso si se usa a escala: caché.
- Solo lectura. Siguiente paso posible: herramienta para publicar el informe como comentario en un issue.
- Los informes los redacta un LLM: revísalos antes de compartirlos.

## Desarrollo

```bash
uv run pytest -q
```

## Licencia

[MIT](LICENSE)
