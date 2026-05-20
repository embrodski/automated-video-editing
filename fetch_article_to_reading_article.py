#!/usr/bin/env python3
"""
Fetch an article from a URL and write a canonical "reading article" text file:
one sentence-like chunk per line, blank lines between paragraphs.

This is intended for the Inkhaven-Reading-Autocut workflow.

Heuristics:
- Prefer JSON-LD (type=Article/NewsArticle) and use `headline`, optional
  `description`/`alternativeHeadline`, and `articleBody` when present.
- Fallback: extract text from within the <article> tag (best-effort).
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.request import Request, urlopen


SENTENCE_TERMINALS = ".?!:;"
ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "ave", "mt",
    "etc", "vs", "eg", "ie", "fig", "no", "vol", "ch",
})


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fetch article URL to reading_article.txt",
    )
    p.add_argument("--url", required=True, help="Article URL (e.g. Substack post)")
    out = p.add_mutually_exclusive_group(required=True)
    out.add_argument(
        "--output",
        help="Output text file path (use this for a custom filename)",
    )
    out.add_argument(
        "--output-dir",
        dest="output_dir",
        help='Output folder; writes "reading_article.txt" inside it',
    )
    p.add_argument("--include-title", action="store_true", default=True,
                  help="Include title/subtitle at the top (default: true)")
    p.add_argument("--no-include-title", dest="include_title", action="store_false",
                  help="Do not include title/subtitle")
    return p.parse_args()


def _fetch_html(url: str) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0 Safari/537.36"
        },
    )
    with urlopen(req, timeout=30) as resp:
        raw = resp.read()
        # Try declared charset, else utf-8 fallback
        charset = getattr(resp.headers, "get_content_charset", lambda: None)() or "utf-8"
        return raw.decode(charset, errors="replace")


def _iter_jsonld_blocks(page_html: str) -> Iterable[str]:
    # Non-greedy to avoid spanning multiple scripts.
    for m in re.finditer(
        r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        yield html.unescape(m.group(1).strip())


def _load_json_maybe(s: str) -> Optional[Any]:
    try:
        return json.loads(s)
    except Exception:
        return None


def _as_list(x: Any) -> list:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def _is_article_type(t: Any) -> bool:
    vals = _as_list(t)
    for v in vals:
        if not isinstance(v, str):
            continue
        if v.lower() in ("article", "newsarticle", "blogposting"):
            return True
    return False


@dataclass
class ArticleExtract:
    title: str = ""
    subtitle: str = ""
    author: str = ""
    body: str = ""


def extract_from_jsonld(page_html: str) -> Optional[ArticleExtract]:
    best: Optional[ArticleExtract] = None
    for block in _iter_jsonld_blocks(page_html):
        data = _load_json_maybe(block)
        if data is None:
            continue
        for obj in _as_list(data):
            if not isinstance(obj, dict):
                continue
            if not _is_article_type(obj.get("@type")):
                continue
            body = obj.get("articleBody") or ""
            title = obj.get("headline") or ""
            subtitle = obj.get("alternativeHeadline") or obj.get("description") or ""
            author = ""
            auth = obj.get("author")
            # JSON-LD author can be dict, list, or string.
            for a in _as_list(auth):
                if isinstance(a, dict) and isinstance(a.get("name"), str):
                    author = a["name"].strip()
                    break
                if isinstance(a, str) and a.strip():
                    author = a.strip()
                    break
            if isinstance(body, str) and body.strip():
                cand = ArticleExtract(
                    title=str(title).strip(),
                    subtitle=str(subtitle).strip(),
                    author=author,
                    body=str(body),
                )
                # Prefer the longest body
                if best is None or len(cand.body) > len(best.body):
                    best = cand
    return best


def _strip_tags(fragment_html: str) -> str:
    # Drop scripts/styles
    fragment_html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", fragment_html, flags=re.I | re.S)
    # Replace <br> and block closings with newlines
    fragment_html = re.sub(r"<br\s*/?>", "\n", fragment_html, flags=re.I)
    fragment_html = re.sub(r"</(p|div|li|blockquote|h1|h2|h3|h4|h5|h6)>", "\n", fragment_html, flags=re.I)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", fragment_html)
    text = html.unescape(text)
    return text


def extract_from_article_tag(page_html: str) -> Optional[ArticleExtract]:
    """First <article>...</article> block (may be short on sites that use many
    small <article> cards for related posts)."""
    m = re.search(r"<article\b[^>]*>(.*?)</article>", page_html, flags=re.I | re.S)
    if not m:
        return None
    text = _strip_tags(m.group(1))
    # Normalize blank lines
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return None
    return ArticleExtract(body=text)


def extract_from_main_tag(page_html: str) -> Optional[ArticleExtract]:
    """`<main>` often holds the primary article on modern layouts (e.g. Bellingcat),
    while `<article>` is used for small related-post cards."""
    m = re.search(r"<main\b[^>]*>(.*?)</main>", page_html, flags=re.I | re.S)
    if not m:
        return None
    text = _strip_tags(m.group(1))
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return None
    return ArticleExtract(body=text)


def extract_from_longest_article_tag(page_html: str) -> Optional[ArticleExtract]:
    """Pick the longest `<article>...</article>` body (skips tiny related-post cards)."""
    best: Optional[ArticleExtract] = None
    best_len = 0
    for m in re.finditer(r"<article\b[^>]*>(.*?)</article>", page_html, flags=re.I | re.S):
        raw = m.group(1)
        if re.search(r'class=["\'][^"\']*grid_item', raw, flags=re.I):
            continue
        text = _strip_tags(raw)
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if len(text) > best_len:
            best_len = len(text)
            best = ArticleExtract(body=text) if text else None
    return best


_CONTENT_CONTAINER_RE = re.compile(
    r"(entry-content|post-content|article-content|wp-block-post-content|post-body|entry__content)",
    re.I,
)
_TITLE_CONTAINER_RE = re.compile(r"(entry-title|post-title|article-title|wp-block-post-title)", re.I)


class _CommonContentHTMLParser(HTMLParser):
    """Best-effort fallback extractor for common blog/article templates."""

    _BLOCK_TAGS = {"p", "div", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._capture_stack: list[bool] = []
        self._capturing = False
        self._buffer: list[str] = []
        self.blocks: list[str] = []
        self.title_text = ""
        self._title_capture_depth = 0
        self._title_buffer: list[str] = []
        self._document_title = False
        self._document_title_buffer: list[str] = []

    @staticmethod
    def _attrs_text(attrs: list[tuple[str, Optional[str]]]) -> str:
        parts: list[str] = []
        for key, value in attrs:
            if key in {"class", "id"} and value:
                parts.append(value)
        return " ".join(parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return

        attrs_text = self._attrs_text(attrs)
        matched_capture = bool(_CONTENT_CONTAINER_RE.search(attrs_text))
        self._capture_stack.append(matched_capture)
        if matched_capture:
            self._capturing = True

        matched_title = tag == "h1" and bool(_TITLE_CONTAINER_RE.search(attrs_text))
        if matched_title:
            self._title_capture_depth += 1

        if tag == "title":
            self._document_title = True

        if self._capturing and tag == "br":
            self._buffer.append("\n")
        if self._capturing and tag in self._BLOCK_TAGS:
            self._buffer.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return

        if tag == "title":
            self._document_title = False

        if self._capturing and tag in self._BLOCK_TAGS:
            self._buffer.append("\n")

        if self._title_capture_depth and tag == "h1":
            self._title_capture_depth -= 1
            if not self.title_text:
                self.title_text = normalize_ws("".join(self._title_buffer))
            self._title_buffer.clear()

        if self._capture_stack:
            matched_capture = self._capture_stack.pop()
            if matched_capture:
                block = normalize_ws("".join(self._buffer))
                if block:
                    self.blocks.append(block)
                self._buffer.clear()
                self._capturing = any(self._capture_stack)

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not data:
            return
        if self._capturing:
            self._buffer.append(data)
        if self._title_capture_depth:
            self._title_buffer.append(data)
        if self._document_title:
            self._document_title_buffer.append(data)

    @property
    def document_title(self) -> str:
        return normalize_ws("".join(self._document_title_buffer))


def extract_from_common_content_container(page_html: str) -> Optional[ArticleExtract]:
    parser = _CommonContentHTMLParser()
    parser.feed(page_html)
    if not parser.blocks:
        return None
    body = max(parser.blocks, key=len)
    title = clean_title_text(parser.title_text or parser.document_title)
    return ArticleExtract(title=title, body=body)


def format_title_line(extracted: ArticleExtract) -> str:
    """Create a single canonical title line that aligns with how readers speak it.

    Important: do NOT split this line at ':'; title alignment is sensitive.
    """
    title = clean_title_text(extracted.title).strip()
    subtitle = normalize_ws(extracted.subtitle).strip()
    author = normalize_ws(extracted.author).strip()

    if title and subtitle:
        low_t = title.lower()
        low_s = subtitle.lower()
        if low_s not in low_t:
            # Common spoken format: "Title: Subtitle"
            title = f"{title}: {subtitle}"
    if author:
        low = title.lower()
        # Avoid duplicating "by ..." if already present.
        if " by " not in low:
            title = f"{title} by {author}" if title else f"by {author}"
    return normalize_ws(title)


def normalize_ws(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    # Keep paragraph structure; collapse excessive blank lines
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def clean_title_text(title: str) -> str:
    """Drop common site-name suffixes from document titles."""
    title = normalize_ws(title)
    for sep in (" | ", " - ", " — ", " – "):
        if sep in title:
            left, _right = title.split(sep, 1)
            if left.strip():
                return left.strip()
    return title


def split_article_line(line: str) -> list[str]:
    line = line.strip()
    if not line:
        return []
    words = line.split()
    sentences: list[str] = []
    current: list[str] = []
    for w in words:
        current.append(w)
        if not w:
            continue
        # Treat sentence terminals normally (".", "?", "!", etc), and also
        # footnote-style terminals like "ship.1" or "ship.1)" which are common
        # in blog posts.
        is_terminal = False
        last = w[-1]
        if last in SENTENCE_TERMINALS:
            is_terminal = True
        else:
            # e.g. "ship.1", "ship.12)", "ship.3”"
            if re.search(r"[.?!][0-9]+[)\]\"'”’`]*$", w):
                is_terminal = True
        if not is_terminal:
            continue
        if w.endswith("..."):
            continue

        stripped = re.sub(r"[0-9]+[)\]\"'”’`]*$", "", w)
        stripped = stripped.rstrip(SENTENCE_TERMINALS + ",\"'`)")
        stripped_low = stripped.lower().rstrip(".")
        if stripped_low in ABBREVIATIONS:
            continue
        sentences.append(" ".join(current))
        current = []
    if current:
        sentences.append(" ".join(current))
    return sentences


def chunk_to_lines(text: str) -> list[str]:
    text = normalize_ws(text)
    if not text:
        return []

    out: list[str] = []
    paragraphs = text.split("\n\n")
    for pi, para in enumerate(paragraphs):
        para = para.strip("\n ").strip()
        if not para:
            continue
        # Preserve hard line breaks inside paragraphs (poetry/lists often come this way)
        for raw_line in para.split("\n"):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            out.extend(split_article_line(raw_line))
        # Blank line between paragraphs
        out.append("")
    # Remove trailing blank lines
    while out and out[-1] == "":
        out.pop()
    return out


_JUNK_EXACT = {
    "share",
    "subscribe",
    "sign in",
    "subscribesign in",
}


_MONTH_RE = re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\b", re.I)
_DATE_RE = re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\s+\d{1,2},\s+\d{4}$", re.I)
_TRAILING_STOP_RE = re.compile(
    r"^(share this:?|like loading|related|comments are closed\.?|join \d+ other subscribers|sign me up|already have a wordpress\.com account|create a free website or blog at wordpress\.com|design a site like this with wordpress\.com|get started)$",
    re.I,
)
_COMMENTS_RE = re.compile(r"^\d+\s+thoughts on\b", re.I)

def is_junk_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    low = s.lower()
    if low in _JUNK_EXACT:
        return True
    if re.fullmatch(r"\d+", s):
        return True
    if _DATE_RE.fullmatch(s):
        return True
    # Substack sometimes emits month-name prefix lines in headers
    if _MONTH_RE.match(s) and len(s.split()) <= 4 and "," in s:
        return True
    return False


def strip_leading_junk_body_lines(lines: list[str], *, max_scan: int = 20) -> list[str]:
    """Remove leading header/chrome lines from JSON-LD bodies (author/date/counters)."""
    out = list(lines)
    scanned = 0
    while out and scanned < max_scan:
        if out[0] == "":
            out.pop(0)
            scanned += 1
            continue
        if is_junk_line(out[0]):
            out.pop(0)
            scanned += 1
            continue
        # Heuristic: probable author/byline (e.g. "First Last") near the top.
        # Avoid removing legitimate content by only applying very early.
        if scanned < 6:
            s = out[0].strip()
            if re.fullmatch(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", s) and "," not in s and "." not in s:
                out.pop(0)
                scanned += 1
                continue
        break
    return out


def strip_trailing_junk_body_lines(lines: list[str]) -> list[str]:
    """Trim known site chrome / comments blocks that appear after article content."""
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        if _TRAILING_STOP_RE.fullmatch(s) or _COMMENTS_RE.match(s):
            trimmed = lines[:i]
            while trimmed and not trimmed[-1].strip():
                trimmed.pop()
            return trimmed
    return lines


_LESSWRONG_POST_RE = re.compile(
    r"https?://(?:www\.)?lesswrong\.com/posts/[^/]+/([^/?#]+)",
    re.I,
)


def _strip_lesswrong_leading_star_metadata(md: str) -> str:
    """Drop LessWrong /api/post header lines like ``*   By [...]`` before body prose."""
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if re.match(r"^\*\s{3,}", line):
            i += 1
            continue
        break
    return "\n".join(lines[i:]).lstrip("\n")


def _strip_markdownish_lesswrong(md: str) -> str:
    """Best-effort plain text from LessWrong /api/post markdown export."""
    s = md
    s = re.sub(r"(?m)^\[\^[^\]]+\]:.*$", "", s)
    s = re.sub(r"(?m)^>\s?", "", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"\[\^[^\]]+\]", "", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"(?<!\*)\*(?!\*)([^*]+)(?<!\*)\*(?!\*)", r"\1", s)
    s = re.sub(r"^\s*\*\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^#+\s+", "", s, flags=re.MULTILINE)
    return normalize_ws(s)


def extract_lesswrong_post(url: str) -> Optional[ArticleExtract]:
    """LessWrong post pages are client-rendered; use /api/post/<slug> markdown."""
    m = _LESSWRONG_POST_RE.search(url)
    if not m:
        return None
    slug = m.group(1)
    api_url = f"https://www.lesswrong.com/api/post/{slug}"
    req = Request(
        api_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0 Safari/537.36"
        },
    )
    with urlopen(req, timeout=30) as resp:
        raw = resp.read()
        charset = getattr(resp.headers, "get_content_charset", lambda: None)() or "utf-8"
        md = raw.decode(charset, errors="replace")

    for marker in ("## Top Comments", "Top Comments Index", "### Comment by"):
        cut = md.find(marker)
        if cut != -1:
            md = md[:cut]
            break

    title = ""
    body_md = md
    for line in md.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            rest_i = md.find("\n", md.index(line)) + 1
            body_md = md[rest_i:]
            break
    body_md = _strip_lesswrong_leading_star_metadata(body_md)
    body = _strip_markdownish_lesswrong(body_md)
    if not body.strip():
        return None
    return ArticleExtract(title=title, body=body)


def _pick_best_extract(page_html: str) -> Optional[ArticleExtract]:
    """Choose the richest body among JSON-LD, <main>, <article>, and common containers."""
    candidates: list[ArticleExtract] = []
    for fn in (
        extract_from_jsonld,
        extract_from_main_tag,
        extract_from_longest_article_tag,
        extract_from_article_tag,
        extract_from_common_content_container,
    ):
        cand = fn(page_html)
        if cand is None:
            continue
        body = (cand.body or "").strip()
        if not body:
            continue
        candidates.append(
            ArticleExtract(
                title=cand.title or "",
                subtitle=cand.subtitle or "",
                author=getattr(cand, "author", "") or "",
                body=body,
            )
        )
    if not candidates:
        return None

    def score(c: ArticleExtract) -> int:
        return len(c.body)

    return max(candidates, key=score)


def main() -> int:
    args = parse_args()
    page = _fetch_html(args.url)

    extracted = _pick_best_extract(page)
    if extracted is None:
        extracted = extract_lesswrong_post(args.url)
    if extracted is None:
        print("Error: could not extract article text from URL.", file=sys.stderr)
        return 2

    lines: list[str] = []
    if args.include_title:
        title_line = format_title_line(extracted)
        if title_line:
            # Keep title as a single line (do not sentence-split it).
            lines.append(title_line)
            lines.append("")

    body = extracted.body
    for needle in ("\nShare this article", "\nRelated articles"):
        cut = body.find(needle)
        if cut != -1:
            body = body[:cut]
    body = body.strip()
    extracted = ArticleExtract(
        title=extracted.title,
        subtitle=extracted.subtitle,
        author=extracted.author,
        body=body,
    )

    body_lines = chunk_to_lines(extracted.body)
    body_lines = [ln for ln in body_lines if not is_junk_line(ln)]
    body_lines = strip_leading_junk_body_lines(body_lines)
    body_lines = strip_trailing_junk_body_lines(body_lines)
    lines.extend(body_lines)

    # Ensure at least something useful.
    # Collapse multiple blank lines to single blanks.
    cleaned: list[str] = []
    prev_blank = False
    for ln in lines:
        s = ln.rstrip()
        is_blank = not s.strip()
        if is_blank and prev_blank:
            continue
        cleaned.append(s)
        prev_blank = is_blank

    # Final pass: remove a likely author/byline line near the top (common in Substack JSON-LD).
    # Only applies very early to reduce false positives.
    for i in range(min(10, len(cleaned))):
        s = cleaned[i].strip()
        if not s:
            continue
        if re.fullmatch(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", s) and "," not in s and "." not in s:
            # Remove if surrounded by blank(s) or followed by a blank.
            before_blank = (i == 0) or (not cleaned[i - 1].strip())
            after_blank = (i + 1 < len(cleaned)) and (not cleaned[i + 1].strip())
            if before_blank or after_blank:
                cleaned.pop(i)
                # Also remove an extra blank line left behind.
                if i < len(cleaned) and not cleaned[i].strip():
                    cleaned.pop(i)
                break
    if not any(ln.strip() for ln in cleaned):
        print("Error: extracted text was empty after processing.", file=sys.stderr)
        return 3

    if args.output_dir is not None:
        out_path = Path(args.output_dir) / "reading_article.txt"
    else:
        out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(cleaned) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote reading article text to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

