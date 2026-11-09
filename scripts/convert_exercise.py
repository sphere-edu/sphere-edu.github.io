#!/usr/bin/env python3
"""Convert an old-style SPHERE exercise page (docs/<name>/index.html, styled by
css/common.css and css/screen.css) into the modern layout that uses
css/exercise.css and js/exercise.js.

The wording of the page is kept exactly. Before writing, the script compares all
the text of the old page with the new one and refuses to write if anything was
lost or changed (use --force to write anyway).

Usage (from the site folder):
    python3 scripts/convert_exercise.py docs/xss/index.html              # print to stdout
    python3 scripts/convert_exercise.py docs/xss/index.html -o new.html  # write elsewhere
    python3 scripts/convert_exercise.py --in-place docs/*/index.html     # convert many

Only the Python 3 standard library is needed.
"""

import argparse
import html
import os
import re
import sys
import textwrap
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# A small, forgiving HTML tree builder. The old pages have unclosed and
# misnested tags, so this follows the browser's most important recovery rules.
# ---------------------------------------------------------------------------

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "source", "track", "wbr"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
CLOSES_P = {"address", "article", "aside", "blockquote", "center", "details",
            "div", "dl", "fieldset", "figcaption", "figure", "footer", "form",
            "header", "hr", "main", "nav", "ol", "p", "pre", "section", "table",
            "ul"} | HEADINGS
SCOPE_LIMIT = {"table", "td", "th", "caption", "html", "body"}
BLOCK = {"html", "head", "body", "header", "main", "article", "section", "aside",
         "nav", "details", "summary", "div", "p", "ul", "ol", "li", "dl", "dt",
         "dd", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption",
         "pre", "figure", "figcaption", "blockquote", "hr", "center", "form"} | HEADINGS


class Node:
    def __init__(self, tag, attrs=None, text=None):
        self.tag = tag            # element name, "#text" or "#comment"
        self.attrs = dict(attrs or {})
        self.text = text
        self.children = []
        self.parent = None
        self.keep_class = False   # True for elements this script created

    def append(self, child):
        child.parent = self
        self.children.append(child)
        return child

    def is_el(self, *tags):
        return self.tag not in ("#text", "#comment") and (not tags or self.tag in tags)

    def classes(self):
        return (self.attrs.get("class") or "").split()

    def iter(self):
        yield self
        for c in list(self.children):
            yield from c.iter()

    def text_content(self):
        if self.tag == "#text":
            return self.text
        if self.tag == "#comment":
            return ""
        return "".join(c.text_content() for c in self.children)

    def replace_with(self, *nodes):
        parent = self.parent
        i = parent.children.index(self)
        for n in nodes:
            n.parent = parent
        parent.children[i:i + 1] = list(nodes)
        self.parent = None

    def unwrap(self):
        self.replace_with(*self.children)

    def remove(self):
        if self.parent is not None:
            self.parent.children.remove(self)
            self.parent = None


def text_node(s):
    return Node("#text", text=s)


