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
Any other difference (missing, extra or moved text) is reported; the exit code is the number of acts that
differ.
"""
import difflib
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from acts import ACTS  # noqa: E402

WORD = re.compile(r'[^\W_]+')


def words(s: str) -> list[str]:
    return [w.casefold() for w in WORD.findall(s)]


def pdf_words(pdf: Path, title: str) -> list[str]:
    out = subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', str(pdf), '-'], capture_output=True, check=True).stdout
    pages = out.decode('utf-8').split('\f')
    keep = []
    for n, page in enumerate(pages):
        lines = [l for l in page.split('\n') if l.strip()]
        if not lines:
            continue
        if n == 0:
            while lines and lines[0].strip() != 'BERMUDA':
                lines.pop(0)  # the crest letters
        elif lines[0].strip().upper() == title.upper():
            lines.pop(0)
        elif lines[0].upper().startswith(title.upper() + '  '):
            lines[0] = lines[0][len(title):]  # the header shares a printed row with a table cell (landscape tables)
        if lines and re.fullmatch(r'\d{1,4}', lines[-1].strip()):
            lines.pop()
        keep.extend(lines)
    return words('\n'.join(keep))


def repo_words(repo: Path, act: dict) -> tuple[list[str], list[tuple[int, int]]]:
    """The words of the act's files in index order, and the letter ranges of its contents.md files."""
    def show(p):
        return subprocess.run(['git', '-C', str(repo), 'show', f'HEAD:{p}'], capture_output=True, check=True).stdout.decode('utf-8')
    order = [l for l in show(f"{act['id']}/index.txt").split('\n') if l]
    out, ranges, pos = [], [], 0
    for p in order:
        w = words(show(f"{act['id']}/{p}"))
        n = sum(len(x) for x in w)
        if p.rsplit('/', 1)[-1] in ('title.md', 'contents.md') or p.rsplit('/', 1)[-1].startswith('schedule'):
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
    bad = 0
    for act in ACTS:
        a = pdf_words(HERE / '.cache' / f"{act['id']}.pdf", act['title'])
        b, ranges = repo_words(repo, act)
        if same(''.join(a), ''.join(b), ranges):
            exact = ''.join(a) == ''.join(b)
            print(f"{act['id']}: {len(''.join(a))} letters and digits ({len(a)} source words), identical"
                  + ('' if exact else f' (in order outside title, contents and schedules; {len(ranges)} such range(s) as the same letters)'))
            continue
        bad += 1
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        ops = [o for o in sm.get_opcodes() if o[0] != 'equal']
        print(f"{act['id']}: {len(a)} source words, {len(b)} repo words, {len(ops)} differences")
        for tag, i1, i2, j1, j2 in ops[:show]:
            print(f"  {tag}: pdf[{i1}:{i2}] {' '.join(a[max(0, i1 - 3):i2 + 3])!r} | repo {' '.join(b[max(0, j1 - 3):j2 + 3])!r}")
        if sorted(a) == sorted(b):
            print('  (same words, different order)')
    sys.exit(bad)


if __name__ == '__main__':
    main()
