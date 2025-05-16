import anyio
import click
import httpx
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from datetime import datetime
from typing import Optional, List, Dict, Any
import json
from urllib.parse import urlencode


async def fetch_aws_news(
    topic: str,
    news_type: str = "all",
    include_regional_expansions: bool = False,
    limit: int = 40,
    since_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch AWS news articles based on the provided parameters.

    Args:
        topic: The AWS topic/service to search for
        news_type: Type of news to fetch ('all', 'news', 'blogs')
        include_regional_expansions: Whether to include regional expansion news
        limit: Maximum number of results to return
        since_date: Optional ISO 8601 date to filter results

    Returns:
        List of news articles
    """
    base_url = "https://api.aws-news.com/articles"

    # Build query parameters
    params = {
        "page_size": limit,
        "hide_regional_expansions": not include_regional_expansions,
        "search": topic
    }

    # Add article type filter if specified
    if news_type.lower() == "news":
        params["article_type"] = "news"
    elif news_type.lower() == "blogs" or news_type.lower() == "blog":
        params["article_type"] = "blog"

    # Add date filter if provided
    if since_date:
        try:
            # Validate the date format
            datetime.fromisoformat(since_date.replace('Z', '+00:00'))
            params["since"] = since_date
        except ValueError:
            raise ValueError(
                "Invalid date format. Please use ISO 8601 format (e.g., 2025-05-01T00:00:00Z)")

    # Construct the URL with query parameters
    url = f"{base_url}?{urlencode(params)}"

    # Make the request
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()

        # Parse and return the JSON response
        data = response.json()
        return data


@click.command()
@click.option("--port", default=8000, help="Port to listen on for SSE")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    help="Transport type",
)
def main(port: int, transport: str) -> int:
    app = Server("aws-news-mcp-server")

    @app.call_tool()
    async def call_tool(
        name: str, arguments: dict
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        if name != "get_aws_news":
            raise ValueError(f"Unknown tool: {name}")

        # Extract and validate required parameters
        if "topic" not in arguments:
            raise ValueError("Missing required argument 'topic'")

        topic = arguments["topic"]
        news_type = arguments.get("news_type", "all")
        include_regional_expansions = arguments.get(
            "include_regional_expansions", False)
        limit = arguments.get("number_of_results", 40)
        since_date = arguments.get("since_date")

        # Fetch AWS news
        try:
            news_articles = await fetch_aws_news(
                topic=topic,
                news_type=news_type,
                include_regional_expansions=include_regional_expansions,
                limit=limit,
                since_date=since_date
            )

            # Format the response
            result = {
                "topic": topic,
                "news_type": news_type,
                "include_regional_expansions": include_regional_expansions,
                "articles": news_articles
            }

            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error fetching AWS news: {str(e)}")]

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="get_aws_news",
                description="""
Returns a list of AWS news articles with announcements of new products, services, and capabilities for the specified AWS topic/service.

You can filter on news type which is news or blogs. By default, returns both news and blogs.

You can optionally ask for regional expansion news (defaults to false).

Optionally, specify a "since" date in ISO 8601 format by which to filter the results.

Examples:
- To get all news about Amazon S3: use topic="s3"
- To get only blog posts about Amazon EC2: use topic="ec2", news_type="blogs"
- To get news about Lambda since January 2025: use topic="lambda", since_date="2025-01-01T00:00:00Z"
- To get regional expansion news for DynamoDB: use topic="dynamodb", include_regional_expansions=true

Use this tool when:
1. The user asks about recent AWS announcements for a specific service
2. The user wants to know about new features or capabilities in AWS services
3. The user is looking for AWS blog posts about specific topics
4. The user wants to stay updated on AWS service expansions to new regions
                """,
                inputSchema={
                    "type": "object",
                    "required": ["topic"],
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "AWS topic or service to search for (e.g., 's3', 'lambda', 'ec2')",
                        },
                        "news_type": {
                            "type": "string",
                            "enum": ["all", "news", "blogs"],
                            "default": "all",
                            "description": "Type of news to return (all, news, or blogs)",
                        },
                        "include_regional_expansions": {
                            "type": "boolean",
                            "default": False,
                            "description": "Whether to include regional expansion news",
                        },
                        "number_of_results": {
                            "type": "integer",
                            "default": 40,
                            "description": "Maximum number of results to return",
                        },
                        "since_date": {
                            "type": "string",
                            "description": "Optional ISO 8601 date to filter results (e.g., '2025-01-01T00:00:00Z')",
                        },
                    },
                },
            )
        ]

    if transport == "sse":
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.responses import Response
        from starlette.routing import Mount, Route

        sse = SseServerTransport("/messages/")

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await app.run(
                    streams[0], streams[1], app.create_initialization_options()
                )
            return Response()

        starlette_app = Starlette(
            debug=True,
            routes=[
                Route("/sse", endpoint=handle_sse, methods=["GET"]),
                Mount("/messages/", app=sse.handle_post_message),
            ],
        )

        import uvicorn

        uvicorn.run(starlette_app, host="0.0.0.0", port=port)
    else:
        async def arun():
            async with stdio_server() as streams:
                await app.run(
                    streams[0], streams[1], app.create_initialization_options()
                )

        anyio.run(arun)

    return 0


if __name__ == "__main__":
    main()
