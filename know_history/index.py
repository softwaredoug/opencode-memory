"""Index latest into tpuff."""
from .tpuff import TurboPufferIndex
from .parse_telemetry import MIN_UTC_TIMESTAMP, prompt_docs
import argparse
from sys import argv


def index_latest(force: bool = False):
    """Index the latest docs into TurboPuffer."""
    indexer = TurboPufferIndex()
    last_index_time = indexer.last_index_time()
    if force:
        last_index_time = MIN_UTC_TIMESTAMP
        print("Force reindexing all docs into TurboPuffer.")
    else:
        print(f"Indexing telemetry after {last_index_time.isoformat()} into TurboPuffer.")
    docs = prompt_docs(last_index_time=last_index_time)
    indexer.index_docs(docs)


def main():
    parser = argparse.ArgumentParser(description="Index latest docs into TurboPuffer.")
    parser.add_argument("--force", action="store_true", help="Force reindexing all docs.",
                        default=False)
    args = parser.parse_args(argv[1:])
    index_latest(force=args.force)


if __name__ == "__main__":
    main()
