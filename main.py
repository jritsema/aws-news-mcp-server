import logging
from log import debug, info, warn, error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


def main():
    logging.info("aws-news-mcp-server")
    info({"project_name": "aws-news-mcp-server"})


if __name__ == "__main__":
    main()
