"""Fetch every consolidated PDF in the catalogue, ramping from 1 request in flight towards 5.

    python scripts/bermuda-law/fetch_fast.py [--seed CSV] [--refresh] [--max-inflight 5]

--seed builds .cache/catalogue.json from a data/catalogue.csv of an earlier build (no search pages needed).
Same cache format as fetch.py (.cache/<id>.pdf, .cache/status.json). Starts at one request in flight, about 1 s
apart; after every 60 clean answers in a row one more is allowed, up to --max-inflight. A timeout or 5xx drops it
back to 1 and pauses 60 s; a 429 or 503 pauses 5 minutes; a 403 or a challenge page stops the run (exit 3).
Core laws are fetched first. Progress lines go to stdout (the runner sends them to progress.log).
"""
import argparse
import csv
import datetime
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / '.cache'
SITE = 'https://www.bermudalaws.bm'
CORE = ('Bermuda Constitution Order 1968', 'Criminal Code Act 1907', 'Companies Act 1981', 'Interpretation Act 1951',
        'Evidence Act 1905', 'Rules of the Supreme Court 1985', 'Supreme Court Act 1905', 'Court of Appeal Act 1964',
        'Criminal Jurisdiction and Procedure Act 2015', 'Income Tax Act 1988',
        # the six laws of the first build, so the layout rename can be made in the first push
        'Motor Car Act 1951', 'Bermuda Immigration and Protection Act 1956', 'Human Rights Act 1981',
        'Employment Act 2000')


def seed(path: Path) -> None:
    rows = list(csv.DictReader(path.open(encoding='utf-8-sig')))
    laws = []
    for r in rows:
        u = r['url']
        rest = u[len(f'{SITE}/Laws/Consolidated Law/'):]
        year, _, title = rest.partition('/')
        laws.append({'url': u, 'year': year, 'title': title, 'query': 'seed'})
    laws.sort(key=lambda x: x['url'])
    CACHE.mkdir(exist_ok=True)
    (CACHE / 'catalogue.json').write_text(json.dumps({'expected': len(laws), 'count': len(laws), 'retrieved': 'seed',
                                                      'laws': laws}, indent=1, ensure_ascii=False) + '\n',
                                          'utf-8', newline='\n')
    print(f'seeded {len(laws)} laws', flush=True)


class Gate:
    def __init__(self, cap: int):
        self.cap, self.allowed, self.inflight, self.clean, self.last = cap, 1, 0, 0, 0.0
        self.cv = threading.Condition()
        self.pause_until = 0.0
        self.serving = 0
        self.stopped = None

    def enter(self, ticket: int):
        """Requests go in catalogue order (ticket = position), so the core laws go first."""
        with self.cv:
            while True:
                if self.stopped:
                    return False
                now = time.time()
                gap = 1.0 / self.allowed
                if ticket == self.serving and self.inflight < self.allowed and now >= self.pause_until \
                        and now >= self.last + gap:
                    self.inflight += 1
                    self.serving += 1
                    self.last = now
                    self.cv.notify_all()
                    return True
                self.cv.wait(0.2)

    def leave(self, outcome: str):
        with self.cv:
            self.inflight -= 1
            if outcome == 'ok':
                self.clean += 1
                if self.clean >= 30 and self.allowed < self.cap:
                    self.allowed += 1
                    self.clean = 0
                    print(f'ramp: {self.allowed} in flight', flush=True)
            elif outcome == 'slow':
                self.allowed, self.clean = 1, 0
                self.pause_until = time.time() + 60
                print('back-off: 1 in flight, pause 60 s', flush=True)
            elif outcome == 'throttle':
                self.allowed, self.clean = 1, 0
                self.pause_until = time.time() + 300
                print('throttled: 1 in flight, pause 300 s', flush=True)
            elif outcome == 'blocked':
                self.stopped = 'blocked'
            self.cv.notify_all()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=Path)
    ap.add_argument('--refresh', action='store_true')
    ap.add_argument('--max-inflight', type=int, default=5)
    args = ap.parse_args()
    if args.seed:
        seed(args.seed)
    sys.path.insert(0, str(HERE))
    from acts import ACTS  # noqa: E402  (reads the catalogue just written)
    from fetch import UA, meta, save, url_for  # noqa: E402
    status_file = CACHE / 'status.json'
    status = json.loads(status_file.read_text('utf-8')) if status_file.exists() else {}
    todo = [a for a in ACTS if args.refresh or a['id'] not in status]
    todo.sort(key=lambda a: (a['path_title'] not in CORE, a['id']))
    gate = Gate(args.max_inflight)
    lock = threading.Lock()
    done = [0]

    def one(job):
        ticket, act = job
        if not gate.enter(ticket):
            return
        out = CACHE / f"{act['id']}.pdf"
        tmp = CACHE / f"{act['id']}.part"
        url = url_for(act)
        r = subprocess.run(['curl', '-sS', '--compressed', '-m', '180', '-A', UA, '-o', str(tmp), '-w',
                            '%{http_code} %{content_type}', url], capture_output=True, text=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        code, _, ctype = r.stdout.partition(' ')
        head = tmp.read_bytes()[:2000] if tmp.exists() else b''
        ok = code == '200' and 'pdf' in ctype and head[:5] == b'%PDF-'
        if code in ('', '000') or code.startswith('5') and code != '503':
            outcome = 'slow'
        elif code in ('429', '503'):
            outcome = 'throttle'
        elif code == '403' or b'challenge' in head.lower() or b'captcha' in head.lower():
            outcome = 'blocked'
        else:
            outcome = 'ok'
        with lock:
            if outcome in ('slow', 'throttle', 'blocked'):
                print(act['id'], 'transient' if outcome != 'blocked' else 'BLOCKED', code, r.stderr.strip()[:200],
                      flush=True)
                tmp.unlink(missing_ok=True)
            else:
                if ok:
                    os.replace(tmp, out)
                else:
                    tmp.unlink(missing_ok=True)
                st = {'url': url, 'http': code, 'content_type': ctype, 'ok': ok}
                if ok:
                    st.update(meta(out))
                status[act['id']] = st
                done[0] += 1
                if done[0] % 10 == 0:
                    save(status_file, status)
                    print(f'{done[0]}/{len(todo)} fetched; {gate.allowed} in flight', flush=True)
        gate.leave(outcome)

    with ThreadPoolExecutor(args.max_inflight) as ex:
        list(ex.map(one, enumerate(todo)))
    with lock:
        save(status_file, status)
    if done[0]:
        (CACHE / 'fetched_on.txt').write_text(datetime.date.today().isoformat() + '\n', 'utf-8', newline='\n')
    print(f'{done[0]} fetched this run; {sum(1 for s in status.values() if s.get("ok"))} PDFs cached', flush=True)
    if gate.stopped:
        print('STOPPED: blocked (403 or challenge)', flush=True)
        sys.exit(3)


if __name__ == '__main__':
    main()
