"""Structural and date-query gate for the Bermuda own-builder repository.

    python -X utf8 check_repo.py <repo> --today YYYY-MM-DD

Checks every commit and law file, and every seventh section or schedule against the
date reader at each version boundary. Corrections append metadata or source text.
"""
import csv
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path


def run(repo, *args, input_bytes=None):
    result = subprocess.run(['git', '-C', str(repo), *args], input=input_bytes, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', 'replace'))
    return result.stdout


def text(repo, *args):
    return run(repo, *args).decode('utf-8')


def batch_blobs(repo, specs):
    """Read immutable Git blobs in one process, with the same bytes as git show."""
    if not specs:
        return {}
    response = run(repo, 'cat-file', '--batch', input_bytes=('\n'.join(specs) + '\n').encode('utf-8'))
    pos, out = 0, {}
    for spec in specs:
        end = response.index(b'\n', pos)
        header = response[pos:end].split()
        pos = end + 1
        if len(header) < 3 or header[1] == b'missing':
            raise ValueError(f'missing blob: {spec}')
        size = int(header[2])
        out[spec] = response[pos:pos + size]
        pos += size + 1
    return out


def date_before(day):
    return (dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat()


def reader(repo, day, law, name):
    return subprocess.run([sys.executable, '-X', 'utf8', 'tools/in_force_on.py', day, law, name],
                          cwd=repo, capture_output=True)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    repo = Path(sys.argv[1]).resolve()
    today = sys.argv[sys.argv.index('--today') + 1]
    bad = []
    log = text(repo, 'log', '--first-parent', '--reverse', '--format=%H%x1f%ae%x1f%P%x1f%B%x1e', 'main')
    if '\r' in log:
        bad.append('carriage return in a commit message')
    commits = [c.strip('\n').split('\x1f') for c in log.split('\x1e') if c.strip()]
    messages = {h: body for h, _, _, body in commits}
    paths = text(repo, 'ls-tree', '-r', '--name-only', 'main').splitlines()
    law_folders = sorted({p.split('/')[0] for p in paths if p.endswith('/index.txt') and p.count('/') == 1})
    last = ''
    corrections = []
    for h, email, parents, body in commits:
        if len(parents.split()) > 1:
            bad.append(f'{h[:7]} is a merge')
        dates = re.findall(r'^In-force: (\d{4}-\d{2}-\d{2})$', body, re.M)
        if len(dates) != 1:
            bad.append(f'{h[:7]} has {len(dates)} In-force trailers')
            continue
        day = dates[0]
        try:
            dt.date.fromisoformat(day)
        except ValueError:
            bad.append(f'{h[:7]} invalid In-force date {day}')
        kinds = re.findall(r'^Kind: (\S+)$', body, re.M)
        if len(kinds) != 1 or kinds[0] not in ('consolidated', 'documentation', 'correction'):
            bad.append(f'{h[:7]} invalid Kind trailer')
            continue
        kind = kinds[0]
        if kind == 'consolidated':
            if not email.endswith('.invalid'):
                bad.append(f'{h[:7]} consolidated author is not publisher .invalid')
            if day < last:
                bad.append(f'{h[:7]} goes back in time')
            last = day
            if 'Date-source: source-amendment-note' in body and not re.search(r'^In-force-basis: \S', body, re.M):
                bad.append(f'{h[:7]} source-dated version lacks In-force-basis')
        elif kind == 'correction':
            corrections.append(h)
            for trailer in ('In-force-basis', 'Reason', 'Supersedes', 'Files'):
                if not re.search(rf'^{trailer}: \S', body, re.M):
                    bad.append(f'{h[:7]} correction lacks {trailer}')
            corrected = re.findall(r'^Corrects: ([0-9a-f]{40})$', body, re.M)
            if not corrected or len(corrected) != len(set(corrected)):
                bad.append(f'{h[:7]} invalid Corrects list')
            changed = set(text(repo, 'diff-tree', '--no-commit-id', '--name-only', '-r', h).splitlines())
            named = set(re.search(r'^Files: (.+)$', body, re.M).group(1).split(', ')) if re.search(r'^Files: (.+)$', body, re.M) else set()
            if changed != named:
                bad.append(f'{h[:7]} correction Files mismatch')
            law_changes = {p for p in changed if p.split('/')[0] in law_folders}
            if law_changes:
                act_paths = re.findall(r'^Act-path: (\S+)$', body, re.M)
                if len(act_paths) != 1 or act_paths[0] not in law_folders or any(
                        not p.startswith(act_paths[0] + '/') for p in law_changes):
                    bad.append(f'{h[:7]} correction law files differ from Act-path')
            for original in corrected:
                if original not in messages or text(repo, 'merge-base', original, h).strip() != original:
                    bad.append(f'{h[:7]} Corrects is not an existing ancestor: {original}')
            if email != 'bermuda-law@lexifina.com':
                bad.append(f'{h[:7]} correction author identity')
        if day > today:
            bad.append(f'{h[:7]} is dated after {today}')

    correction_file = repo / 'data' / 'date-corrections.tsv'
    overrides = {}
    if correction_file.exists():
        with correction_file.open(encoding='utf-8', newline='') as f:
            rows = list(csv.DictReader(f, delimiter='\t'))
        for row in rows:
            h = row['original_commit']
            old, new = row['published_in_force'], row['corrected_in_force']
            if h in overrides or h not in messages:
                bad.append(f'date-corrections: duplicate or unknown {h}')
                continue
            if f'In-force: {old}' not in messages[h] or not row['in_force_basis'].strip():
                bad.append(f'date-corrections: missing source basis or mismatched old date for {h[:7]}')
            try:
                dt.date.fromisoformat(new)
            except ValueError:
                bad.append(f'date-corrections: invalid date for {h[:7]}')
            if not re.fullmatch('[0-9a-f]{64}', row['source_pdf_sha256']):
                bad.append(f'date-corrections: invalid source hash for {h[:7]}')
            overrides[h] = new
        metadata_corrections = [c for c in corrections if not re.search(r'^Act-path: ', messages[c], re.M)]
        named = {h for c in metadata_corrections for h in re.findall(r'^Corrects: ([0-9a-f]{40})$', messages[c], re.M)}
        if set(overrides) != named:
            bad.append('date-corrections rows differ from correction Corrects trailers')

    checked = 0
    samples = []
    specs = []
    for law in law_folders:
        index = text(repo, 'show', f'main:{law}/index.txt').splitlines()
        have = sorted(p[len(law) + 1:] for p in paths if p.startswith(law + '/') and p != law + '/index.txt')
        if sorted(index) != have:
            bad.append(f'{law}: index.txt and files differ')
        for name in index:
            spec = f'main:{law}/{name}'
            specs.append(spec)
            if name.startswith(('section-', 'schedule', 'order/section-', 'order/schedule')) and checked % 7 == 0:
                history = text(repo, 'log', '--first-parent', '--format=%H%x1f%(trailers:key=In-force,valueonly,separator=)%x1f%(trailers:key=Consolidated,valueonly,separator=)',
                               'main', '--', f'{law}/{name}')
                versions = []
                for line in history.splitlines():
                    h, in_force, consolidated = (line.split('\x1f') + ['', ''])[:3]
                    day = overrides.get(h) or (in_force or consolidated).strip()
                    if day:
                        versions.append((h, day))
                        specs.append(f'{h}:{law}/{name}')
                if not versions:
                    bad.append(f'{law}/{name}: no dated history')
                else:
                    samples.append((law, name, versions))
            checked += 1
    blobs = batch_blobs(repo, list(dict.fromkeys(specs)))
    for spec in (f'main:{p}' for p in paths if p.endswith('/index.txt') is False and p.split('/')[0] in law_folders):
        if spec in blobs and b'\r' in blobs[spec]:
            bad.append(f'{spec[5:]} has a CR')
    for law, name, versions in samples:
        for i, (h, day) in enumerate(versions):
            wanted = blobs[f'{h}:{law}/{name}']
            got = reader(repo, day, law, name)
            if got.returncode or got.stdout != wanted:
                bad.append(f'on-date tool differs for {law}/{name} at {day}')
            before = reader(repo, date_before(day), law, name)
            if i + 1 < len(versions):
                prior = blobs[f'{versions[i + 1][0]}:{law}/{name}']
                if before.returncode or before.stdout != prior:
                    bad.append(f'on-date tool differs for prior {law}/{name} before {day}')
            elif before.returncode == 0:
                bad.append(f'on-date tool gave {law}/{name} before first source date {day}')
        if blobs[f'main:{law}/{name}'] != blobs[f'{versions[0][0]}:{law}/{name}']:
            bad.append(f'latest blob differs for {law}/{name}')
    for problem in bad:
        print('FAIL', problem)
    print(f'{len(commits)} commits, {len(law_folders)} laws, {checked} files, {len(samples)} sampled paths; '
          + ('OK' if not bad else f'{len(bad)} problems'))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
