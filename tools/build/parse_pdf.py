"""Turn one bermudalaws.bm consolidated PDF into files: one per section or schedule, one paragraph per line.

    python scripts/bermuda-law/parse_pdf.py <pdf> [<act id>]     # prints the files, for inspection

The PDFs are born digital (Antenna House XSL Formatter, "Government of Bermuda (XSL v.2.4.2.x)") with one layout:
- page 1: crest letters, BERMUDA, the title and number ("1951 : 89", "BX 182 / 1968"), then TABLE OF CONTENTS;
- a running header (the title, bold 10pt) on every later page and the page number (bold 12pt) at the foot;
- section headings bold 9pt at the left margin (x 108), the section number in the margin on the first body line,
  subsection and paragraph labels "(1)", "(a)", "(i)" in front of their text on the same baseline;
- PART / CHAPTER / SCHEDULE headings bold and centred; cross-headings italic and centred;
- history notes in italic 8pt below a section: "[Section 7 amended by 2008:44 s.3 effective 23 December 2008]";
- end matter: "[Assent Date: ...]", "[Operative Date: ...]" or "[This Act was brought into operation ...]", and
  "[Amended by: 1953 : 37 ... ]" in 7pt.
The header, footer and crest are dropped by their content (title text, a bare page number, the crest font), not by
position alone. Everything else is kept, in the order printed, so the letters of the files read in index order equal
the letters of the PDF (check_repo.py checks this against pdftotext).
"""
from __future__ import annotations

import re
import sys
import unicodedata

import pymupdf as fitz

LABEL = re.compile(r'^(?:\(?[0-9]{1,3}[A-Z]{0,3}\)|\([a-z]{1,2}\)|\([A-Z]{1,2}\)|\([ivxlc]{1,7}\)|\([0-9]{1,3}[a-z]{1,2}\)|'
                   r'“\([0-9A-Za-z]{1,6}\)|[0-9]{1,3}[A-Z]{0,3}\.?)$')
SECNUM = re.compile(r'^[0-9]{1,3}[A-Z]{0,3}$')
ORDINALS = {'FIRST': '1', 'SECOND': '2', 'THIRD': '3', 'FOURTH': '4', 'FIFTH': '5', 'SIXTH': '6', 'SEVENTH': '7',
            'EIGHTH': '8', 'NINTH': '9', 'TENTH': '10'}
SCHEDULE = re.compile(r'^(?:SCHEDULE\s+([0-9]{1,2}[A-Z]?)\b|(FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|'
                      r'NINTH|TENTH)\s+SCHEDULE(?:\s+([A-Z])\b(?!\s+[A-Z]))?|SCHEDULE$)')
END_MATTER = re.compile(r'^\[(?:Assent Date:|Operative Date:|This (?:Act|Order) was brought into operation|Amended by:)')
SOFT = re.compile('[\u00ad\u200b\ufeff]')
SPACES = re.compile('[\\s\u2002\u2003\u2009\u202f]+')


def norm(s: str) -> str:
    return SPACES.sub(' ', SOFT.sub('', unicodedata.normalize('NFC', s))).strip()


def green(colour: int) -> bool:
    """The site's colour for provisions not yet in force (#339966). Other colours (blue e-mail links, the near-black
    of an embedded emblem, white) are ordinary text."""
    r, g, b = colour >> 16 & 255, colour >> 8 & 255, colour & 255
    return g > r + 40 and g > b + 20


class Frag:
    __slots__ = ('x0', 'x1', 'y', 'text', 'size', 'bold', 'italic', 'font')

    def __init__(self, line: dict, black_only: bool = False):
        spans = [s for s in line['spans'] if s['text'] and not (black_only and green(s['color']) and s['text'].strip())]
        self.x0, _, self.x1, _ = line['bbox']
        self.y = spans[0]['origin'][1] if spans else line['bbox'][3]
        self.text = ''.join(s['text'] for s in spans)
        ink = [s for s in spans if s['text'].strip()] or spans
        self.size = round(max(s['size'] for s in ink), 1) if ink else 0
        self.bold = bool(ink) and all('Bold' in s['font'] or s['flags'] & 16 for s in ink)
        self.italic = bool(ink) and all('Italic' in s['font'] or s['flags'] & 2 for s in ink)
        self.font = ink[0]['font'] if ink else ''


