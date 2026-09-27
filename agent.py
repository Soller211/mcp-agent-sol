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
