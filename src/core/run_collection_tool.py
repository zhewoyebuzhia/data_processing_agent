"""Stable entry point used by Windows Task Scheduler for collection tools."""
import os
import runpy
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: run_collection_tool.py <tool path relative to project root>")

    tool_path = (PROJECT_ROOT / sys.argv[1]).resolve()
    try:
        tool_path.relative_to(PROJECT_ROOT / "tools")
    except ValueError as exc:
        raise SystemExit("Only tools/ collection scripts can be scheduled") from exc
    if not tool_path.is_file():
        raise SystemExit(f"Collection tool not found: {tool_path}")

    os.chdir(PROJECT_ROOT)
    runpy.run_path(str(tool_path), run_name="__main__")


if __name__ == "__main__":
    main()