class Row:
    """All fragments on one baseline of one page, left to right."""

    def __init__(self, page: int, frags: list[Frag]):
        self.page = page
        self.frags = sorted(frags, key=lambda f: f.x0)
        self.y = min(f.y for f in frags)
        self.x0 = self.frags[0].x0
        self.x1 = max(f.x1 for f in frags)
        ink = [f for f in self.frags if f.text.strip()]
        self.size = max(f.size for f in ink) if ink else 0
        self.bold = bool(ink) and all(f.bold for f in ink)
        self.italic = bool(ink) and all(f.italic for f in ink)
        self.L, self.R = 108, 504  # the page's left margin and right edge (set by rows_of)

    @property
    def text(self) -> str:
        out = ''
        prev = None
        for f in self.frags:
            t = norm(f.text)
            if not t:
                continue
            if prev is not None:
                gap = f.x0 - prev.x1
                out += ' | ' if gap > 20 and not LABEL.match(norm(prev.text)) else ' '
            out += t
            prev = f
        return out

    def label(self) -> str | None:
        """The leading margin label ("12A", "(1)", "(a)") if this row starts with one followed by text."""
        if len(self.frags) < 2:
            return None
        t = norm(self.frags[0].text)
        return t if LABEL.match(t) and self.frags[1].x0 - self.frags[0].x1 > 2 else None

    @property
    def centred(self) -> bool:
        return self.x0 > self.L + 4 and abs((self.x0 + self.x1) / 2 - (self.L + self.R) / 2) < 16 \
            and self.label() is None


HEADER = re.compile(r'^(?:Title \d+[A-Z]?|Laws of Bermuda|Item \d+[0-9A-Za-z().]*|Laws of Bermuda Item \d+[0-9A-Za-z().]*)$',
                    re.I)
FOOTER = re.compile(r'^(?:\d{1,4}|\d{0,4}1989Revision\d{0,4})$', re.I)  # matched with the spaces taken out


def _mode(values: list[float]) -> float:
    counts: dict[int, int] = {}
    for v in values:
        counts[round(v)] = counts.get(round(v), 0) + 1
    return max(sorted(counts), key=lambda k: counts[k]) if counts else 0


