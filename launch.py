"""Console entry point for MCP clients that cannot set a working directory.

The server takes its lab from --lab, so this file stays deliberately small: it
only has to make `python launch.py --lab <dir>` work from any working directory.
"""

import sys

from vroid_mcp.server import main

if __name__ == '__main__':
    sys.exit(main())
