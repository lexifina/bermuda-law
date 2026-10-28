"""Build the Bermuda law repository from the bermudalaws.bm PDF cache (fetch.py).

    python scripts/bermuda-law/build.py C:/Users/alany/Documents/bermuda-law --today YYYY-MM-DD [--verify-rebuild]

Bermuda Laws Online publishes the current consolidated text of each law as one PDF and keeps no earlier
consolidations, so this is a **current-only** record:

1. Each law in acts.py is one commit, `Kind: consolidated`, authored by the publisher (the Attorney-General's
   Chambers, which runs the site), dated noon Bermuda time on the day its PDF was produced (the PDF's own
   CreationDate, e.g. D:20260716145002-04'00'). That date is also the `In-force:` and `Consolidated:` trailer: the
   text is the law as amended up to that consolidation. Commits are in date order.
2. One file per section (`section-12A.md`) or schedule (`schedule-1B.md`), plus `title.md` (title and number),
   `contents.md` (the printed table of contents) and `end.md` (assent/operation dates and the "Amended by" list).
   `index.txt` lists them in printed order. One paragraph per line. The Constitution Order's own sections are in
   `constitution/order/`; the Constitution (Schedule 2 to the Order) is at `constitution/`.
3. Every history note is kept as printed (`[Section 7 amended by 2008:44 s.3 effective 23 December 2008]`) and
   parsed into data/amendments.csv (law, file, action, amending law, effective date, note). No line is credited to
   an amending law: the text before each amendment is not published.
4. Green text (the site's mark for provisions not yet in force) would go to a `future` branch; the build stops if a
   PDF has any non-black text, so it cannot slip into main unnoticed. None of the current PDFs has any.

The whole history is written by one git fast-import from sorted input with fixed dates, so the same cache always
gives the same hashes (`--verify-rebuild` builds twice into temporary folders and compares).
"""
import argparse
import datetime as dt
import io
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf

HERE = Path(__file__).parent
CACHE = HERE / '.cache'
sys.path.insert(0, str(HERE))
from acts import ACTS  # noqa: E402
from parse_pdf import parse  # noqa: E402

COMMITTER = 'Lexifina <bermuda-law@lexifina.com>'
PUBLISHER = "Attorney-General's Chambers, Bermuda (Bermuda Laws Online) <bermuda-laws-online@bermudalaws-bm.invalid>"
SITE = 'https://www.bermudalaws.bm'
MONTHS = {m: i for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
                                      'september', 'october', 'november', 'december'], 1)}
LAW_REF = re.compile(r'(UK SI\s*\d{4}\s*No\.?\s*\d+|UK SI\s*\d+\s*/\s*\d{4}|SR&O\s*\d+\s*/\s*\d{4}|'
                     r'(?:BR|GN|BX)\s*\d+\s*/\s*\d{4}|\b(?:1[89]|20)\d{2}\s*:\s*\d+\b)')
EFFECTIVE = re.compile(r'\beffective\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})')
ACTION = re.compile(r'\b(inserted|amended|substituted|repealed|revoked|deleted|replaced|renumbered|added|'
                     r'suspended|modified|transferred|brought into force|came into force|corrected)\b', re.I)


# ------------------------------------------------------------------------------------------------ dates

def nth_sunday(year: int, month: int, n: int) -> dt.date:
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(6 - d.weekday()) % 7)
    return d + dt.timedelta(days=7 * (n - 1))


def last_sunday(year: int, month: int) -> dt.date:
    d = dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def utc_offset(day: dt.date) -> int:
    """Bermuda: AST (UTC-4); daylight time UTC-3 (start <= day < end). Since 2007 the second Sunday of March to the
    first Sunday of November; 1987-2006 the first Sunday of April to the last Sunday of October; 1974-1986 the last
    Sunday of April to the last Sunday of October. Hard-coded (no tzdata here)."""
    y = day.year
    if y >= 2007:
        start, end = nth_sunday(y, 3, 2), nth_sunday(y, 11, 1)
    elif y >= 1987:
        start, end = nth_sunday(y, 4, 1), last_sunday(y, 10)
    elif y >= 1974:
        start, end = last_sunday(y, 4), last_sunday(y, 10)
    else:
        return -4
    return -3 if start <= day < end else -4


def git_date(day: str, seq: int) -> str:
    d = dt.date.fromisoformat(day)
    if d.year < 1970:
        return f'{seq} -0400'
    off = utc_offset(d)
    ts = int(dt.datetime(d.year, d.month, d.day, 12 - off, 0, tzinfo=dt.timezone.utc).timestamp())
    return f'{ts} {"-" if off < 0 else "+"}{abs(off):02d}00'