def rows_of(pdf_path: str, title: str, black_only: bool = False) -> list[Row]:
    """The printed rows of the PDF, without the crest, running headers and footers.
    Two layouts: the XSL-formatted PDFs (margin x 108, running title header, bold page number) and the older
    Word-made "1989 Revision" PDFs (mirrored margins, "Title 5 / Laws of Bermuda / Item 16(a)" header on odd pages,
    the title on even pages, "1989 Revision" and the page number at the foot)."""
    doc = fitz.open(pdf_path)
    out: list[Row] = []
    tnorm = norm(title).upper()
    pages: list[list[Frag]] = []
    for pno, page in enumerate(doc):
        frags = []
        rev_y: list[float] = []
        height = page.rect.height
        for b in page.get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE)['blocks']:
            for line in b.get('lines', []):
                f = Frag(line, black_only)
                t = norm(f.text)
                if not t:
                    continue
                if pno == 0 and f.size <= 7.5 and f.y < 220:
                    continue  # the crest's letters ("QUO FATA FERUNT")
                if f.y < 160 and (HEADER.match(t) or (pno > 0 and f.bold and t.upper().replace(' ', '') == tnorm.replace(' ', ''))):
                    continue  # running header: the title, or "Title 5 / Laws of Bermuda / Item 16(a)"
                if f.y > height * 0.75 and FOOTER.match(t.replace(' ', '')) and f.size >= 9.5 and (f.bold or f.italic or f.size >= 10.5):
                    if 'revision' in t.lower().replace(' ', ''):
                        rev_y.append(f.y)
                    continue  # page number, "1989 Revision"
                frags.append(f)
        # a "1989 Revisio" + "n" footer split in two
        split = [g for g in frags if g.y > height * 0.75 and g.italic and g.size >= 10.5
                 and re.fullmatch(r'1989 ?Revisi?o?', norm(g.text))]
        rev_y += [g.y for g in split]
        if split:
            frags = [g for g in frags if g not in split and not (
                g.y > height * 0.75 and g.italic and g.size >= 10.5 and norm(g.text) in ('n', 'on', 'ion'))]
        # a page number in body type just above the "1989 Revision" footer, away from the section-number margin
        rev = sorted(rev_y)
        if rev:
            frags = [g for g in frags if not (re.fullmatch(r'\d{1,4}', norm(g.text)) and rev[0] - 22 <= g.y < rev[0]
                                              and g.size >= 9 and all(abs(g.x0 - x) > 4 for x in (108, 180)))]
        # a running title wrapped onto two printed rows ("... (RESTRICTED ZONES) ORDER" / "2010")
        top = [g for g in frags if pno > 0 and g.y < 160 and g.bold and g.size >= 10]
        if len(top) >= 2 and ''.join(norm(g.text) for g in top[:2]).upper().replace(' ', '') == tnorm.replace(' ', ''):
            frags = [g for g in frags if g is not top[0] and g is not top[1]]
        pages.append(frags)
    geo = {}
    for parity in (0, 1):
        ps = [fr for k, fr in enumerate(pages) if k % 2 == parity and fr]
        lefts = [min(f.x0 for f in fr if f.size >= 8.5) for fr in ps if any(f.size >= 8.5 for f in fr)]
        rights = [max(f.x1 for f in fr if f.size >= 8.5) for fr in ps if any(f.size >= 8.5 for f in fr)]
        geo[parity] = (_mode(lefts) or 108, _mode(rights) or 504)
    for pno, frags in enumerate(pages):
        frags.sort(key=lambda f: (round(f.y, 1), f.x0))
        group: list[Frag] = []
        rows = []
        for f in frags:
            if group and abs(f.y - group[0].y) > 2.0:
                rows.append(Row(pno, group))
                group = []
            group.append(f)
        if group:
            rows.append(Row(pno, group))
        for r in rows:
            r.L, r.R = geo[pno % 2]
        out += rows
    return out


def schedule_id(text: str) -> str | None:
    m = SCHEDULE.match(text)
    if not m:
        return None
    if m.group(1):
        return m.group(1)
    if m.group(2):
        return ORDINALS[m.group(2)] + (m.group(3) or '')
    return ''


WORDS = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*")
VOCAB: dict = {'plain': set(), 'hyphenated': set()}


def learn(rows: list['Row']) -> None:
    """The document's own vocabulary, to tell a line-end hyphen that breaks a word ("dis-" + "cretion") from one
    that belongs to it ("Attorney-" + "General"): words and hyphenated compounds printed whole, inside a line."""
    VOCAB['plain'] = set()
    VOCAB['hyphenated'] = set()
    for r in rows:
        t = r.text
        if t.endswith('-'):
            t = t[:t.rstrip('-').rfind(' ') + 1]  # the broken word at the end is not evidence
        for w in WORDS.findall(t):
            w = w.lower()
            (VOCAB['hyphenated'] if '-' in w else VOCAB['plain']).add(w)


def join_hyphen(text: str, nxt: str) -> str:
    """Join a line ending in '-' to the next. The hyphen goes only when the joined word is printed whole elsewhere in
    the document and the hyphenated form is not; otherwise it stays, as printed."""
    left = re.search(r'([A-Za-z]+)-$', text)
    right = re.match(r'([A-Za-z]+)', nxt)
    if left and right:
        a, b = left.group(1).lower(), right.group(1).lower()
        if f'{a}-{b}' not in VOCAB['hyphenated'] and (a + b) in VOCAB['plain']:
            return text[:-1] + nxt
    return text + nxt


