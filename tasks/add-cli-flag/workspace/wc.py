"""Count lines in files. Usage: python wc.py FILE [FILE ...]"""

import argparse
import sys


def count_lines(text):
    return len(text.splitlines())


def main(argv=None):
    parser = argparse.ArgumentParser(description="Count lines in files.")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args(argv)
    total = 0
    for name in args.files:
        with open(name, encoding="utf-8") as fh:
            n = count_lines(fh.read())
        total += n
        print(f"{n:>8} {name}")
    if len(args.files) > 1:
        print(f"{total:>8} total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
