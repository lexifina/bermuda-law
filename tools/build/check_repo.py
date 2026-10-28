"""Structural checks of the built Bermuda repo. Standard library only.

    python scripts/bermuda-law/check_repo.py <repo> --today YYYY-MM-DD

- every commit has `In-force: YYYY-MM-DD`; every law commit `Kind: consolidated` and a `.invalid` author email;
- in-force dates never go backwards on main and none is after --today; no merges; no CR in any message or file;
- every file listed in each law's index.txt exists and every law file is listed;
- tools/in_force_on.py prints, for every 7th section or schedule file, exactly the stored file on the consolidation day,
  and refuses the day before.
"""
import re
import subprocess
import sys
from pathlib import Path


def git(repo, *a, binary=False):
    r = subprocess.run(['git', '-C', str(repo), *a], capture_output=True)
    if r.returncode:
        sys.exit(r.stderr.decode())
    return r.stdout if binary else r.stdout.decode('utf-8')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    repo = Path(sys.argv[1])
    today = sys.argv[sys.argv.index('--today') + 1]
    bad = []
    log = git(repo, 'log', '--first-parent', '--reverse', '--format=%H%x1f%ae%x1f%P%x1f%B%x1e', 'main')
    last = ''
    if '\r' in log:
        bad.append('carriage return in a commit message')
    commits = [c.strip('\n').split('\x1f') for c in log.split('\x1e') if c.strip()]
    for h, email, parents, body in commits:
        if len(parents.split()) > 1:
            bad.append(f'{h[:7]} is a merge')
        m = re.search(r'^In-force: (\d{4}-\d{2}-\d{2})$', body, re.M)
        if not m:
            bad.append(f'{h[:7]} has no In-force')
            continue
        doc = 'Kind: documentation' in body
        if not doc:
            if 'Kind: consolidated' not in body or not email.endswith('.invalid'):
                bad.append(f'{h[:7]} law commit lacks Kind: consolidated or a .invalid author')
            if m.group(1) < last:
                bad.append(f'{h[:7]} goes back in time')
            last = m.group(1)
        if m.group(1) > today:
            bad.append(f'{h[:7]} is dated after {today}')
    files = git(repo, 'ls-tree', '-r', '--name-only', 'main').split('\n')
    laws = sorted({f.split('/')[0] for f in files if f.endswith('/index.txt') and f.count('/') == 1})
    checked = 0
    for law in laws:
        listed = [l for l in git(repo, 'show', f'main:{law}/index.txt').split('\n') if l]
        have = sorted(f[len(law) + 1:] for f in files if f.startswith(law + '/') and not f.endswith('/index.txt'))
        if sorted(listed) != have:
            bad.append(f'{law}: index.txt and the files differ')
        day = re.search(r'^In-force: (\S+)', git(repo, 'log', '-1', '--format=%B', 'main', '--', law), re.M).group(1)
        before = subprocess.run(['git', '-C', str(repo), 'log', '-1', '--format=%cs', 'main', '--', law],
                                capture_output=True, text=True).stdout.strip()
        import datetime as dt
        prev_day = (dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat()
        for name in listed:
            blob = git(repo, 'show', f'main:{law}/{name}', binary=True)
            if b'\r' in blob:
                bad.append(f'{law}/{name} has a CR')
            if not name.startswith(('section-', 'schedule', 'order/section-', 'order/schedule')) or checked % 7:
                checked += 1
                continue
            checked += 1
            out = subprocess.run([sys.executable, '-X', 'utf8', 'tools/in_force_on.py', day, law, name], cwd=repo,
                                 capture_output=True).stdout
            if out != blob:
                bad.append(f'on-date tool differs for {law}/{name} on {day}')
            r = subprocess.run([sys.executable, '-X', 'utf8', 'tools/in_force_on.py', prev_day, law, name], cwd=repo,
                               capture_output=True)
            if r.returncode == 0:
                bad.append(f'on-date tool gave a version of {law}/{name} on {prev_day}, before the record starts')
    for b in bad:
        print('FAIL', b)
    print(f'{len(commits)} commits, {len(laws)} laws, {checked} files; ' + ('OK' if not bad else f'{len(bad)} problems'))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
