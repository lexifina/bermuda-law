"""Independent check: the letters and digits of each act in the repo equal those of the raw PDF.

    python scripts/bermuda-law/check_text.py <repo> [--show N]

The source side is read by poppler's `pdftotext -layout` (not PyMuPDF, which the build uses; -layout keeps each
printed row together and does not remove line-end hyphens), keeping every text line except:
on page 1, the crest's letters above "BERMUDA"; on later pages, the first line when it is the running header (the act's
title); on every page, the last line when it is a bare page number. Both sides are cut to one stream of letters and
digits, casefolded (so spaces, punctuation and hyphens, including a line-end hyphen the build removed, do not
count). The repo side is every file of the act in its index.txt order, read from git HEAD; the markdown heading marks
("#", "##") and the table cell mark "|" are punctuation anyway.
Exact order is required everywhere except inside the title page, the printed tables of contents and the schedules
(title.md, contents.md, schedule*.md), which are mostly tables. There,
pdftotext -layout shifts the column of section numbers against the titles: it puts "24" beside "GENERAL" in the Human
Rights Act 1981, whose section 23 is "Consent to prosecution". So for those ranges the same letters are required, in
any order. The same holds in schedule tables, where the two readers order the cells of a wrapped row differently.
On a page whose running header shares a printed row with a table cell, the title is cut from the front of that row.
The older Word-made "1989 Revision" PDFs also lose their header rows ("Title 5", "Laws of Bermuda", "Item 16(a)"),
their "1989 Revision" footer (also when pdftotext puts it on a row of text, or letter-spaced) and their page number.
A table row (a file with " | ") is compared as the same letters in any order, like a schedule.
A law that fails the in-order comparison but has exactly the same letters and digits overall is reported as "the
same letters, in another order"; one whose letters differ is reported as different, with the words found on one
side only. Laws with green text are read from the `future` branch, which has the whole printed text.
Run over every law, it writes .cache/check_text.tsv (one row per law), which the next build publishes as
data/check-text.tsv. The exit code is the number of laws that differ (at most 125).
"""
import difflib
from collections import Counter
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from acts import ACTS  # noqa: E402

# what each remaining difference is, after looking at it (filled in by hand from the last run)
NOTES: dict[str, str] = {}

WORD = re.compile(r'[^\W_]+')


def words(s: str) -> list[str]:
    return [w.casefold() for w in WORD.findall(s)]


OLD_HEADER = re.compile(r'(?:Title \d+[A-Z]?|Laws of Bermuda|Item \d+[0-9A-Za-z().]*)'
                        r'(?: (?:Title \d+[A-Z]?|Laws of Bermuda|Item \d+[0-9A-Za-z().]*))*', re.I)
OLD_FOOTER = re.compile(r'\d{0,4}(?:1989Revision)?\d{0,4}', re.I)  # matched with the spaces taken out
REVISION = r'1 ?9 ?8 ?9 ?R ?e ?v ?i ?s ?i ?o ?n'  # sometimes letter-spaced ("1 9 8 9 R e v i s ion")


