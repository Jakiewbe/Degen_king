"""Static import-boundary test for the agent package.

Ensures degenking.agent does not import any module that grants access to
exchange connectivity, execution, order placement, or config mutation.

The agent may only import:
  - degenking.reporting
  - degenking.audit
"""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_AGENT_IMPORTS = [
    "degenking.market_data",
    "degenking.strategy",
    "degenking.risk",
    "degenking.orders",
    "degenking.paper",
    "degenking.reconciliation",
    "degenking.positions",
    "degenking.config",
    "degenking.persistence",
]

ALLOWED_AGENT_IMPORTS = [
    "degenking.reporting",
    "degenking.audit",
]


def _is_forbidden(module: str) -> bool:
    """Check if a module name or prefix matches a forbidden import."""
    for forbidden in FORBIDDEN_AGENT_IMPORTS:
        if module == forbidden or module.startswith(forbidden + "."):
            return True
    return False


def test_agent_package_does_not_import_forbidden_modules() -> None:
    """Walk agent source AST and assert no forbidden imports exist."""
    agent_dir = Path(__file__).parents[2] / "src" / "degenking" / "agent"

    if not agent_dir.exists():
        # Phase 0: agent directory may not exist yet; skip gracefully.
        return

    for path in agent_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            else:
                continue

            for module in imported:
                assert not _is_forbidden(module), (
                    f"{path.name} imports forbidden module: {module}"
                )


def test_agent_allowed_imports_exist() -> None:
    """Verify allowed import target packages exist in the project."""
    import importlib.util

    for module_name in ALLOWED_AGENT_IMPORTS:
        spec = importlib.util.find_spec(module_name)
        assert spec is not None, f"Allowed import target not found: {module_name}"
