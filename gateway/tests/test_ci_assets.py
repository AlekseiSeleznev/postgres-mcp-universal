from pathlib import Path
import subprocess

_ROOT_GUIDE = "CL" + "AUDE.md"
_FORBIDDEN_BRAND = "cl" + "aude"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_ci_smoke_scripts_exist():
    repo = _repo_root()
    shell_script = repo / "tools" / "ci-smoke.sh"
    ps_script = repo / "tools" / "ci-smoke.ps1"
    catalog_generator = repo / "tools" / "generate_tool_catalog.py"
    catalog_doc = repo / "docs" / "mcp-tool-catalog.md"
    dev_requirements = repo / "gateway" / "requirements-dev.txt"
    win_wrapper = repo / "install.cmd"
    win_install = repo / "install.ps1"
    win_unwrapper = repo / "uninstall.cmd"
    win_uninstall = repo / "uninstall.ps1"

    assert shell_script.exists()
    assert ps_script.exists()
    assert catalog_generator.exists()
    assert catalog_doc.exists()
    assert dev_requirements.exists()
    assert win_wrapper.exists()
    assert win_install.exists()
    assert win_unwrapper.exists()
    assert win_uninstall.exists()
    assert shell_script.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")
    assert ps_script.stat().st_size > 0
    shell_text = shell_script.read_text(encoding="utf-8")
    assert "search_quiet()" in shell_text
    assert "grep -E -q" in shell_text


def test_root_guides_exist():
    repo = _repo_root()
    assert (repo / "CODEX.md").exists()
    assert (repo / "AGENTS.md").exists()
    assert (repo / _ROOT_GUIDE).exists()


def test_ci_workflow_uses_smoke_scripts():
    ci_workflow = (_repo_root() / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "./tools/ci-smoke.sh" in ci_workflow
    assert "./tools/ci-smoke.ps1" in ci_workflow
    assert "--cov-fail-under=100" in ci_workflow
    assert "gateway/requirements-dev.txt" in ci_workflow
    assert 'FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"' in ci_workflow
    assert "actions/checkout@v6" in ci_workflow
    assert "actions/setup-python@v6" in ci_workflow


def test_docker_publish_workflow_uses_version_tags():
    workflow = (_repo_root() / ".github" / "workflows" / "docker-publish.yml").read_text(encoding="utf-8")
    assert 'tags: ["v*"]' in workflow
    assert "type=semver,pattern={{version}}" in workflow
    assert "type=raw,value=latest" in workflow
    assert 'FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"' in workflow
    assert "actions/checkout@v6" in workflow
    assert "docker/setup-qemu-action@v4" in workflow
    assert "docker/setup-buildx-action@v4" in workflow
    assert "docker/login-action@v4" in workflow
    assert "docker/metadata-action@v6" in workflow
    assert "docker/build-push-action@v7" in workflow
    assert "platforms: linux/amd64,linux/arm64" in workflow


def test_dashboard_module_split_assets_exist():
    repo = _repo_root()
    web_ui = repo / "gateway" / "gateway" / "web_ui.py"
    web_ui_content = repo / "gateway" / "gateway" / "web_ui_content.py"
    dashboard_arch = repo / "docs" / "dashboard-architecture.md"

    assert web_ui_content.exists()
    assert dashboard_arch.exists()
    text = web_ui.read_text(encoding="utf-8")
    assert "from gateway.web_ui_content import DASHBOARD_HTML, _T, render_docs" in text


def test_tools_service_modules_exist():
    repo = _repo_root()
    tools_dir = repo / "gateway" / "gateway" / "tools"
    assert (tools_dir / "query_service.py").exists()
    assert (tools_dir / "schema_service.py").exists()
    assert (tools_dir / "health_service.py").exists()


def test_setup_script_is_codex_first():
    text = (_repo_root() / "setup.sh").read_text(encoding="utf-8")
    assert "codex mcp add" in text
    assert 'docker rm -f "${CONTAINER}"' in text
    assert "--remove-orphans" in text
    assert (_FORBIDDEN_BRAND + " mcp") not in text.lower()


def test_readme_is_russian_and_matches_neutral_install_flow():
    text = (_repo_root() / "README.md").read_text(encoding="utf-8")
    assert "## Требования" in text
    assert "## Быстрый старт" in text
    assert "## Подключение MCP-клиента" in text
    assert "## Подключение через Codex" in text
    assert "## Удаление и чистый повторный подъём" in text
    assert ".\\install.cmd" in text
    assert "ExecutionPolicy Bypass" in text
    assert "POST http://localhost:8090/mcp" in text
    assert "PG_MCP_STATE_FILE" in text
    assert "PG_MCP_RATE_LIMIT_ENABLED" in text
    assert "429" in text
    assert "connection_string" in text
    assert "gateway/requirements-dev.txt" in text
    assert "--cov-fail-under=100" in text
    assert "Table of Contents (English)" not in text
    assert "Connect to " + _FORBIDDEN_BRAND.title() + " Code" not in text


def test_codex_and_agents_guides_match_roles():
    repo = _repo_root()
    codex = (repo / "CODEX.md").read_text(encoding="utf-8")
    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")

    assert "Безопасное удаление" in codex
    assert "codex mcp remove postgres-universal" in codex
    assert ".\\install.cmd" in codex
    assert "PG_MCP_RATE_LIMIT_ENABLED" in codex
    assert "нейтральная" in agents.lower()
    assert "codex mcp add" not in agents
    assert "POST http://localhost:8090/mcp" in agents
    assert "install.cmd" in agents


def test_compose_and_ci_are_aligned_with_bridge_networking():
    repo = _repo_root()
    compose = (repo / "docker-compose.yml").read_text(encoding="utf-8")
    ci = (repo / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "network_mode: host" not in compose
    assert "network: host" not in compose
    assert "ports:" in compose
    assert "install.cmd" in ci
    assert "install.ps1" in ci
    assert "uninstall.cmd" in ci
    assert "uninstall.ps1" in ci


def test_windows_wrappers_use_execution_policy_bypass():
    repo = _repo_root()
    install_cmd = (repo / "install.cmd").read_text(encoding="utf-8")
    uninstall_cmd = (repo / "uninstall.cmd").read_text(encoding="utf-8")

    assert "ExecutionPolicy Bypass" in install_cmd
    assert "install.ps1" in install_cmd
    assert "ExecutionPolicy Bypass" in uninstall_cmd
    assert "uninstall.ps1" in uninstall_cmd


def test_dev_requirements_cover_async_tests():
    text = (_repo_root() / "gateway" / "requirements-dev.txt").read_text(encoding="utf-8")

    assert "-r requirements.txt" in text
    assert "pytest" in text
    assert "pytest-asyncio" in text
    assert "pytest-cov" in text


def test_tracked_files_do_not_reference_removed_client_brand():
    repo = _repo_root()
    files = subprocess.run(
        ["git", "ls-files"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    # The client-specific root guide may retain brand-specific notes.
    # README.md and docs/* are treated as user-facing documentation.
    allow_list = {
        _ROOT_GUIDE, "README.md",
        "gateway/tests/test_ci_assets.py",
    }

    offenders = []
    for rel in files:
        if rel in allow_list:
            continue
        path = repo / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if rel.startswith("docs/"):
            continue
        if _FORBIDDEN_BRAND in text.lower():
            offenders.append(rel)

    assert offenders == []