def pdf_words(pdf: Path, title: str) -> list[str]:
    out = subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', str(pdf), '-'], capture_output=True, check=True).stdout
    pages = out.decode('utf-8').split('\f')
    keep = []
    for n, page in enumerate(pages):
        lines = [l for l in page.split('\n') if l.strip()]
        if not lines:
            continue
        top = [l.strip() for l in lines[:12]]
        if n == 0 and 'BERMUDA' in top and all(len(w) <= 3 for l in top[:top.index('BERMUDA')] for w in l.split()):
            while lines and lines[0].strip() != 'BERMUDA':
                lines.pop(0)  # the crest letters ("QUO FAT A F E R UN T")
        # the 1989 Revision header: "Title 5", "Laws of Bermuda", "Item 16(a)", in up to three printed rows
        while lines and OLD_HEADER.fullmatch(' '.join(lines[0].split())):
            lines.pop(0)
        if n > 0 and lines:
            if ''.join(lines[0].split()).upper() == ''.join(title.split()).upper():
                lines.pop(0)
            elif len(lines) > 1 and ''.join((lines[0] + lines[1]).split()).upper() == ''.join(title.split()).upper():
                del lines[:2]  # the title wrapped onto two printed rows
            elif lines[0].upper().startswith(title.upper() + '  '):
                lines[0] = lines[0][len(title):]  # the header shares a printed row with a table cell (landscape)
                lines[0] = re.sub(r'^\s*' + REVISION + r'\s*$', '', lines[0], flags=re.I)
        # the foot: the page number, and "1989 Revision" in the older PDFs, in one or two printed rows; a row that is
        # only "1989 Revision" (and the page number) goes wherever pdftotext puts it
        lines = [l for l in lines if not re.fullmatch(r'\d{0,4}1989revision\d{0,4}', ''.join(l.split()).lower())]
        for k in range(len(lines) - 1, max(len(lines) - 9, -1), -1):
            flat = ''.join(lines[k].split())
            if flat and OLD_FOOTER.fullmatch(flat) and (k == len(lines) - 1 or 'revision' in flat.lower()
                                                         or (k >= len(lines) - 4 and flat in (str(n), str(n + 1)))):
                del lines[k]
                continue
            # the page number at the end of a printed row of text (a two-column list), set off by a wide gap
            if k >= len(lines) - 3:
                lines[k] = re.sub(r'(?<=\S)\s{8,}(\d{1,4})\s*$',
                                  lambda m: '' if abs(int(m.group(1)) - n - 1) <= 3 else m.group(0), lines[k])
            # "1989 Revision" sharing a printed row with other text ("[Amended by        1989 Revision"), set off by
            # wide gaps
            lines[k] = re.sub(r'(?:^\s*|\s{2,})' + REVISION + r'(?=\s{2,}|\s*$)', '  ', lines[k], flags=re.I)
        keep.extend(lines)
    return words('\n'.join(keep))


class Blobs:
    """Reads files from git through one `git cat-file --batch` process (one `git show` per file is slow on Windows)."""

    def __init__(self, repo: Path):
        self.p = subprocess.Popen(['git', '-C', str(repo), 'cat-file', '--batch'], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE)

    def get(self, spec: str) -> str | None:
        self.p.stdin.write(spec.encode('utf-8') + b'\n')
        self.p.stdin.flush()
        head = self.p.stdout.readline().split()
        if len(head) < 3 or head[1] == b'missing':
            return None
        data = self.p.stdout.read(int(head[2]))
        self.p.stdout.read(1)
        return data.decode('utf-8')


def repo_words(blobs: Blobs, ref: str, act: dict) -> tuple[list[str], list[tuple[int, int]]]:
    """The words of the act's files in index order, and the letter ranges of its title, contents and schedules."""
    order = [l for l in blobs.get(f"{ref}:{act['id']}/index.txt").split('\n') if l]
    out, ranges, pos = [], [], 0
    for p in order:
        text = blobs.get(f"{ref}:{act['id']}/{p}")
        w = words(text)
        n = sum(len(x) for x in w)
        if p.rsplit('/', 1)[-1] in ('title.md', 'contents.md') or p.rsplit('/', 1)[-1].startswith('schedule') or ' | ' in text:
            if ranges and ranges[-1][1] == pos:
                ranges[-1] = (ranges[-1][0], pos + n)  # title.md and contents.md together
            else:
                ranges.append((pos, pos + n))
        out += w
        pos += n
    return out, ranges


