#!/usr/bin/env python3
"""Convert an old-style SPHERE index.html (a numbered list of links) into the
new catalog layout that uses css/catalog.css and js/catalog.js.

Old entries look like:
    <li><a href="docs/sqli/index.html">Exploits: SQL Injection</a></li>

Each becomes a catalog row: the text before the first ": " is the topic and the
rest is the exercise name. Tags and descriptions are taken from --previous (a
page already in the new layout, usually the current index.html) when that page
has an entry with the same link. Entries it does not have get no tags, and a
description taken from the first sentence of the exercise's Overview section.
The script lists those entries so you can review them.

Usage (from the site folder):
    python3 scripts/convert_index.py old_index.html --previous index.html -o index.html
    python3 scripts/convert_index.py old_index.html               # print to stdout

Only the Python 3 standard library is needed.
"""

import argparse
import html
import os
import re
import sys
from html.parser import HTMLParser

DEFAULT_TITLE = "SPHERE Shared Education Materials"
DEFAULT_INTRO = (
    'This website offers a collection of materials for teaching cybersecurity. '
    'If you are interested in contributing please make a pull request against '
    '<a href="https://github.com/sphere-edu/sphere-edu">this repository</a>.'
)
MAX_DESCRIPTION = 220


class OldIndexParser(HTMLParser):
    """Collects the page title and every <li><a href=...>text</a></li>."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.entries = []  # (href, text)
        self._in_title = False
        self._in_li = False
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        elif tag == "li":
            self._in_li = True
        elif tag == "a" and self._in_li and self._href is None:
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "a" and self._href is not None:
            text = " ".join("".join(self._text).split())
            if self._href and text:
                self.entries.append((self._href, text))
            self._href = None
        elif tag == "li":
            self._in_li = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._href is not None:
            self._text.append(data)


class NewIndexParser(HTMLParser):
    """Reads tags and descriptions from a page already in the new layout."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.entries = {}  # href -> {"tags": [...], "description": str}
        self._current = None
        self._in_p = False
        self._p = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "li" and "data-tags" in attrs:
            tags = [t.strip().lower() for t in attrs["data-tags"].split(",") if t.strip()]
            self._current = {"tags": tags, "description": "", "href": None}
        elif self._current is not None:
            if tag == "a" and self._current["href"] is None:
                self._current["href"] = attrs.get("href")
            elif tag == "p":
                self._in_p = True
                self._p = []

    def handle_endtag(self, tag):
        if self._current is None:
            return
        if tag == "p" and self._in_p:
            self._current["description"] = " ".join("".join(self._p).split())
            self._in_p = False
        elif tag == "li" and not self._in_p:
            if self._current["href"]:
                self.entries[self._current["href"]] = self._current
            self._current = None

    def handle_data(self, data):
        if self._in_p:
            self._p.append(data)


def extract_intro(source):
    """Returns the raw HTML between the opening of the page body and the list."""
    m = re.search(r'<div id="page"[^>]*>(.*?)<[ou]l', source, flags=re.S | re.I)
    if not m:
        m = re.search(r"<body[^>]*>(.*?)<[ou]l", source, flags=re.S | re.I)
    intro = " ".join(m.group(1).split()) if m else ""
    return intro or DEFAULT_INTRO


def overview_sentence(site_dir, href):
    """First sentence of the Overview section of an exercise page, or ""."""
    path = os.path.join(site_dir, href.split("#")[0].split("?")[0])
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            page = f.read()
    except OSError:
        return ""
    page = re.sub(r"<!--.*?-->", "", page, flags=re.S)
    page = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", page, flags=re.S | re.I)
    m = re.search(r"<h[1-4][^>]*>\s*(?:<a[^>]*>\s*)?Overview.*?</h[1-4]>(.*?)<h[1-4]",
                  page, flags=re.S | re.I)
    if not m:
        return ""
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    text = " ".join(html.unescape(text).split())
    s = re.match(r"(.+?[.!?])(\s|$)", text)
    sentence = s.group(1) if s else text
    if len(sentence) > MAX_DESCRIPTION:
        sentence = sentence[:MAX_DESCRIPTION].rsplit(" ", 1)[0] + "…"
    return sentence


def split_title(text):
    topic, sep, name = text.partition(": ")
    if not sep:
        return "", text
    return topic.strip(), name.strip()


