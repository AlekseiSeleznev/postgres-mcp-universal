from pathlib import Path

from gateway.mcp_server import ALL_TOOL_MODULES


def test_generated_tool_catalog_is_synced_with_registered_tools():
    repo_root = Path(__file__).resolve().parents[2]
    catalog = (repo_root / "docs" / "mcp-tool-catalog.md").read_text(encoding="utf-8")

    total = sum(len(module.TOOLS) for module in ALL_TOOL_MODULES)
    assert f"Total tools: **{total}**." in catalog

    for module in ALL_TOOL_MODULES:
        module_name = module.__name__.split(".")[-1]
        assert f"## `{module_name}` ({len(module.TOOLS)})" in catalog
        for tool in module.TOOLS:
            assert f"`{tool.name}`" in catalog