def day_of(d: str, m: str, y: str) -> str | None:
    if m.lower() not in MONTHS:
        return None
    try:
        return dt.date(int(y), MONTHS[m.lower()], int(d)).isoformat()
    except ValueError:
        return None


def pdf_info(pdf: Path) -> dict:
    doc = pymupdf.open(str(pdf))
    m = re.match(r'D:(\d{4})(\d{2})(\d{2})', doc.metadata.get('creationDate') or '')
    colours = set()
    for page in doc:
        for b in page.get_text('dict')['blocks']:
            for line in b.get('lines', []):
                for s in line['spans']:
                    if s['text'].strip():
                        colours.add(s['color'])
    return {'created': f'{m.group(1)}-{m.group(2)}-{m.group(3)}' if m else None, 'pages': doc.page_count,
            'colours': sorted(colours), 'subject': ' '.join((doc.metadata.get('subject') or '').split()),
            'producer': doc.metadata.get('creator') or ''}


# ------------------------------------------------------------------------------------------------ notes

def note_rows(act_id: str, path: str, note: str) -> list[list[str]]:
    """One row per amending law named in a history note: [law, file, action, amending law, effective, note]."""
    rows = []
    refs = list(LAW_REF.finditer(note))
    effs = list(EFFECTIVE.finditer(note))
    for k, ref in enumerate(refs):
        nxt = refs[k + 1].start() if k + 1 < len(refs) else len(note)
        eff = next((e for e in effs if ref.end() <= e.start() < nxt), None)
        if eff is None:  # "by 2005:31 s.2 and 2006:8 effective ..." : the next date after it
            eff = next((e for e in effs if e.start() >= ref.end()), None)
        before = note[:ref.start()]
        clause = before[max(before.rfind(';'), 0):]
        acts = ACTION.findall(clause) or ACTION.findall(before)
        rows.append([act_id, path, acts[-1].lower() if acts else '', ' '.join(ref.group(1).split()),
                     day_of(*eff.groups()) if eff else '', note])
    if not refs:
        rows.append([act_id, path, (ACTION.findall(note) or [''])[0].lower(), '', '', note])
    return rows


# ------------------------------------------------------------------------------------------------ build

def build_act(act: dict, today: str) -> dict:
    pdf = CACHE / f"{act['id']}.pdf"
    info = pdf_info(pdf)
    if info['colours'] != [0]:
        sys.exit(f"{act['id']}: non-black text {info['colours']} (green = not yet in force); handle it before building")
    res = parse(str(pdf), act)
    files = {f"{act['id']}/{p}": t for p, t in res['files'].items()}
    files[f"{act['id']}/index.txt"] = '\n'.join(res['order']) + '\n'
    amend = []
    for path, note in res['notes']:
        amend += note_rows(act['id'], path, note)
    listed = []
    end = res['files'].get('end.md', '')
    if '[Amended by:' in end:
        for line in end.split('[Amended by:', 1)[1].split('\n'):
            line = line.strip().rstrip(']').strip()
            if line:
                listed.append(line)
    title = res['files']['title.md'].split('\n')
    number = title[2] if len(title) > 2 else ''
    effective = sorted(r[4] for r in amend if r[4])
    day = info['created']
    if not day or day > today:
        sys.exit(f"{act['id']}: PDF creation date {day} missing or after --today")
    if effective and effective[-1] > day:
        print(f"note: {act['id']} has a history note effective {effective[-1]}, after its consolidation {day}")
    units = [p for p in res['order'] if p.rsplit('/', 1)[-1].startswith(('section-', 'schedule'))]
    return {'act': act, 'files': files, 'amend': amend, 'listed': listed, 'day': day, 'info': info,
            'number': number, 'units': len(units), 'notes': len(res['notes']), 'latest_effective':
            effective[-1] if effective else '', 'url': f"{SITE}/Laws/Consolidated%20Law/{act['year']}/"
            + act['path_title'].replace(' ', '%20')}


def message(b: dict) -> str:
    a = b['act']
    subject = f"{a['title']}: as consolidated on Bermuda Laws Online, {b['day']}"
    body = [f"The text of the {a['title']} ({b['number']}) as Bermuda Laws Online publishes it, in the consolidated",
            f"PDF produced on {b['day']}. The site keeps no earlier consolidations, so this commit holds the whole text",
            'and no line is credited to an amending law. The history notes under the sections',
            f"({b['notes']}) and the \"Amended by\" list in end.md ({len(b['listed'])} entries) are kept as printed."]
    trailers = ['Kind: consolidated', f"In-force: {b['day']}", f"Consolidated: {b['day']}", 'Date-source: pdf-created',
                f"Law: {a['title']}", f"Number: {b['number']}"]
    if b['latest_effective']:
        trailers.append(f"Latest-note-effective: {b['latest_effective']}")
    trailers.append(f"Source: {b['url']}")
    return '\n'.join([subject, '', *body, '', *trailers]) + '\n'


