"""Append a fresh build (build.py into a scratch repository) to the published main, without rewriting it.

    python scripts/bermuda-law/append.py SCRATCH_REPO TARGET_REPO [--push]

main on GitHub is append-only. build.py writes the whole history from scratch in flat `<id>/` folders; this script
adds to TARGET's origin/main, by one git fast-import with `from <tip>`:

1. once, a pure-rename commit moving the first layout (act/<year>/<short title>/, constitution/constitution/) to
   the type/year layout of STRUCTURE.md (acts/<year>/<number>-<short title>/, constitution/);
2. one commit per law whose files differ from what main holds at its folder, in consolidation-day order, with the
   scratch commit's message, date (noon Bermuda time on the PDF's production day) and these trailers added:
   In-force-basis, Law-id, Path; the author is the last amending law in the law's "Amended by" list (the law itself
   when it lists none);
3. a data commit: data/ tables, laws.csv with the new folders, data/paths.json, corpus.json counts.

Blobs are taken from the scratch repository (fetched into refs/scratch/main), so nothing is re-parsed.
"""
import argparse
import csv
import io
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / '.cache'
COMMITTER = 'Lexifina <bermuda-law@lexifina.com>'
NOWIN = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def git(repo, *a, input=None, check=True) -> str:
    r = subprocess.run(['git', '-C', str(repo), *a], input=input, capture_output=True, creationflags=NOWIN)
    if check and r.returncode:
        sys.exit(f"git {' '.join(a)}: {r.stderr.decode('utf-8', 'replace')[-2000:]}")
    return r.stdout.decode('utf-8', 'replace')


def tree(repo, rev) -> dict[str, str]:
    out = {}
    for line in git(repo, 'ls-tree', '-r', '-z', rev).split('\0'):
        if line:
            meta, path = line.split('\t', 1)
            out[path] = meta.split()[2]
    return out


def short(title: str, kind: str) -> tuple[str, str]:
    """(year, slug without the trailing 'act <year>' / '<year>')."""
    t = ' '.join(title.split())
    m = re.search(r'\b(1[6-9]\d\d|20\d\d)\s*(\(\d+\))?$', t)
    year = m.group(1) if m else ''
    s = re.sub(r'[^a-z0-9]+', '-', t.lower().replace('&', ' and ')).strip('-')
    if year:
        s = re.sub(rf'-(act-)?{year}(-\d+)?$', '', s) if kind == 'acts' else re.sub(rf'-{year}(-\d+)?$', '', s)
    if len(s) > 70:
        s = s[:70].rstrip('-')
    return year, s or 'law'


def number_of(num: str, kind: str) -> str:
    n = ' '.join(num.split())
    m = re.fullmatch(r'(1[6-9]\d\d|20\d\d)\s*:\s*(\d+)', n)
    if m:
        return m.group(2)
    m = re.fullmatch(r'(BR|GN|BX|SR&O)\s*(\d+)\s*/\s*(\d{4})', n, re.I)
    if m:
        return f"{m.group(1).lower().replace('&', '')}-{m.group(2)}"
    return ''


def layout(laws: list[dict], status: dict) -> dict[str, str]:
    """id -> folder."""
    out, used = {}, set()
    for r in sorted(laws, key=lambda r: r['id']):
        i = r['id']
        if i == 'constitution':
            out[i] = 'constitution'
            continue
        subj = (status.get(i) or {}).get('subject', '')
        title = r['title']
        if subj == 'Regulation - Statutory Instruments':
            kind = 'statutory-instruments'
        elif subj == 'Statute' or re.search(r'\bAct(\s+\d{4})?(\s*\(\d+\))?$', title.strip()):
            kind = 'acts'
        else:
            kind = 'statutory-instruments'
        year, s = short(title, kind)
        if not year:
            y = r.get('year', '')
            year = y if re.fullmatch(r'\d{4}', y) else 'undated'
        num = number_of(r['number'], kind)
        base = f"{kind}/{year}/{num + '-' if num else ''}{s}"
        p, k = base, 2
        while p in used:
            p, k = f'{base}-{k}', k + 1
        used.add(p)
        out[i] = p
    return out


def inforce_line(T, tip) -> str:
    d = git(T, 'log', '-1', '--format=%(trailers:key=In-force,valueonly,separator=)', '--grep=^In-force: [0-9]', tip).strip()
    return f'In-force: {d}\n' if d else ''


