"""Smoke test: the installed command, launched as a real subprocess over stdio, as an MCP host does.

Source: MCP SDK "Client transports", StdioServerParameters example (research plan Topic 1).
Skipped if the package isn't installed as a command (for example, running from a bare checkout).
"""
import shutil
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters

from code_recycle import index, settings

COMMAND = shutil.which("code-recycle") or shutil.which("code-recycle", path=str(Path(sys.executable).parent))


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.skipif(COMMAND is None, reason="code-recycle is not installed as a command")
@pytest.mark.anyio
async def test_installed_command_serves_mcp_over_stdio(make_tree, write_settings):
    make_tree({"tools/dates.py": 'def parse_iso_date(text):\n    """Turn 2026-11-05 into a date."""\n    pass\n'})
    p = write_settings('[index]\nfolders = ["."]\nindex_path = "idx.db"\n')
    index.build(settings.load(p), progress=lambda m: None)
    server = StdioServerParameters(command=COMMAND, args=["serve"], env={"CODE_RECYCLE_SETTINGS": str(p)})
    async with Client(server) as client:  # spawns the process; leaving the block shuts it down
        tools = [t.name for t in (await client.list_tools()).tools]
        result = await client.call_tool("search_own_work", {"query": "parse an iso date"})
    assert tools == ["search_own_work"]
    assert "parse_iso_date (function)" in result.content[0].text
