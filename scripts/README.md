# Scripts

## convert_index.py

Converts an old-style `index.html` (a numbered list of links) into the catalog
layout used by the front page. The new page depends on `css/catalog.css` for
its styling and `js/catalog.js` for tags and search; the script only writes the
HTML. It needs only Python 3, with no extra packages.

Run it from the site folder:

```bash
python3 scripts/convert_index.py old_index.html --previous index.html -o index.html
```

### What it does

- Each `<li><a href="...">Topic: Name</a></li>` becomes a catalog row, split
  into topic and name at the first `: `. The page title and intro sentence are
  taken from the old file.
- Tags and descriptions are copied from the `--previous` page (normally the
  current `index.html`) for every entry with the same link. `--previous` and
  `-o` can name the same file.
- Entries that are not on the `--previous` page get no tags, and their
  description is the first sentence of the Overview section of the exercise
  page. These sentences are often wordy ("The purpose of this exercise
  is to…"), so you may want to shorten them.
- When it finishes, it lists the entries that are missing tags or a
  description, so you know what to fill in.

### Options

| Option | Meaning |
| --- | --- |
| `--previous FILE` | Page in the new layout to copy tags and descriptions from. |
| `-o FILE`, `--output FILE` | Where to write the result. Without it, the page is printed to the screen. |
| `--sort` | Sort entries alphabetically instead of keeping the old file's order. |
| `--site-dir DIR` | Site folder that the links are relative to, used to find each exercise's Overview. Defaults to the folder holding the old file. |

### Tags

Tags live in the `data-tags` attribute of each entry in `index.html`, as a
comma-separated list:

```html
<li data-tags="web, databases, secure-coding, attack, defense">
```

The tag filters on the page are built from these automatically. Reuse existing
tags where you can; `attack` and `defense` are shown in red and blue.

## convert_exercise.py

Converts an old-style exercise page (`docs/<name>/index.html`, styled by
`css/common.css` and `css/screen.css`) into the modern layout used by
`docs/synflood/index.html`. The new page depends on `css/exercise.css` for its
styling and `js/exercise.js` for copy buttons and the contents list; the script
only writes the HTML. It needs only Python 3, with no extra packages.

Run it from the site folder. To look at the result first, write it somewhere
else:

```bash
python3 scripts/convert_exercise.py docs/xss/index.html -o /tmp/xss.html
```

To convert pages in place (git keeps the old versions):

```bash
python3 scripts/convert_exercise.py --in-place docs/xss/index.html
```

```bash
python3 scripts/convert_exercise.py --in-place docs/*/index.html
```

Pages that already use `css/exercise.css` are skipped, so running it on every
page is safe.

### What it does

- The wording is kept exactly. Before writing, the script compares all the
  text of the old and new page and refuses to write if anything differs. It
  then prints where the difference is.
- The page title, author line and contents list move into a dark header and a
  contents sidebar that stays visible on wide screens and folds into a
  "Contents" button on phones.
- `<pre>` blocks become code blocks with a Copy button. A block where every
  line starts with `sudo` is shown as a command, with a `$` prompt.
- The old boxes become styled notes: AI guidance (`ai`, titled "Use of AI"),
  tips (`infobox`), warnings (`warning`) and due dates (`due-date`). Their small
  icons, such as `alert.png` and `idea.png`, are dropped. A box that was never
  closed is ended at the next heading.
- `<tt>` becomes `<code>`, and so does coloured or monospace text without
  spaces (for example a red lab name). Other old formatting is removed:
  `<font>`, `<center>`, inline styles, and tables or `<div>`s used only for
  layout.
- Headings are renumbered so sections start at `<h2>`. Old anchor links keep
  working.
- Empty spacer paragraphs are removed, and loose text is wrapped in
  paragraphs. An image alone in a paragraph becomes a figure, and wide tables
  scroll sideways on phones.
- HTML comments, including instructor notes, are kept as they are.

It also reports contents links that point to a section that doesn't exist.
These links were already broken on the old pages; fix them by hand.

### Options

| Option | Meaning |
| --- | --- |
| `-o FILE`, `--output FILE` | Write the result here (one input page only). Without `-o` or `--in-place`, the page is printed to the screen. |
| `--in-place` | Overwrite each input page. Needed when converting more than one page. |
| `--force` | Write even if the text check fails, or if the page is already converted. |

### After converting

Check each converted page in a browser. The script can't catch these by itself:

- **Commands vs. output:** only blocks where every line starts with `sudo` get
  the `$` prompt. To mark another block as a command, change its class to
  `code command`; for sample output, use `code output`.
- **Figures:** an image followed by text such as a full stop stays inline
  rather than becoming a figure.
