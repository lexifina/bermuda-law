"""Push a work-in-progress snapshot of scripts/bermuda-law (wip/ folder, no cache) to the `wip` branch.

    python scripts/bermuda-law/push_wip.py <repo> [--tree-from main]

With --tree-from REF the snapshot also carries that ref's tree (the current build), with the scripts under wip/.
Each call adds one commit on top of origin/wip (or starts it), then pushes and checks ls-remote.
"""
import datetime
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
repo = sys.argv[1]
tree_from = sys.argv[sys.argv.index('--tree-from') + 1] if '--tree-from' in sys.argv else None


def git(*a, inp=None, env=None):
    r = subprocess.run(['git', '-C', repo, *a], input=inp, capture_output=True, env=env)
    if r.returncode:
        sys.exit(r.stderr.decode())
    return r.stdout.decode().strip()


import os
idx = os.path.join(repo, '.git', 'wip-index')
env = dict(os.environ, GIT_INDEX_FILE=idx)
if os.path.exists(idx):
    os.remove(idx)
if tree_from:
    git('read-tree', tree_from, env=env)
for f in sorted(HERE.iterdir()):
    if f.is_file() and f.suffix in ('.py', '.md', '.json') or f.name == '.gitignore':
        data = f.read_bytes().replace(b'\r\n', b'\n')
        blob = git('hash-object', '-w', '--stdin', inp=data)
        git('update-index', '--add', '--cacheinfo', f'100644,{blob},wip/{f.name}', env=env)
tree = git('write-tree', env=env)
os.remove(idx)
subprocess.run(['git', '-C', repo, 'fetch', '-q', 'origin', 'wip'], capture_output=True)
parent = subprocess.run(['git', '-C', repo, 'rev-parse', '-q', '--verify', 'origin/wip'], capture_output=True,
                        text=True).stdout.strip()
now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
msg = f'Work in progress: scripts/bermuda-law at {now}\n\nKind: documentation\nIn-force: {now[:10]}\n'.encode()
e2 = dict(os.environ, GIT_AUTHOR_NAME='Lexifina', GIT_AUTHOR_EMAIL='bermuda-law@lexifina.com',
          GIT_COMMITTER_NAME='Lexifina', GIT_COMMITTER_EMAIL='bermuda-law@lexifina.com')
args = ['commit-tree', tree] + (['-p', parent] if parent else [])
c = git(*args, inp=msg, env=e2)
git('push', '-q', 'origin', f'{c}:refs/heads/wip')
remote = git('ls-remote', 'origin', 'wip').split()[0]
print('wip', c[:7], 'remote', remote[:7], 'OK' if remote == c else 'MISMATCH')
