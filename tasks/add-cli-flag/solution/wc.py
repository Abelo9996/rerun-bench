"""Count lines in files. Usage: python wc.py FILE [FILE ...]"""

import argparse
import sys


def count_lines(text):
    return len(text.splitlines())


def count_words(text):
    return len(text.split())


def main(argv=None):
    parser = argparse.ArgumentParser(description="Count lines in files.")
    parser.add_argument("files", nargs="+")
    parser.add_argument("--words", action="store_true", help="count words instead of lines")
    args = parser.parse_args(argv)
    counter = count_words if args.words else count_lines
    total = 0
    for name in args.files:
        with open(name, encoding="utf-8") as fh:
            n = counter(fh.read())
        total += n
        print(f"{n:>8} {name}")
    if len(args.files) > 1:
        print(f"{total:>8} total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
