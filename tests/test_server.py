"""The MCP tool, tested in memory with the SDK's own Client (MCP SDK docs, "Testing")."""
import pytest
from mcp import Client

from code_recycle import index, settings
from code_recycle.server import build_server


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def server(make_tree, write_settings):
    make_tree({
        "lib/retry.py": 'def retry_with_backoff(call, tries=3):\n    """Retry a call, waiting longer each time."""\n    pass\n',
        "protected/alerts.py": "def send_alert(text):\n    pass\n",
    })
    p = write_settings('[index]\nfolders = ["."]\nindex_path = "idx.db"\n[rules]\nno_suggest_into = ["protected/"]\n')
    index.build(settings.load(p), progress=lambda m: None)
    return build_server(p), p.parent


@pytest.mark.anyio
async def test_the_tool_is_listed_with_a_description(server):
    mcp, _ = server
    async with Client(mcp, raise_exceptions=True) as client:
        tools = (await client.list_tools()).tools
    assert [t.name for t in tools] == ["search_own_work"]
    assert "before searching the web" in tools[0].description


@pytest.mark.anyio
async def test_the_tool_returns_file_and_lines(server):
    mcp, root = server
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("search_own_work", {"query": "retry with backoff"})
    text = result.content[0].text
    assert "retry_with_backoff (function)" in text and "lib/retry.py:1-3" in text


@pytest.mark.anyio
async def test_reuse_rules_apply_through_the_tool(server):
    mcp, root = server
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("search_own_work", {"query": "retry with backoff", "from_path": str(root / "protected" / "x.py")})
    text = result.content[0].text
    assert "lib/retry.py" not in text and "matches exist outside this folder" in text


@pytest.mark.anyio
async def test_a_bad_limit_is_a_clean_tool_error(server):
    mcp, _ = server
    async with Client(mcp) as client:
        result = await client.call_tool("search_own_work", {"query": "x", "limit": 99})
    assert result.is_error and "between 1 and 20" in result.content[0].text


@pytest.mark.anyio
async def test_rules_apply_when_from_path_is_left_out(server, monkeypatch):
    mcp, root = server
    monkeypatch.chdir(root / "protected")  # the host started the server inside the protected folder
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("search_own_work", {"query": "retry with backoff"})
    text = result.content[0].text
    assert "lib/retry.py" not in text and "matches exist outside this folder" in text
