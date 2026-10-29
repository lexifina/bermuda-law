"""The Bermuda laws in this repository: every consolidated law Bermuda Laws Online lists (catalogue.py), each in a
folder of its own named after its title.

id: folder name in the repo; year and path_title: the bermudalaws.bm path /Laws/Consolidated Law/<year>/<path_title>
(the year can be empty); title: the title the PDF itself gives (its Title metadata, read by fetch.py), else the
path title. The six laws of the first build keep their folders: the Constitution Order is `constitution/` (the
Constitution, its Schedule 2, at the top; the Order's own sections in `constitution/order/`).
"""
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / '.cache'

SPECIAL = {
    'Bermuda Constitution Order 1968': {'id': 'constitution', 'main_folder': 'order',
                                        'sub_acts': {'SCHEDULE 2 TO THE ORDER': ''}},
}


def slug(title: str) -> str:
    s = re.sub(r'[^a-z0-9]+', '-', title.lower().replace('&', ' and ')).strip('-')
    if len(s) > 90:
        s = s[:80].rstrip('-') + '-' + hashlib.sha256(title.encode('utf-8')).hexdigest()[:8]
    return s


def title_of(meta: str, path_title: str) -> str:
    """The PDF's Title metadata, unless it is a cut-off start of the path title (then the path title)."""
    meta, path_title = ' '.join(meta.split()), ' '.join(path_title.split())
    if not meta or (path_title.lower().startswith(meta.lower()) and len(path_title) > len(meta)):
        return path_title
    return meta


def load() -> list[dict]:
    cat = CACHE / 'catalogue.json'
    status_file = CACHE / 'status.json'
    status = json.loads(status_file.read_text('utf-8')) if status_file.exists() else {}
    if not cat.exists():
        return []
    laws = json.loads(cat.read_text('utf-8'))['laws']
    out, seen = [], set()
    for law in sorted(laws, key=lambda x: (x['title'], x['year'])):
        path_title = law['title']
        extra = SPECIAL.get(path_title, {})
        i = extra.get('id') or slug(path_title)
        if i in seen:
            i = f"{i}-{law['year'] or 'no-year'}"
        k = 2
        base = i
        while i in seen:
            i = f'{base}-{k}'
            k += 1
        seen.add(i)
        st = status.get(i, {})
        act = {'id': i, 'year': law['year'], 'path_title': path_title,
               'title': title_of(st.get('title') or '', path_title), 'kind': st.get('subject', ''),
               'url': law['url']}
        act.update({k: v for k, v in extra.items() if k != 'id'})
        out.append(act)
    return out


ACTS = load()