def element(tag, attrs=None, children=(), keep_class=True):
    n = Node(tag, attrs)
    n.keep_class = keep_class
    for c in children:
        n.append(c)
    return n


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.stack = [self.root]

    def _in_scope(self, names, limit=SCOPE_LIMIT):
        for node in reversed(self.stack[1:]):
            if node.tag in names:
                return node
            if node.tag in limit:
                return None
        return None

    def _pop_to(self, node):
        while self.stack[-1] is not node:
            self.stack.pop()
        self.stack.pop()

    def handle_starttag(self, tag, attrs):
        if tag in CLOSES_P:
            p = self._in_scope({"p"})
            if p:
                self._pop_to(p)
        if tag == "li":
            li = self._in_scope({"li"}, SCOPE_LIMIT | {"ol", "ul"})
            if li:
                self._pop_to(li)
        elif tag in ("dt", "dd"):
            d = self._in_scope({"dt", "dd"}, SCOPE_LIMIT | {"dl"})
            if d:
                self._pop_to(d)
        elif tag == "tr":
            r = self._in_scope({"tr", "td", "th"}, {"table"})
            if r:
                while self.stack[-1].tag != "tr" and self.stack[-1].tag in ("td", "th"):
                    self.stack.pop()
                if self.stack[-1].tag == "tr":
                    self.stack.pop()
        elif tag in ("td", "th"):
            cell = self._in_scope({"td", "th"}, {"table", "tr"})
            if cell:
                self._pop_to(cell)
        node = self.stack[-1].append(Node(tag, [(k, v if v is not None else "") for k, v in attrs]))
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for node in reversed(self.stack[1:]):
            if node.tag == tag:
                self._pop_to(node)
                return
        # A stray end tag with nothing open to close is ignored, as browsers do.

    def handle_data(self, data):
        self.stack[-1].append(text_node(data))

    def handle_comment(self, data):
        self.stack[-1].append(Node("#comment", text=data))


def parse(source):
    b = TreeBuilder()
    b.feed(source)
    b.close()
    return b.root


def find(root, pred):
    for n in root.iter():
        if n.is_el() and pred(n):
            return n
    return None


def find_all(root, pred):
    return [n for n in root.iter() if n.is_el() and pred(n)]


def has_class(name):
    return lambda n: name in n.classes()


# ---------------------------------------------------------------------------
# Serializer: tidy, indented HTML with inline content kept on one line.
# ---------------------------------------------------------------------------

def esc_text(s):
    return html.escape(s, quote=False).replace("\xa0", "&nbsp;")


def attrs_html(node):
    out = []
    for k, v in node.attrs.items():
        out.append(f' {k}="{html.escape(v, quote=True)}"' if v != "" or k in ("alt",) else f" {k}")
    return "".join(out)


def is_block(n):
    return n.is_el() and n.tag in BLOCK


def inline_html(n):
    if n.tag == "#text":
        return esc_text(re.sub(r"[ \t\r\n\f]+", " ", n.text))
    if n.tag == "#comment":
        return f"<!--{n.text}-->"
    if n.tag == "pre":
        return pre_html(n)
    inner = "".join(inline_html(c) for c in n.children)
    if n.tag in VOID:
        return f"<{n.tag}{attrs_html(n)}>"
    return f"<{n.tag}{attrs_html(n)}>{inner}</{n.tag}>"


def pre_html(n):
    return f"<pre{attrs_html(n)}>" + "".join(
        esc_text(c.text) if c.tag == "#text" else
        (f"<!--{c.text}-->" if c.tag == "#comment" else raw_html(c))
        for c in n.children) + "</pre>"


def raw_html(n):
    """Serializes without touching whitespace (used inside <pre>)."""
    if n.tag == "#text":
        return esc_text(n.text)
    if n.tag == "#comment":
        return f"<!--{n.text}-->"
    if n.tag in VOID:
        return f"<{n.tag}{attrs_html(n)}>"
    return f"<{n.tag}{attrs_html(n)}>" + "".join(raw_html(c) for c in n.children) + f"</{n.tag}>"


def block_lines(n, depth):
    ind = "  " * depth
    if n.tag == "pre":
        return [ind + pre_html(n)]
    if not is_block(n):
        s = inline_html(n).strip()
        return [ind + s] if s else []
    open_tag = f"<{n.tag}{attrs_html(n)}>"
    if n.tag in VOID:
        return [ind + open_tag]
    close_tag = f"</{n.tag}>"
    if not any(is_block(c) for c in n.children):
        inner = "".join(inline_html(c) for c in n.children).strip()
        return [ind + open_tag + inner + close_tag]
    lines = [ind + open_tag]
    run = []

    def flush():
        s = "".join(run).strip()
        if s:
            lines.append("  " * (depth + 1) + s)
        run.clear()

    for c in n.children:
        if is_block(c):
            flush()
            lines.extend(block_lines(c, depth + 1))
        else:
            run.append(inline_html(c))
    flush()
    lines.append(ind + close_tag)
    return lines


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