def author_for(listed: list[str], title: str) -> str:
    if listed:
        last = ' '.join(listed[-1].split())
        return f'{last} (latest amending law listed) <amending-law@bermudalaws-bm.invalid>'
    return f'{title} (as enacted, no amendment listed) <enacted-law@bermudalaws-bm.invalid>'


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('scratch', type=Path)
    ap.add_argument('target', type=Path)
    ap.add_argument('--push', action='store_true')
    args = ap.parse_args()
    S, T = args.scratch, args.target
    git(T, 'fetch', '-q', 'origin', 'main')
    git(T, 'fetch', '-q', '--no-tags', str(S.resolve()), '+main:refs/scratch/main')
    tip = git(T, 'rev-parse', 'origin/main').strip()
    cur = tree(T, tip)
    stip = git(T, 'rev-parse', 'refs/scratch/main').strip()
    stree = tree(T, stip)
    laws_rows = list(csv.DictReader(io.StringIO(git(T, 'show', f'{stip}:laws.csv'))))
    for r in laws_rows:
        r['id'] = r['folder'].rstrip('/').split('/')[0]
    cat = {}
    cj = CACHE / 'catalogue.json'
    status = json.loads((CACHE / 'status.json').read_text('utf-8'))
    for a in json.loads(cj.read_text('utf-8'))['laws']:
        cat[a['url']] = a['year']
    for r in laws_rows:
        src = r['source'].replace('%20', ' ')
        r['year'] = cat.get(src, '')
    paths = layout(laws_rows, status)
    amended = {}
    for row in csv.DictReader(io.StringIO(git(T, 'show', f'{stip}:data/amended-by.csv'))):
        amended.setdefault(row['law'], []).append((int(row['position']), row['amending_law']))
    title_of = {r['id']: r['title'] for r in laws_rows}

    buf = io.BytesIO()
    w = buf.write
    parent = tip
    n_commits = 0
    last_day = ''
    old_paths = json.loads(git(T, 'show', f'{tip}:data/paths.json'))['paths'] if 'data/paths.json' in cur else {}

    # 1. pure rename of the first layout
    if any(p.startswith('act/') or p.startswith('constitution/constitution/') for p in cur):
        missing = [i for i in old_paths if i not in paths]
        if missing:
            sys.exit(f'first-layout laws not built yet: {missing}')
        moves = {}
        for i, old in old_paths.items():
            new = paths.get(i, 'constitution' if i == 'constitution' else None)
            if new is None:
                continue
            for p in cur:
                if p.startswith(old + '/'):
                    moves[p] = new + p[len(old):]
        msg = ('Layout: acts/<year>/<number>-<short title>/ and constitution/ (pure rename)\n\n'
               'The type/year layout of STRUCTURE.md, ready for every consolidated law on Bermuda Laws Online.\n'
               'Renames only: no file content changes in this commit.\n\nKind: layout\n' + inforce_line(T, tip)).encode()
        when = git(T, 'log', '-1', '--format=%ct %cd', '--date=format:%z', tip).strip()
        w(b'commit refs/heads/append-staging\n')
        w(f'author {COMMITTER} {when}\ncommitter {COMMITTER} {when}\n'.encode())
        w(f'data {len(msg)}\n'.encode() + msg + b'\nfrom ' + tip.encode() + b'\n')
        for old, new in sorted(moves.items()):
            w(f'D {old}\nM 100644 {cur[old]} {new}\n'.encode('utf-8'))
            cur[new] = cur.pop(old)
        w(b'\n')
        parent = None
        n_commits += 1

    # 2. one commit per law that differs
    log = git(T, 'log', '--reverse', '--format=%H%x01%an <%ae>%x01%at %ad%x01%B%x02', '--date=format:%z', stip)
    for ent in log.split('\x02'):
        ent = ent.strip('\n')
        if not ent:
            continue
        h, au, when, body = ent.split('\x01', 3)
        if 'Kind: consolidated' not in body:
            continue
        files = git(T, 'diff-tree', '--no-commit-id', '--name-only', '-r', '--root', h).split()
        ids = {f.split('/')[0] for f in files}
        if len(ids) != 1:
            continue
        i = ids.pop()
        dest = paths.get(i)
        if not dest:
            continue
        new = {dest + p[len(i):]: sha for p, sha in stree.items() if p.startswith(i + '/')}
        have = {p: s for p, s in cur.items() if p.startswith(dest + '/')}
        if new == have:
            continue
        listed = [a for _, a in sorted(amended.get(i, []))]
        author = author_for(listed, title_of.get(i, i))
        day = re.search(r'^In-force: (\S+)', body, re.M).group(1)
        last_day = max(last_day, day)
        lines = body.rstrip('\n').split('\n')
        if have:  # a later consolidation of a law main already holds: the commit is the diff
            blank = [k for k, ln in enumerate(lines) if not ln.strip()]
            if len(blank) >= 2:
                lines[blank[0] + 1:blank[1]] = [
                    'A later consolidation of a law this record already holds: the diff shows what changed since the',
                    'previous PDF. Changes are not credited line by line; the history notes and the "Amended by" list',
                    'name the amending laws and the days they took effect.']
        extra = [f'In-force-basis: consolidation day (the PDF CreationDate): the law as amended up to {day}',
                 'Author-basis: ' + ('last entry of the law Amended by list' if listed else 'no Amended by list'),
                 f'Law-id: {i}', f'Path: {dest}/']
        msg = ('\n'.join(lines + extra) + '\n').encode('utf-8')
        w(b'commit refs/heads/append-staging\n')
        w(f'author {author} {when}\ncommitter {COMMITTER} {when}\n'.encode('utf-8'))
        w(f'data {len(msg)}\n'.encode() + msg + b'\n')
        if parent:
            w(b'from ' + parent.encode() + b'\n')
            parent = None
        for p in sorted(set(have) - set(new)):
            w(f'D {p}\n'.encode('utf-8'))
            del cur[p]
        for p, sha in sorted(new.items()):
            if have.get(p) != sha:
                w(f'M 100644 {sha} {p}\n'.encode('utf-8'))
                cur[p] = sha
        w(b'\n')
        n_commits += 1

    if n_commits == 0:
        print('nothing new', flush=True)
        return

    # 3. data commit
    dirs = {p.rsplit('/', k)[0] for p in cur for k in range(1, p.count('/') + 1)}
    held = {i: paths[i] for i in paths if paths[i] in dirs}
    data = {}
    for p in ('data/amendments.csv', 'data/amended-by.csv', 'data/catalogue.csv', 'data/source-sha256.tsv',
              'data/unreadable.csv'):
        if p in stree:
            data[p] = git(T, 'show', f'{stip}:{p}').encode('utf-8')
    out = io.StringIO()
    wr = csv.writer(out, lineterminator='\n')
    hdr = ['title', 'number', 'folder', 'consolidated', 'files', 'history_notes', 'amended_by_entries',
           'latest_note_effective', 'pdf_pages', 'source']
    wr.writerow(hdr)
    for r in sorted(laws_rows, key=lambda r: held.get(r['id'], '~')):
        if r['id'] in held:
            r2 = dict(r, folder=held[r['id']] + '/')
            wr.writerow([r2[k] for k in hdr])
    data['laws.csv'] = out.getvalue().encode('utf-8')
    data['data/paths.json'] = (json.dumps({'layout': 'acts|statutory-instruments/<year>/<number>-<short title>',
                                           'since': '2026-11-26',
                                           'note': 'Each law id (its first flat folder name) to its folder.',
                                           'paths': dict(sorted(held.items()))}, indent=1, ensure_ascii=False)
                               + '\n').encode('utf-8')
    corpus = json.loads(git(T, 'show', f'{tip}:corpus.json'))
    days = sorted(r['consolidated'] for r in laws_rows if r['id'] in held and r['consolidated'])
    corpus['name'] = 'Laws of Bermuda (consolidated laws from Bermuda Laws Online)'
    corpus['acts'] = len(held)
    if days:
        corpus['history_from'], corpus['record_to'] = days[0], days[-1]
    corpus['citation']['file'] = r'^((?:acts|statutory-instruments)/[^/]+/[a-z0-9-]+|constitution)/section-([0-9]+[A-Z]*)\.md$'
    corpus['author']['consolidated'] = 'the last amending law in the law\'s "Amended by" list (else the law itself)'
    data['corpus.json'] = (json.dumps(corpus, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    when = git(T, 'log', '-1', '--format=%ct %cd', '--date=format:%z', tip).strip()
    msg = (f'Data: laws.csv, data/paths.json, corpus.json and the data tables for {len(held)} laws\n\n'
           'Kind: documentation\n' + (f'In-force: {last_day}\n' if last_day else inforce_line(T, tip))).encode()
    w(b'commit refs/heads/append-staging\n')
    w(f'author {COMMITTER} {when}\ncommitter {COMMITTER} {when}\n'.encode())
    w(f'data {len(msg)}\n'.encode() + msg + b'\n')
    if parent:
        w(b'from ' + parent.encode() + b'\n')
    for p, d in sorted(data.items()):
        w(f'M 100644 inline {p}\ndata {len(d)}\n'.encode('utf-8') + d + b'\n')
    w(b'\n')
    git(T, 'update-ref', 'refs/heads/append-staging', tip)
    r = subprocess.run(['git', '-C', str(T), 'fast-import', '--quiet'],
                       input=buf.getvalue(),
                       capture_output=True, creationflags=NOWIN)
    if r.returncode:
        sys.exit(r.stderr.decode('utf-8', 'replace')[-3000:])
    head = git(T, 'rev-parse', 'append-staging').strip()
    if git(T, 'merge-base', tip, head).strip() != tip:
        sys.exit('not a fast-forward')
    print(f'{n_commits + 1} commits on top of {tip[:10]}: {head[:10]}; {len(held)} laws held', flush=True)
    if args.push:
        git(T, 'push', '-q', 'origin', f'{head}:refs/heads/main')
        remote = git(T, 'ls-remote', 'origin', 'refs/heads/main').split()[0]
        print(f'pushed {head[:10]}; ls-remote {remote[:10]} {"OK" if remote == head else "MISMATCH"}', flush=True)


if __name__ == '__main__':
    main()
