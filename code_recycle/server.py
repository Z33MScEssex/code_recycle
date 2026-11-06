"""The MCP server: one read-only search tool that any MCP client can call.

Source: MCP Python SDK v2 (pinned to 2.3.0), "Connect to a real host" example and README
(research plan Topic 1). mcp.run() with no arguments serves over stdio, which every host speaks.
"""
import os  # the folder the host started the server in

from mcp.server import MCPServer  # the SDK's server class
from mcp.server.mcpserver.exceptions import ToolError  # a clean error the client can show

from . import index, search, settings as settings_mod


def build_server(settings_path):
    """An MCP server bound to one settings file. Settings are read now, so mistakes show at start-up."""
    s = settings_mod.load(settings_path)
    mcp = MCPServer("code_recycle")

    @mcp.tool()
    def search_own_work(query: str, from_path: str = "", limit: int = 5) -> str:
        """Search the user's own code and verified research sources before searching the web.

        Use this first when about to write code, or to look up a library or API: the user may have
        solved it before. Results give the file and line numbers, and for research entries the
        source URL, where on the page, what it taught and the verified code copied from it.

        query: what you need, in plain words, for example "retry an HTTP request with backoff".
        from_path: the file or folder you are working in, so the user's reuse rules can apply.
            If left out, the folder the server was started in is used.
        limit: how many results to return, 1 to 20.
        """
        if not 1 <= limit <= 20:
            raise ToolError("limit must be between 1 and 20")
        try:
            # Hosts start the server in the project's folder, so that's the safe default when the
            # caller doesn't say: a rule like no_suggest_into still applies if from_path is left out
            answer = search.search(s, query, from_path=from_path or os.getcwd(), limit=limit)
        except index.IndexBuildError as e:
            raise ToolError(str(e))
        return search.format_answer(answer)

    return mcp