class Unit:
    def __init__(self, path: str, heading: list[str]):
        self.path = path
        self.lines: list[str] = list(heading)
        self.para: list[Row] = []

    def flush(self):
        if not self.para:
            return
        text = ''
        for r in self.para:
            t = r.text
            if not text:
                text = t
            elif text.endswith('-') and not text.endswith(' -'):
                text = join_hyphen(text, t)
            elif text.endswith(('—', '–')) and not text.endswith((' —', ' –')):
                text += t
            else:
                text += ' ' + t
        self.lines.append(text)
        self.para = []


def parse(pdf_path: str, act: dict, black_only: bool = False) -> dict:
    """{'files': {relative path: text}, 'order': [relative paths in printed order], 'notes': [(file, note)]}.
    black_only: leave out text printed in green, the site's mark for provisions not yet in force."""
    rows = rows_of(pdf_path, act['title'], black_only)
    learn(rows)
    sub_acts = act.get('sub_acts', {})          # centred heading -> folder, e.g. constitution: Schedule 2
    not_schedules = set(act.get('not_schedules', []))
    base = act.get('main_folder', '')           # folder of the main instrument's own sections
    folder = ''
    units: list[Unit] = []
    pending: list[str] = []
    cur: Unit | None = None
    mode = 'front'
    in_schedule = False
    amended_list = False

    def path(name: str) -> str:
        return f'{folder}/{name}' if folder else name

    def start(name: str) -> Unit:
        nonlocal cur, pending
        if cur:
            cur.flush()
        p = path(name)
        k = 2
        while any(u.path == p for u in units):
            p = path(f'{name[:-3]}~{k}.md')
            k += 1
        cur = Unit(p, pending)
        pending = []
        units.append(cur)
        return cur

    def section_start(k: int) -> bool:
        """Row k is a bold heading at the left margin whose next row starts with a section number at the margin."""
        r = rows[k]
        if not (r.bold and r.size >= 9 and r.x0 < r.L + 7):
            return False
        j = k + 1
        while j < len(rows) and rows[j].bold and rows[j].x0 < rows[j].L + 7 and rows[j].page == rows[j - 1].page \
                and rows[j].y - rows[j - 1].y < 13:
            j += 1
        if j >= len(rows):
            return False
        n = rows[j]
        return bool(SECNUM.match(norm(n.frags[0].text))) and abs(n.frags[0].x0 - n.L) < 4

    front = start('title.md')
    i = 0
    prev: Row | None = None
    while i < len(rows):
        r = rows[i]
        t = r.text
        if mode == 'front':
            if section_start(i):
                cur.flush()
                cur = None
                folder = base
                mode = 'body'
                continue  # a section heading with no table of contents before it: reread in body mode
            if t == 'TABLE OF CONTENTS' or (t.startswith('ARRANGEMENT OF ') and t.upper() == t):
                mode = 'toc'
                folder = base
                start('contents.md')
                cur.para = [r]
                cur.flush()
                prev = r
                i += 1
                continue
            new_para = prev is None or r.page != prev.page or r.y - prev.y > 13 or r.size != prev.size
            if new_para:
                cur.flush()
            cur.para.append(r)
            prev = r
            i += 1
            continue
        if END_MATTER.match(t) and mode != 'end':
            mode = 'end'
            folder = ''
            start('end.md')
        if mode == 'toc':
            if r.bold and r.size >= 9 or t.startswith('[preamble') or t.startswith('[words of enactment'):
                cur.flush()
                cur = None
                mode = 'body'
                continue  # reread this row in body mode
            if r.label() or r.page != prev.page or r.y - prev.y > 13 or r.size != prev.size or r.centred or prev.centred \
                    or r.italic != prev.italic:
                cur.flush()
            cur.para.append(r)
            prev = r
            i += 1
            continue
        if mode == 'end':
            # "[Amended by:" and then each amending law on a line of its own; other notes one paragraph each
            if prev is not None and (r.page != prev.page or r.y - prev.y > 13 or r.size != prev.size or amended_list):
                cur.flush()
            cur.para.append(r)
            amended_list = amended_list or t.startswith('[Amended by:')
            prev = r
            i += 1
            continue
        # body
        if r.centred and (r.bold or r.italic) and r.size >= 9 and not t.startswith('['):
            sid = schedule_id(t)
            if t in sub_acts:
                if cur:
                    cur.flush()
                cur = None
                folder = sub_acts[t]
                in_schedule = False
                pending.append('## ' + t)
            elif sid is not None and t not in not_schedules:
                in_schedule = True
                start(f"schedule{'-' + sid if sid else ''}.md")
                cur.lines.append('## ' + t)
            elif in_schedule:
                cur.flush()
                cur.lines.append('## ' + t)
            else:
                if cur:
                    cur.flush()
                cur = None
                pending.append('## ' + t)
            prev = r
            i += 1
            continue
        if t == 'ARRANGEMENT OF SECTIONS' and not in_schedule:
            mode = 'toc'
            start('contents.md')
            cur.para = [r]
            cur.flush()
            prev = r
            i += 1
            continue
        if r.bold and r.size >= 9 and r.x0 < r.L + 7 and not in_schedule:
            # a section heading: one or more bold rows, then the section number on the next row
            head = [r]
            j = i + 1
            while j < len(rows) and rows[j].bold and rows[j].x0 < rows[j].L + 7 and rows[j].page == head[-1].page \
                    and rows[j].y - head[-1].y < 13:
                head.append(rows[j])
                j += 1
            nxt = rows[j] if j < len(rows) else None
            num = norm(nxt.frags[0].text) if nxt is not None else ''
            if nxt is not None and SECNUM.match(num) and abs(nxt.frags[0].x0 - nxt.L) < 4:
                start(f'section-{num}.md')
                cur.lines.append('# ' + ' '.join(h.text for h in head))
                prev = head[-1]
                i = j
                continue
            # a bold left heading with no number (e.g. "Constituency 1 - ..."): a heading line inside the unit
            if cur is None:
                pending.append('# ' + ' '.join(h.text for h in head))
            else:
                cur.flush()
                cur.lines.append('### ' + ' '.join(h.text for h in head))
            prev = head[-1]
            i = j
            continue
        if cur is None:
            # loose text between headings (e.g. "[preamble and words of enactment omitted]")
            pending.append(t)
            prev = r
            i += 1
            continue
        new_para = (not cur.para or r.label() is not None or r.size != prev.size or r.italic != prev.italic
                    or (r.page == prev.page and r.y - prev.y > (11.8 if in_schedule else 13))
                    or (r.page != prev.page and (prev.x1 < prev.R - 9 or t.startswith('“')))
                    or prev.centred)
        if new_para:
            cur.flush()
        cur.para.append(r)
        prev = r
        i += 1
    if cur:
        cur.flush()
    if pending:
        u = Unit(path('headings.md'), pending)
        units.append(u)
    files = {}
    order = []
    notes = []
    for u in units:
        if not u.lines:
            continue
        files[u.path] = '\n'.join(u.lines) + '\n'
        order.append(u.path)
        for line in u.lines:
            if line.startswith('[') and line.endswith(']') and re.search(
                    r'\b(?:amended|inserted|substituted|repealed|revoked|deleted|replaced|renumbered|added|'
                    r'came into force|effective)\b', line, re.I):
                notes.append((u.path, line))
    return {'files': files, 'order': order, 'notes': notes, 'pages': len(set(r.page for r in rows))}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.path.insert(0, __import__('os').path.dirname(__file__))
    from acts import ACTS
    act = next(a for a in ACTS if a['id'] == sys.argv[2]) if len(sys.argv) > 2 else {'title': sys.argv[1]}
    res = parse(sys.argv[1], act)
    for p in res['order']:
        print(f'===== {p}')
        print(res['files'][p], end='')
    print(f"== {len(res['order'])} files, {len(res['notes'])} notes", file=sys.stderr)
