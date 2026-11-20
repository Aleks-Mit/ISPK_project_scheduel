rem=r"""
@echo off
python "%~f0"
pause
exit /b
"""
#!/usr/bin/env python3
"""Export all source and config files of the project into one text file."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "project_export.txt"
MAX_FILE_BYTES = 300_000

SKIP_DIRS = {
    ".venv", "venv", "env", ".git", "__pycache__", ".pytest_cache",
    ".mypy_cache", "htmlcov", "instance", "json_backups", "node_modules",
    ".idea", "docs",
}
INCLUDE_EXTENSIONS = {
    ".py", ".html", ".css", ".js", ".sql", ".ini", ".cfg", ".toml",
    ".txt", ".yml", ".yaml", ".md", ".bat", ".sh",
}
INCLUDE_NAMES = {"Dockerfile", ".gitignore", ".gitattributes"}
SKIP_NAMES_PREFIX = ("output", "project_export")


def collect_files():
    files, skipped = [], []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if name.startswith(SKIP_NAMES_PREFIX):
                continue
            if path.suffix.lower() not in INCLUDE_EXTENSIONS and name not in INCLUDE_NAMES:
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                skipped.append(str(path.relative_to(ROOT)))
                continue
            files.append(path)
    return files, skipped


def main():
    files, skipped = collect_files()
    with OUTPUT.open("w", encoding="utf-8") as out:
        out.write("PROJECT EXPORT\n")
        out.write(f"Root: {ROOT}\n\n")
        for path in files:
            rel = path.relative_to(ROOT)
            out.write("-" * 40 + "\n")
            out.write(f"File: {path.name}\n")
            out.write(f"Path: {rel}\n")
            out.write("-" * 40 + "\n")
            out.write(path.read_text(encoding="utf-8", errors="replace"))
            out.write("\n\n")

    print(f"Exported {len(files)} files to {OUTPUT.name}")
    print(f"Size: {OUTPUT.stat().st_size / 1024:.0f} KB")
    if skipped:
        print("Skipped (too large):")
        for s in skipped:
            print("  ", s)


if __name__ == "__main__":
    main()
