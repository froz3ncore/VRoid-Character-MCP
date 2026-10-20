"""Run installation diagnostics without importing or launching the MCP server."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vroid_mcp.diagnostics import main

if __name__ == '__main__':
    raise SystemExit(main())
