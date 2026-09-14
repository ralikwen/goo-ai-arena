"""Allowlisted clean export: never include research, credentials, media or trial history."""

from pathlib import Path

from .core import render_catalog


def export_files(root):
    root = Path(root)
    files = {}
    for package in ("arena_contract", "arena_platform"):
        for path in (root / package).rglob("*"):
            relative = path.relative_to(root / package)
            if any(part in {"__pycache__", "repository"} for part in relative.parts):
                continue
            if path.is_file() and path.suffix in {".py", ".json", ".md", ".cjs"}:
                if path.is_symlink():
                    raise ValueError("Export source may not be a symlink")
                files[path.relative_to(root).as_posix()] = path.read_bytes()
    template = root / "arena_platform" / "repository"
    if template.is_dir():
        for path in template.rglob("*"):
            if path.is_file():
                if path.is_symlink():
                    raise ValueError("Export source may not be a symlink")
                files[path.relative_to(template).as_posix()] = path.read_bytes()
    else:
        # The exported repository already has the template files at its root.
        for relative in ("README.md", "discovery.json", ".gitignore", "LICENSE.md", "LICENSE-MIT",
                         ".github/CODEOWNERS", ".github/workflows/admission.yml",
                         ".github/workflows/platform-tests.yml",
                         "docs/participate.md", "docs/platform-security.md", "docs/trial-results.md"):
            path = root / relative
            if relative == "docs/trial-results.md" and not path.exists():
                continue  # Optional retrospective; absent before the first completed trial.
            if path.is_symlink():
                raise ValueError("Export source may not be a symlink")
            files[relative] = path.read_bytes()
    semantic = "docs/community-replay-spec-v0.2.md"
    files[semantic] = (root / semantic).read_bytes()
    files.update(render_catalog({}, {}))
    return files
