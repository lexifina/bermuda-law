"""Detached runner: fetch every consolidated PDF, build into a scratch repository, append to main and push.

    pythonw scripts/bermuda-law/runner.py   (started detached, CREATE_NO_WINDOW, below-normal priority)

Writes progress.log next to this file. One build/push at a time: the first as soon as the core laws are cached
(about 5 minutes in), then every 15 minutes while fetch_fast.py runs, then a final one; then catalogue.py looks for
laws added since the seed catalogue, and any new ones are fetched, built and pushed. Stops on a block (exit 3).
"""
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / '.cache'
LOG = HERE / 'progress.log'
SCRATCH = Path(r'C:\Users\alany\Documents\bermuda-law-build')
TARGET = Path(r'C:\Users\alany\Documents\bermuda-law')
TODAY = datetime.date.today().isoformat()
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0)
PY = sys.executable.replace('pythonw.exe', 'python.exe')
CORE_IDS = ('criminal-code-act-1907', 'companies-act-1981', 'interpretation-act-1951', 'constitution',
            'motor-car-act-1951', 'employment-act-2000', 'human-rights-act-1981',
            'bermuda-immigration-and-protection-act-1956')


def log(msg: str) -> None:
    with LOG.open('a', encoding='utf-8') as f:
        f.write(f'{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n')


def run(args: list[str], name: str) -> int:
    log(f'start {name}')
    with LOG.open('a', encoding='utf-8') as f:
        r = subprocess.run([PY, *args], stdout=f, stderr=subprocess.STDOUT, creationflags=FLAGS, cwd=str(HERE))
    log(f'end {name}: exit {r.returncode}')
    return r.returncode


def build_and_push() -> None:
    if run([str(HERE / 'build.py'), str(SCRATCH), '--today', TODAY], 'build') == 0:
        run([str(HERE / 'append.py'), str(SCRATCH), str(TARGET), '--push'], 'append+push')


def core_ready() -> bool:
    try:
        st = json.loads((CACHE / 'status.json').read_text('utf-8'))
    except (OSError, ValueError):
        return False
    return all(i in st for i in CORE_IDS)


def fetch_cycle(extra: list[str]) -> int:
    with LOG.open('a', encoding='utf-8') as f:
        p = subprocess.Popen([PY, str(HERE / 'fetch_fast.py'), *extra], stdout=f, stderr=subprocess.STDOUT,
                             creationflags=FLAGS, cwd=str(HERE))
    log(f'fetch pid {p.pid}')
    first, last_build = True, time.time()
    while p.poll() is None:
        time.sleep(20)
        if first and (core_ready() or time.time() - last_build > 600) or not first and time.time() - last_build > 900:
            first = False
            build_and_push()
            last_build = time.time()
    log(f'fetch exit {p.returncode}')
    return p.returncode


def main() -> None:
    log(f'runner pid {os.getpid()}')
    rc = fetch_cycle(['--seed', str(CACHE / 'catalogue_seed.csv')])
    if rc == 3:
        log('BLOCKED: stopping')
        return
    fetch_cycle([])  # retry transients
    build_and_push()
    # laws added since the seed: the search catalogue (2 s apart), then fetch, build, push
    if run([str(HERE / 'catalogue.py')], 'catalogue') == 0:
        if fetch_cycle([]) == 3:
            log('BLOCKED: stopping')
            return
        build_and_push()
    log('runner done')


if __name__ == '__main__':
    main()