def render_entry(href, text, tags, description):
    topic, name = split_title(text)
    esc = lambda s: html.escape(s, quote=False)
    topic_html = f'<span class="topic">{esc(topic)}</span> ' if topic else ""
    lines = [
        f'        <li data-tags="{html.escape(", ".join(tags))}">',
        f'          <a href="{html.escape(href)}">{topic_html}<span class="name">{esc(name)}</span></a>',
    ]
    if description:
        lines.append(f"          <p>{esc(description)}</p>")
    lines.append("        </li>")
    return "\n".join(lines)


PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="index,nofollow">
  <meta name="description" content="A collection of materials for teaching cybersecurity.">
  <meta name="color-scheme" content="light dark">
  <title>{title}</title>
  <link rel="stylesheet" href="css/catalog.css">
  <script src="js/catalog.js" defer></script>
</head>

<body>
  <header class="masthead">
    <div class="wrap">
      <h1>{title}</h1>
      <p>{intro}</p>
    </div>
  </header>

  <div class="wrap layout">
    <!-- Built from the data-tags below by js/catalog.js. Stays hidden if scripts are off. -->
    <aside class="filters" id="filters" aria-label="Filter by tag" hidden>
      <details id="tag-panel" open>
        <summary>Filter by tag</summary>
        <h2 class="filters-title">Filter by tag</h2>
        <div class="tag-cloud" id="tag-cloud"></div>
      </details>
    </aside>

    <main>
      <div class="toolbar" id="toolbar" hidden>
        <form id="search-form" role="search">
          <label class="visually-hidden" for="search">Search exercises and tags</label>
          <input id="search" type="search" placeholder="Search titles, descriptions and tags" autocomplete="off" spellcheck="false">
        </form>
        <p class="hint" id="hint" hidden></p>
        <div class="active-tags" id="active-tags" hidden></div>
        <p class="result-count" id="result-count" aria-live="polite"></p>
      </div>

      <!--
        To add an exercise, copy one <li> below and keep the list in alphabetical order.
        data-tags is a comma-separated list; the tag filters are built from it automatically.
        Reuse existing tags where you can. "attack" and "defense" are coloured red and blue.
      -->
      <ul class="catalog" id="catalog">
{entries}
      </ul>

      <div class="empty" id="empty" hidden>
        <p>No exercises match this search.</p>
        <button type="button" class="text-button" id="empty-clear">Clear search and tags</button>
      </div>
    </main>
  </div>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("old", help="old-style index.html to convert")
    ap.add_argument("--previous", metavar="FILE",
                    help="page in the new layout to take tags and descriptions from")
    ap.add_argument("-o", "--output", metavar="FILE", help="where to write (default: stdout)")
    ap.add_argument("--site-dir", metavar="DIR",
                    help="site folder that the links are relative to "
                         "(default: the folder holding the old file)")
    ap.add_argument("--sort", action="store_true",
                    help="sort entries alphabetically instead of keeping the old order")
    args = ap.parse_args()

    with open(args.old, encoding="utf-8", errors="replace") as f:
        source = f.read()
    old = OldIndexParser()
    old.feed(source)
    if not old.entries:
        sys.exit(f"No <li><a href=...> entries found in {args.old}")

    previous = {}
    if args.previous:
        with open(args.previous, encoding="utf-8", errors="replace") as f:
            p = NewIndexParser()
            p.feed(f.read())
        previous = p.entries

    site_dir = args.site_dir or os.path.dirname(os.path.abspath(args.old))
    entries = sorted(old.entries, key=lambda e: e[1].lower()) if args.sort else old.entries

    rendered, untagged, no_description = [], [], []
    for href, text in entries:
        prev = previous.get(href)
        tags = prev["tags"] if prev else []
        description = prev["description"] if prev and prev["description"] else ""
        if not description:
            description = overview_sentence(site_dir, href)
            if not description:
                no_description.append(text)
        if not tags:
            untagged.append(text)
        rendered.append(render_entry(href, text, tags, description))

    title = " ".join(old.title.split()) or DEFAULT_TITLE
    page = PAGE.format(title=html.escape(title, quote=False),
                       intro=extract_intro(source),
                       entries="\n".join(rendered))

    # Read everything before writing, so --previous and -o can name the same file.
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(page)
    else:
        sys.stdout.write(page)

    print(f"Converted {len(entries)} entries.", file=sys.stderr)
    if untagged:
        print(f"{len(untagged)} without tags (add them in data-tags):", file=sys.stderr)
        for t in untagged:
            print(f"  - {t}", file=sys.stderr)
    if no_description:
        print(f"{len(no_description)} without a description (no Overview section found):",
              file=sys.stderr)
        for t in no_description:
            print(f"  - {t}", file=sys.stderr)


if __name__ == "__main__":
    main()
