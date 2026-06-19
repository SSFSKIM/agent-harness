"""Shared fixture builder: a minimal repo tree that passes every lint rule."""
import datetime
from pathlib import Path

TODAY = datetime.date.today().isoformat()


def fm(status="draft", owner="harness", last_verified=None,
       type="design-doc", description="A fixture page.", phase=None):
    # KF v2.0: governed content pages need type + description (D11); fixtures emit
    # them by default so a valid page stays green. phase only when a caller needs
    # it (e.g. a product-spec, which D11 requires phased).
    lines = [f"status: {status}", f"last_verified: {last_verified or TODAY}",
             f"owner: {owner}", f"type: {type}", f"description: {description}"]
    if phase:
        lines.append(f"phase: {phase}")
    return "---\n" + "\n".join(lines) + "\n---\n"


def make_repo(tmp: Path) -> Path:
    (tmp / "AGENTS.md").write_text("# map\nSee [beliefs](docs/design-docs/core-beliefs.md)\n")
    dd = tmp / "docs" / "design-docs"
    dd.mkdir(parents=True)
    (dd / "index.md").write_text(fm() + "# Index\n- core-beliefs.md\n")
    (dd / "core-beliefs.md").write_text(fm() + "# Beliefs\n")
    return tmp


def make_plugin(tmp: Path) -> Path:
    """Empty-but-valid plugin tree (for structure/coverage/inventory tests)."""
    plugin = tmp / "plugin"
    for sub in ("scripts", "skills", "agents", "hooks"):
        (plugin / sub).mkdir(parents=True)
    return plugin
