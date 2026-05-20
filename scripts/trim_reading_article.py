from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Trim reading_article.txt at a stop sentence.")
    p.add_argument("--article", required=True, help="Path to reading_article.txt")
    p.add_argument(
        "--stop",
        required=True,
        help="Stop text to trim at (the output ends after the first occurrence of this string).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    article_path = Path(args.article)
    s = article_path.read_text(encoding="utf-8")

    i = s.find(args.stop)
    if i < 0:
        raise SystemExit(f"Stop text not found in article: {args.stop!r}")

    end = i + len(args.stop)
    out = s[:end].rstrip() + "\n"
    article_path.write_text(out, encoding="utf-8")
    print(f"Trimmed {article_path} chars {len(s)} -> {len(out)}")


if __name__ == "__main__":
    main()