def same(a: str, b: str, ranges: list[tuple[int, int]]) -> bool:
    """Equal in order outside the contents ranges; the same letters, in any order, inside them."""
    if len(a) != len(b):
        return False
    edge = 0
    for s, e in ranges:
        if a[edge:s] != b[edge:s] or sorted(a[s:e]) != sorted(b[s:e]):
            return False
        edge = e
    return a[edge:] == b[edge:]


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    repo = Path(sys.argv[1])
    show = int(sys.argv[sys.argv.index('--show') + 1]) if '--show' in sys.argv else 10
    only = [x for x in sys.argv[2:] if not x.startswith('--') and not x.isdigit()]
    blobs = Blobs(repo)
    future = subprocess.run(['git', '-C', str(repo), 'diff', '--name-only', 'main', 'future'], capture_output=True,
                            text=True, encoding='utf-8').stdout.split()
    coloured = {f.split('/')[0] for f in future}
    bad = 0
    checked = 0
    reordered = 0
    results: list[list[str]] = []
    for act in ACTS:
        if only and act['id'] not in only:
            continue
        ref = 'future' if act['id'] in coloured else 'main'
        if blobs.get(f"{ref}:{act['id']}/index.txt") is None:
            continue  # not built (data/unreadable.csv)
        checked += 1
        a = pdf_words(HERE / '.cache' / f"{act['id']}.pdf", act['title'])
        b, ranges = repo_words(blobs, ref, act)
        if same(''.join(a), ''.join(b), ranges):
            exact = ''.join(a) == ''.join(b)
            print(f"{act['id']}{' (future branch)' if ref == 'future' else ''}: {len(''.join(a))} letters and digits ({len(a)} source words), identical"
                  + ('' if exact else f' (in order outside title, contents and schedules; {len(ranges)} such range(s) as the same letters)'))
            results.append([act['id'], 'identical', ref, str(len(''.join(a))), ''])
            continue
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        ops = [o for o in sm.get_opcodes() if o[0] != 'equal']
        if sorted(''.join(a)) == sorted(''.join(b)):
            # every letter and digit is there, none extra; the two readers put some words in a different order
            # (a margin number beside a wrapped heading, a table cell, a two-column contents list)
            reordered += 1
            print(f"{act['id']}: {len(''.join(a))} letters and digits, the same letters; order differs in "
                  f"{len(ops)} place(s)")
            for tag, i1, i2, j1, j2 in ops[:min(show, 3)]:
                print(f"  {tag}: pdf {' '.join(a[max(0, i1 - 3):i2 + 3])!r} | repo {' '.join(b[max(0, j1 - 3):j2 + 3])!r}")
            results.append([act['id'], 'same-letters', ref, str(len(''.join(a))), f'{len(ops)} place(s) in another order'])
            continue
        bad += 1
        ca, cb = Counter(a), Counter(b)
        only_pdf = ' '.join(f'{w}x{n}' for w, n in sorted((ca - cb).items())[:12])
        only_repo = ' '.join(f'{w}x{n}' for w, n in sorted((cb - ca).items())[:12])
        results.append([act['id'], 'differs', ref, str(len(''.join(a))),
                        f'only in pdftotext: {only_pdf or "-"}; only in repo: {only_repo or "-"}'
                        + (f'; {NOTES[act["id"]]}' if act['id'] in NOTES else '')])
        print(f"{act['id']}: DIFFERS: {len(a)} source words, {len(b)} repo words, {len(ops)} differences")
        for tag, i1, i2, j1, j2 in ops[:show]:
            print(f"  {tag}: pdf[{i1}:{i2}] {' '.join(a[max(0, i1 - 3):i2 + 3])!r} | repo {' '.join(b[max(0, j1 - 3):j2 + 3])!r}")
    if not only:
        out = ['law\tresult\tbranch\tletters\tnotes'] + ['\t'.join(r) for r in sorted(results)]
        (HERE / '.cache' / 'check_text.tsv').write_text('\n'.join(out) + '\n', 'utf-8', newline='\n')
    print(f'{checked} laws checked: {checked - bad - reordered} identical, {reordered} the same letters in a '
          f'different order somewhere, {bad} differ')
    sys.exit(min(bad, 125))


if __name__ == '__main__':
    main()
