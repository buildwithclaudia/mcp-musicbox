"""Main entry point for the MCP server."""

from .server import McpServer


def main() -> None:
    """Run the MCP server."""
    server = McpServer()
    server.run()


if __name__ == "__main__":
    main()
