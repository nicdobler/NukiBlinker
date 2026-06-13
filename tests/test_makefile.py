"""Guards on Makefile targets (infra regression tests)."""

from pathlib import Path

MAKEFILE = Path(__file__).resolve().parents[1] / "Makefile"


def _recipe_lines(text: str, target: str) -> list[str]:
    """Return the tab-indented recipe lines for a Make target."""
    lines = text.splitlines()
    recipe: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].startswith(f"{target}:") and not lines[i].startswith("\t"):
            i += 1
            while i < len(lines) and lines[i].startswith("\t"):
                recipe.append(lines[i].strip())
                i += 1
            break
        i += 1
    return recipe


def test_install_target_does_not_regenerate_lock():
    """#112: `make install` must not run `poetry lock` (it dirties the tree)."""
    recipe = _recipe_lines(MAKEFILE.read_text(encoding="utf-8"), "install")
    assert recipe == ["poetry install"]
    assert not any("poetry lock" in line for line in recipe)


def test_lock_has_its_own_target():
    """Lockfile regeneration lives in a dedicated `make lock` target."""
    recipe = _recipe_lines(MAKEFILE.read_text(encoding="utf-8"), "lock")
    assert any("poetry lock" in line for line in recipe)
