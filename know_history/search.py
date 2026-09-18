"""Search context in tpuff."""
from .tpuff import TurboPufferIndex
import argparse
from sys import argv


def search(query: str):
    """Index the latest docs into TurboPuffer."""
    indexer = TurboPufferIndex()
    results = indexer.context_mentioning_terms(phrase=query, top_k=5)
    print(results)


def main():
    parser = argparse.ArgumentParser(description="Index latest docs into TurboPuffer.")
    parser.add_argument("query", nargs="?", help="Query string to search for context.")
    args = parser.parse_args(argv[1:])
    search(query=args.query)


if __name__ == "__main__":
    main()
