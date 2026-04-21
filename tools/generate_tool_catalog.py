#!/usr/bin/env python3
"""Generate docs/mcp-tool-catalog.md from MCP tool registrations."""

from __future__ import annotations

import sys
from pathlib import Path


def _escape(text: str) -> str:
    return " ".join(text.replace("|", r"\|").split())


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "gateway"))

    from gateway.mcp_server import ALL_TOOL_MODULES  # pylint: disable=import-error

    output_path = repo_root / "docs" / "mcp-tool-catalog.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# MCP Tool Catalog")
    lines.append("")

    total_tools = sum(len(module.TOOLS) for module in ALL_TOOL_MODULES)
    lines.append(f"Total tools: **{total_tools}**.")
    lines.append("")
    lines.append("Generated from `gateway/gateway/mcp_server.py` tool modules.")
    lines.append("Regenerate with: `python3 tools/generate_tool_catalog.py`.")
    lines.append("")

    for module in ALL_TOOL_MODULES:
        module_name = module.__name__.split(".")[-1]
        tools = sorted(module.TOOLS, key=lambda tool: tool.name)
        lines.append(f"## `{module_name}` ({len(tools)})")
        lines.append("")
        lines.append("| Tool | Description |")
        lines.append("|------|-------------|")
        for tool in tools:
            lines.append(f"| `{tool.name}` | {_escape(tool.description)} |")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