def fast_import(repo: Path, built: list[dict], docs: dict[str, bytes], doc_day: str, retrieved: str) -> None:
    buf = io.BytesIO()
    w = buf.write
    seq = 0
    for b in built:
        seq += 1
        when = git_date(b['day'], seq)
        msg = message(b).encode('utf-8')
        w(b'commit refs/heads/main\n')
        w(f'author {PUBLISHER} {when}\ncommitter {COMMITTER} {when}\n'.encode('utf-8'))
        w(f'data {len(msg)}\n'.encode() + msg + b'\n')
        for path, text in sorted(b['files'].items()):
            t = text.encode('utf-8')
            w(f'M 100644 inline {path}\ndata {len(t)}\n'.encode('utf-8') + t + b'\n')
        w(b'\n')
    when = git_date(doc_day, seq + 1)
    msg = (f'Documentation: README, REPRODUCE, SOURCES, corpus.json, tools and data\n\n'
           f'Built from the bermudalaws.bm PDFs retrieved on {retrieved}.\n\n'
           f'Kind: documentation\nIn-force: {doc_day}\n').encode('utf-8')
    w(b'commit refs/heads/main\n')
    w(f'author {COMMITTER} {when}\ncommitter {COMMITTER} {when}\n'.encode())
    w(f'data {len(msg)}\n'.encode() + msg + b'\n')
    for path, data in sorted(docs.items()):
        w(f'M 100644 inline {path}\ndata {len(data)}\n'.encode('utf-8') + data + b'\n')
    w(b'\n')
    r = subprocess.run(['git', '-C', str(repo), 'fast-import', '--quiet', '--force'], input=buf.getvalue(),
                       capture_output=True)
    if r.returncode:
        sys.exit(r.stderr.decode('utf-8', 'replace')[-3000:])


def build(repo: Path, today: str) -> str:
    fo = CACHE / 'fetched_on.txt'
    retrieved = fo.read_text('utf-8').strip()
    if retrieved > today:
        sys.exit(f'retrieval date {retrieved} is after --today {today}')
    built = [build_act(a, today) for a in ACTS]
    built.sort(key=lambda b: (b['day'], b['act']['id']))
    import docs as docmod
    docs = docmod.render(built, today, retrieved)
    remote = None
    if (repo / '.git').exists():
        r = subprocess.run(['git', '-C', str(repo), 'remote', 'get-url', 'origin'], capture_output=True, text=True)
        remote = r.stdout.strip() or None

        def onerr(func, path, _):
            import os
            import stat
            os.chmod(path, stat.S_IWRITE)
            func(path)
        shutil.rmtree(repo / '.git', onerror=onerr)
        for child in repo.iterdir():
            shutil.rmtree(child, onerror=onerr) if child.is_dir() else child.unlink()
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', 'init', '-q', '-b', 'main', str(repo)], check=True)
    for k, v in (('core.autocrlf', 'false'), ('core.longpaths', 'true')):
        subprocess.run(['git', '-C', str(repo), 'config', k, v], check=True)
    if remote:
        subprocess.run(['git', '-C', str(repo), 'remote', 'add', 'origin', remote], check=True)
    fast_import(repo, built, docs, retrieved, retrieved)
    subprocess.run(['git', '-C', str(repo), 'checkout', '-q', '-f', 'main'], check=True)
    head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    n = subprocess.run(['git', '-C', str(repo), 'rev-list', '--count', 'HEAD'], capture_output=True, text=True).stdout.strip()
    print(f'built {repo}: {n} commits, head {head}', flush=True)
    return head


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('repo', type=Path)
    ap.add_argument('--today', required=True)
    ap.add_argument('--verify-rebuild', action='store_true')
    args = ap.parse_args()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', args.today):
        sys.exit('--today must be YYYY-MM-DD')
    if args.verify_rebuild:
        heads = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                heads.append(build(Path(tmp) / 'r', args.today))
        print('rebuild identical' if heads[0] == heads[1] else f'REBUILD DIFFERS {heads}')
        sys.exit(0 if heads[0] == heads[1] else 1)
    build(args.repo, args.today)


if __name__ == '__main__':
    main()
