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
                      r'NINTH|TENTH)\s+SCHEDULE\b|SCHEDULE$)')
END_MATTER = re.compile(r'^\[(?:Assent Date:|Operative Date:|This (?:Act|Order) was brought into operation|Amended by:)')
SOFT = re.compile('[­​﻿]')
SPACES = re.compile(r'[\s     ]+')


def norm(s: str) -> str:
    return SPACES.sub(' ', SOFT.sub('', unicodedata.normalize('NFC', s))).strip()


class Frag:
    __slots__ = ('x0', 'x1', 'y', 'text', 'size', 'bold', 'italic', 'font')

    def __init__(self, line: dict):
        spans = [s for s in line['spans'] if s['text']]
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
        return self.x0 > 112 and abs((self.x0 + self.x1) / 2 - 306) < 16 and self.label() is None


def rows_of(pdf_path: str, title: str) -> list[Row]:
    doc = fitz.open(pdf_path)
    out: list[Row] = []
    tnorm = norm(title).upper()
    for pno, page in enumerate(doc):
        frags = []
        for b in page.get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE)['blocks']:
            for line in b.get('lines', []):
                f = Frag(line)
                if not f.text.strip():
                    continue
                if pno == 0 and f.size <= 7.5 and f.y < 220:
                    continue  # the crest's letters ("QUO FATA FERUNT")
                if pno > 0 and f.y < 125 and f.bold and norm(f.text).upper() == tnorm:
                    continue  # running header: the title
                if f.y > 670 and f.bold and re.fullmatch(r'\d{1,4}', norm(f.text)):
                    continue  # page number
                frags.append(f)
        frags.sort(key=lambda f: (round(f.y, 1), f.x0))
        group: list[Frag] = []
        for f in frags:
            if group and abs(f.y - group[0].y) > 2.0:
                out.append(Row(pno, group))
                group = []
            group.append(f)
        if group:
            out.append(Row(pno, group))
    return out


def schedule_id(text: str) -> str | None:
    m = SCHEDULE.match(text)
    if not m:
        return None
    if m.group(1):
        return m.group(1)
    if m.group(2):
        return ORDINALS[m.group(2)]
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


def parse(pdf_path: str, act: dict) -> dict:
    """{'files': {relative path: text}, 'order': [relative paths in printed order], 'notes': [(file, note)]}."""
    rows = rows_of(pdf_path, act['title'])
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
            p = path(f'{name}~{k}')
            k += 1
        cur = Unit(p, pending)
        pending = []
        units.append(cur)
        return cur

    front = start('title.md')
    i = 0
    prev: Row | None = None
    while i < len(rows):
        r = rows[i]
        t = r.text
        if mode == 'front':
            if t == 'TABLE OF CONTENTS':
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
        if r.bold and r.size >= 9 and r.x0 < 115 and not in_schedule:
            # a section heading: one or more bold rows, then the section number on the next row
            head = [r]
            j = i + 1
            while j < len(rows) and rows[j].bold and rows[j].x0 < 115 and rows[j].page == head[-1].page \
                    and rows[j].y - head[-1].y < 13:
                head.append(rows[j])
                j += 1
            nxt = rows[j] if j < len(rows) else None
            num = norm(nxt.frags[0].text) if nxt is not None else ''
            if nxt is not None and SECNUM.match(num) and abs(nxt.frags[0].x0 - 108) < 4:
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
                    or (r.page != prev.page and (prev.x1 < 495 or t.startswith('“')))
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
