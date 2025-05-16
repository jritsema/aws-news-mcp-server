import sys
from aws_news_server import main as aws_news_server_main


def main():

    # Run the AWS News MCP server
    return aws_news_server_main(standalone_mode=False)


if __name__ == "__main__":
    sys.exit(main())