ICON_MAX_BYTES = 4096
NOTE_KINDS = {"ai": "note ai", "infobox": "note tip", "warning": "note warning",
              "due-date": "note due-date"}
KEEP_ATTRS = {
    "*": {"id", "title", "lang", "dir"},
    "a": {"href", "target", "rel"},
    "img": {"src", "alt", "width", "height"},
    "ol": {"type", "start", "reversed"},
    "li": {"value", "type"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
}


def is_blank(n):
    return (n.tag == "#text" and not n.text.strip()) or n.tag == "#comment"


def meaningful(children):
    return [c for c in children if not is_blank(c)]


def is_toc(n):
    return "table-of-contents" in n.classes()


def strip_page_parts(body):
    """Removes the page title (first h1), author line and old contents box."""
    h1 = find(body, lambda n: n.tag == "h1")
    if h1:
        h1.remove()
    author = find(body, has_class("author"))
    if author:
        author.remove()
    toc = find(body, is_toc)
    if toc:
        toc.remove()
    return h1, author, toc


def read_toc(toc):
    """Returns [(href, text, children)] from an old contents box."""
    lst = find(toc, lambda n: n.tag in ("ol", "ul"))

    def items(list_node):
        result = []
        for li in list_node.children:
            if not li.is_el("li"):
                continue
            a = next((x for x in li.iter() if x.is_el("a") and x.attrs.get("href")
                      and not find_parent_list_between(x, li)), None)
            text = " ".join((a.text_content() if a else direct_text(li)).split())
            sub = next((x for x in li.children if x.is_el("ol", "ul")), None)
            if sub is None:
                sub = find(li, lambda x: x.tag in ("ol", "ul"))
            result.append((a.attrs["href"] if a else None, text, items(sub) if sub else []))
        return result

    return items(lst) if lst else []


def find_parent_list_between(node, li):
    p = node.parent
    while p is not None and p is not li:
        if p.tag in ("ol", "ul"):
            return True
        p = p.parent
    return False


def direct_text(li):
    return "".join(c.text_content() for c in li.children if not c.is_el("ol", "ul"))


def slug(text, used):
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"
    s, i = base, 2
    while s in used:
        s, i = f"{base}-{i}", i + 1
    used.add(s)
    return s


KNOWN = BLOCK | VOID | {"a", "abbr", "b", "cite", "code", "del", "dfn", "em", "font", "i",
                       "ins", "kbd", "label", "mark", "q", "s", "samp", "small", "span",
                       "strong", "sub", "sup", "tt", "u", "var"}
TYPO_TAGS = {"t": "tt", "bb": "b"}  # misspellings found in the existing pages


def convert_inline(body):
    for n in find_all(body, lambda n: n.tag not in KNOWN):
        if n.tag in TYPO_TAGS:
            n.tag, n.attrs = TYPO_TAGS[n.tag], {}
        else:
            keep_id(n)
            n.unwrap()
    for n in find_all(body, lambda n: n.tag == "a" and "name" in n.attrs):
        n.attrs.setdefault("id", n.attrs.pop("name"))
    for n in find_all(body, lambda n: n.tag == "tt"):
        n.tag, n.attrs = "code", {}
    for n in find_all(body, lambda n: n.tag in ("font", "span")):
        if n.tag == "span" and "anchor" in n.classes():
            continue
        style = (n.attrs.get("style") or "").lower()
        mono = "monospace" in style or "courier" in (n.attrs.get("face") or "").lower()
        colored = "color" in style or "color" in n.attrs
        text = n.text_content().strip()
        if n.parent and n.parent.tag in ("code", "pre"):
            mono = colored = False
        if mono or (colored and text and not re.search(r"\s", text)):
            n.tag, n.attrs = "code", {}
        elif n.attrs.get("id"):
            n.tag, n.attrs = "span", {"id": n.attrs["id"]}
        else:
            n.unwrap()
    for n in find_all(body, lambda n: n.tag == "a" and n.attrs.get("target")):
        n.attrs["target"] = "_blank"
        n.attrs["rel"] = "noopener"


def convert_notes(body, page_dir):
    for n in find_all(body, lambda n: n.tag == "div" and set(n.classes()) & set(NOTE_KINDS)):
        kind = next(c for c in n.classes() if c in NOTE_KINDS)
        n.tag = "aside"
        n.attrs = {"class": NOTE_KINDS[kind]}
        n.keep_class = True
        # Notes that were never closed swallow the rest of a section: end them
        # at the first heading, as the author intended.
        first_heading = next((c for c in n.children if c.is_el() and c.tag in HEADINGS), None)
        if first_heading:
            i = n.children.index(first_heading)
            rest = n.children[i:]
            del n.children[i:]
            parent = n.parent
            at = parent.children.index(n) + 1
            for r in rest:
                r.parent = parent
            parent.children[at:at] = rest
        # Small decorative icons (alert.png, idea.png) are replaced by the note style.
        for img in find_all(n, lambda x: x.tag == "img"):
            path = os.path.join(page_dir, img.attrs.get("src", ""))
            try:
                small = os.path.getsize(path) <= ICON_MAX_BYTES
            except OSError:
                small = False
            if small:
                img.remove()
        group_paragraphs(n)
    # Join neighbouring AI boxes into one "Use of AI" note.
    for n in find_all(body, lambda n: n.tag == "aside" and "ai" in n.classes()):
        if n.parent is None:
            continue
        siblings = n.parent.children
        i = siblings.index(n) + 1
        while i < len(siblings) and is_blank(siblings[i]):
            i += 1
        while i < len(siblings) and siblings[i].is_el("aside") and "ai" in siblings[i].classes():
            nxt = siblings[i]
            for c in list(nxt.children):
                n.append(c)
            nxt.remove()
            while i < len(siblings) and is_blank(siblings[i]):
                i += 1
    for n in find_all(body, lambda n: n.tag == "aside" and "ai" in n.classes()):
        title = element("p", {"class": "note-title", "data-added": ""}, [text_node("Use of AI")])
        title.parent = n
        n.children.insert(0, title)
        n.attrs["aria-label"] = "Use of AI"


def unwrap_layout(body):
    # Tables with a single cell only position content.
    for t in find_all(body, lambda n: n.tag == "table"):
        rows = [r for r in t.iter() if r.is_el("tr")]
        cells = [c for c in t.iter() if c.is_el("td", "th")]
        if len(rows) <= 1 and len(cells) <= 1:
            for x in [t] + [y for y in t.iter() if y.is_el("tbody", "thead", "tr", "td", "th")]:
                if x.parent is not None:
                    keep_id(x)
                    x.unwrap()
    for n in find_all(body, lambda n: n.tag in ("div", "center")):
        keep_id(n)
        n.unwrap()


def keep_id(n):
    """Leaves an empty anchor behind so links to an unwrapped element still work."""
    if n.attrs.get("id") and n.attrs["id"] != "page":
        anchor = Node("span", {"id": n.attrs["id"]})
        n.children.insert(0, anchor)
        anchor.parent = n


def convert_pre(body):
    for pre in find_all(body, lambda n: n.tag == "pre"):
        text = pre.text_content().replace("\r\n", "\n")
        text = re.sub(r"^\s*\n", "", text)      # leading blank lines
        text = text.rstrip()
        text = textwrap.dedent(text)
        lines = [l for l in text.split("\n") if l.strip()]
        command = bool(lines) and all(re.match(r"sudo\s", l.lstrip()) for l in lines) \
            and all(not l.startswith(" ") for l in lines)
        code = element("code")
        if command and len(lines) > 1:
            for l in text.split("\n"):
                code.append(element("span", {"class": "line"}, [text_node(l)]))
        else:
            code.append(text_node(text))
        new_pre = element("pre", children=[code])
        wrapper = element("div", {"class": "code command" if command else "code"}, [new_pre])
        pre.replace_with(wrapper)


def shift_headings(body):
    hs = find_all(body, lambda n: n.tag in HEADINGS)
    if not hs:
        return
    top = min(int(h.tag[1]) for h in hs)
    for h in hs:
        h.tag = "h" + str(min(6, max(2, int(h.tag[1]) + 2 - top)))


def fix_anchors(body):
    ids = {}
    for n in body.iter():
        if n.is_el() and n.attrs.get("id"):
            ids.setdefault(n.attrs["id"], []).append(n)
    for n in find_all(body, lambda n: n.tag == "span" and "anchor" in n.classes()):
        aid = n.attrs.get("id")
        if not aid or meaningful(n.children):
            n.attrs.pop("class", None)
            continue
        if len(ids.get(aid, [])) > 1:
            n.remove()
            ids[aid].remove(n)
            continue
        nxt = next_element(n)
        if nxt is not None and nxt.tag in HEADINGS and not nxt.attrs.get("id"):
            nxt.attrs["id"] = aid
            n.remove()
        else:
            n.attrs = {"id": aid}


def next_element(n):
    """The next element in document order that is not blank text."""
    cur = n
    while cur is not None:
        if cur.parent is None:
            return None
        sib = cur.parent.children
        i = sib.index(cur) + 1
        while i < len(sib) and is_blank(sib[i]):
            i += 1
        if i < len(sib):
            nxt = sib[i]
            if nxt.tag == "#text":
                return None
            while nxt.is_el() and nxt.tag not in HEADINGS and meaningful(nxt.children) \
                    and nxt.tag in ("section", "div", "p"):
                nxt = meaningful(nxt.children)[0]
            return nxt
        cur = cur.parent
    return None


def clean_attrs(body):
    for n in body.iter():
        if not n.is_el():
            continue
        allowed = KEEP_ATTRS["*"] | KEEP_ATTRS.get(n.tag, set())
        if n.keep_class:
            allowed = allowed | {"class", "aria-label", "data-added"}
        n.attrs = {k: v for k, v in n.attrs.items() if k in allowed}


def group_paragraphs(container):
    """Wraps loose text and inline elements in <p>."""
    out, run = [], []

    def empty_anchor(c):
        return c.is_el("span") and not meaningful(c.children)

    def flush():
        if any(not is_blank(c) and not c.is_el("br") and not empty_anchor(c) for c in run):
            while run and (is_blank(run[0]) or run[0].is_el("br")):
                out.append(run.pop(0)) if run[0].tag == "#comment" else run.pop(0)
            while run and (is_blank(run[-1]) or run[-1].is_el("br")):
                run.pop()
            out.append(element("p", children=run[:], keep_class=False))
        else:
            out.extend(c for c in run if c.tag == "#comment" or empty_anchor(c))
        run.clear()

    for c in container.children:
        if is_block(c):
            flush()
            out.append(c)
        else:
            run.append(c)
    flush()
    container.children = []
    for c in out:
        container.append(c)


def remove_empty_paragraphs(root):
    """Old pages used empty <p> tags as spacers."""
    for p in find_all(root, lambda n: n.tag == "p"):
        kids = meaningful(p.children)
        if (not kids or all(c.is_el("br") for c in kids)) and not p.attrs.get("id"):
            p.replace_with(*[c for c in p.children if c.tag == "#comment"])


def tidy_blocks(article):
    # A list placed directly inside another list (<ol><ol>...</ol></ol>) shows as
    # a doubly indented list; keep just the inner one.
    for lst in find_all(article, lambda n: n.tag in ("ol", "ul")):
        kids = meaningful(lst.children)
        if lst.parent is not None and len(kids) == 1 and kids[0].is_el("ol", "ul"):
            lst.unwrap()
    remove_empty_paragraphs(article)
    for n in [article] + find_all(article, lambda n: n.tag in ("aside", "blockquote")):
        group_paragraphs(n)
    # List items that hold blocks (code, lists) read better with their text in paragraphs.
    for li in find_all(article, lambda n: n.tag in ("li", "dd")):
        if any(is_block(c) for c in li.children):
            group_paragraphs(li)
    remove_empty_paragraphs(article)
    # A paragraph holding only an image becomes a figure.
    for p in find_all(article, lambda n: n.tag == "p"):
        kids = [c for c in meaningful(p.children) if not c.is_el("br")]
        if len(kids) == 1 and kids[0].is_el("img"):
            p.replace_with(element("figure", children=[kids[0]]))
    for t in find_all(article, lambda n: n.tag == "table"):
        wrap = element("div", {"class": "table-wrap"})
        t.replace_with(wrap)
        wrap.append(t)


def build_toc(entries, article):
    ids = {n.attrs["id"] for n in article.iter() if n.is_el() and n.attrs.get("id")}
    used = set(ids)
    if not entries:
        for h in find_all(article, lambda n: n.tag in ("h2", "h3")):
            if not h.attrs.get("id"):
                h.attrs["id"] = slug(h.text_content(), used)
        flat, stack = [], []
        for h in find_all(article, lambda n: n.tag in ("h2", "h3")):
            item = ("#" + h.attrs["id"], " ".join(h.text_content().split()), [])
            if h.tag == "h2" or not flat:
                flat.append(item)
            else:
                flat[-1][2].append(item)
        entries = flat
        ids = {n.attrs["id"] for n in article.iter() if n.is_el() and n.attrs.get("id")}

    missing = []

    def ol(items, depth):
        ind = "  " * depth
        lines = [ind + "<ol>"]
        for href, text, kids in items:
            if href and href.startswith("#") and href[1:] not in ids:
                missing.append(href)
            label = (f'<a href="{html.escape(href)}">{esc_text(text)}</a>' if href
                     else f"<span>{esc_text(text)}</span>")
            if kids:
                lines.append(f"{ind}  <li>{label}")
                lines.extend(ol(kids, depth + 2))
                lines.append(f"{ind}  </li>")
            else:
                lines.append(f"{ind}  <li>{label}</li>")
        lines.append(ind + "</ol>")
        return lines

    return ("\n".join(ol(entries, 4)) if entries else ""), missing


PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="index,nofollow">
  <meta name="color-scheme" content="light dark">
  <title>{title}</title>
  <link rel="stylesheet" href="../../css/exercise.css">
  <script src="../../js/exercise.js" defer></script>
</head>

<body>
  <header class="masthead">
    <div class="wrap">
      <a class="back" href="../../index.html">&larr; SPHERE Shared Education Materials</a>
{eyebrow}      <h1>{heading}</h1>
{author}    </div>
  </header>

  <div class="wrap layout">
{toc}    <article>
{article}
    </article>
  </div>
</body>
</html>
"""

TOC = """    <details class="toc" open>
      <summary>Contents</summary>
      <nav aria-label="Contents">
        <h2 class="toc-title">Contents</h2>
{list}
      </nav>
    </details>

"""


def convert(source, page_dir):
    root = parse(source)
    title_node = find(root, lambda n: n.tag == "title")
    title = " ".join(title_node.text_content().split()) if title_node else ""
    body = find(root, lambda n: n.tag == "body") or root
    for n in find_all(body, lambda n: n.tag in ("script", "style", "head", "title", "link", "meta")):
        n.remove()

    h1, author, toc = strip_page_parts(body)
    toc_entries = read_toc(toc) if toc else []

    convert_inline(body)
    convert_notes(body, page_dir)
    unwrap_layout(body)
    convert_pre(body)
    shift_headings(body)
    fix_anchors(body)
    clean_attrs(body)

    article = element("article")
    for c in list(body.children):
        c.parent = None
        article.append(c)
    tidy_blocks(article)

    # Header text
    topic, sep, rest = title.partition(": ")
    heading = " ".join(h1.text_content().split()) if h1 else (rest if sep else title)
    if sep and heading.startswith(topic + ": "):
        heading = heading[len(topic) + 2:]
    eyebrow = f'      <p class="eyebrow">{esc_text(topic)}</p>\n' if sep else ""
    author_html = ""
    if author:
        kids = list(author.children)
        while kids and (is_blank(kids[-1]) or kids[-1].is_el("br")):
            kids.pop()
        inner = "".join(inline_html(c) for c in kids).strip()
        if inner:
            author_html = f'      <p class="author">{inner}</p>\n'

    toc_list, missing = build_toc(toc_entries, article)
    body_lines = []
    for c in article.children:
        body_lines.extend(block_lines(c, 3))
    page = PAGE.format(
        title=esc_text(title),
        eyebrow=eyebrow,
        heading=esc_text(heading),
        author=author_html,
        toc=TOC.format(list=toc_list) if toc_list else "",
        article="\n".join(body_lines),
    )
    return page, missing


# ---------------------------------------------------------------------------
# Checking that no text was lost
# ---------------------------------------------------------------------------

def visible_text(node):
    if node.tag == "#text":
        return node.text
    if node.tag == "#comment" or (node.is_el() and (node.tag in ("script", "style", "title")
                                                    or "data-added" in node.attrs)):
        return ""
    return "".join(visible_text(c) for c in node.children)


def compare_text(old_source, new_page):
    old = parse(old_source)
    body = find(old, lambda n: n.tag == "body") or old
    strip_page_parts(body)
    for n in find_all(body, lambda n: n.tag in ("head", "title", "script", "style")):
        n.remove()
    new = parse(new_page)
    article = find(new, lambda n: n.tag == "article")
    a = re.sub(r"\s+", "", visible_text(body))
    b = re.sub(r"\s+", "", visible_text(article)) if article else ""
    if a == b:
        return None
    i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
    return f"text differs at character {i}:\n    old: …{a[max(0, i - 40):i + 40]}…\n    new: …{b[max(0, i - 40):i + 40]}…"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+", help="old-style exercise pages")
    ap.add_argument("-o", "--output", metavar="FILE", help="write here (one input file only)")
    ap.add_argument("--in-place", action="store_true", help="overwrite each input file")
    ap.add_argument("--force", action="store_true",
                    help="write even if the text check fails or the page is already converted")
    args = ap.parse_args()

    if len(args.files) > 1 and not args.in_place:
        ap.error("use --in-place to convert more than one file")
    if args.output and args.in_place:
        ap.error("use either -o or --in-place, not both")

    failures = 0
    for path in args.files:
        with open(path, encoding="utf-8", errors="replace") as f:
            source = f.read()
        if "css/exercise.css" in source and not args.force:
            print(f"{path}: already converted, skipped", file=sys.stderr)
            continue
        page, missing = convert(source, os.path.dirname(os.path.abspath(path)))
        problem = compare_text(source, page)
        if problem:
            failures += 1
            print(f"{path}: {problem}", file=sys.stderr)
            if not args.force:
                print(f"{path}: not written (use --force to write anyway)", file=sys.stderr)
                continue
        for href in missing:
            print(f"{path}: contents link {href} has no matching section", file=sys.stderr)
        if args.in_place:
            with open(path, "w", encoding="utf-8") as f:
                f.write(page)
            print(f"{path}: converted", file=sys.stderr)
        elif args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(page)
            print(f"{path}: written to {args.output}", file=sys.stderr)
        else:
            sys.stdout.write(page)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
