import argparse
import asyncio
import logging
import uvicorn
from app.config import settings
from app.server import mcp_server, asgi_app

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("mcp-server")


def main():
    parser = argparse.ArgumentParser(description="Kubernetes & Telemetry MCP Server")
    parser.add_argument(
        "--transport",
        choices=["sse", "stdio"],
        default="sse",
        help="MCP transport protocol (sse over HTTP or stdio pipe)"
    )
    parser.add_argument(
        "--host",
        default=settings.mcp_host,
        help="Host address for SSE HTTP server"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.mcp_port,
        help="Port number for SSE HTTP server"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn hot reloading"
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        logger.info("Starting MCP Server with STDIO transport...")
        asyncio.run(mcp_server.run_stdio_async())
    else:
        logger.info(
            "Starting MCP Server on http://%s:%d (SSE Transport: /sse, Info: /info, Health: /healthz)...",
            args.host,
            args.port
        )
        uvicorn.run(
            asgi_app,
            host=args.host,
            port=args.port,
            log_level=settings.log_level.lower()
        )


if __name__ == "__main__":
    main()
