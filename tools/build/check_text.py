"""Independent check: the letters and digits of each act in the repo equal those of the raw PDF.

    python scripts/bermuda-law/check_text.py <repo> [--show N]

The source side is read by poppler's `pdftotext -layout` (not PyMuPDF, which the build uses; -layout keeps each
printed row together and does not remove line-end hyphens), keeping every text line except:
on page 1, the crest's letters above "BERMUDA"; on later pages, the first line when it is the running header (the act's
title); on every page, the last line when it is a bare page number. Both sides are cut to one stream of letters and
digits, casefolded (so spaces, punctuation and hyphens, including a line-end hyphen the build removed, do not count). The repo side is every file of the act in its index.txt order, read from git HEAD,
with the markdown heading marks ("#", "##", "###") and the table cell mark "|" being punctuation anyway.
A difference of any kind (missing, extra or moved words) is reported; the exit code is the number of acts that differ.
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
        if lines and re.fullmatch(r'\d{1,4}', lines[-1].strip()):
            lines.pop()
        keep.extend(lines)
    return words('\n'.join(keep))


def repo_words(repo: Path, act: dict) -> list[str]:
    def show(p):
        return subprocess.run(['git', '-C', str(repo), 'show', f'HEAD:{p}'], capture_output=True, check=True).stdout.decode('utf-8')
    order = [l for l in show(f"{act['id']}/index.txt").split('\n') if l]
    return words('\n'.join(show(f"{act['id']}/{p}") for p in order))


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    repo = Path(sys.argv[1])
    show = int(sys.argv[sys.argv.index('--show') + 1]) if '--show' in sys.argv else 10
    bad = 0
    for act in ACTS:
        a = pdf_words(HERE / '.cache' / f"{act['id']}.pdf", act['title'])
        b = repo_words(repo, act)
        if ''.join(a) == ''.join(b):
            print(f"{act['id']}: {len(''.join(a))} letters and digits ({len(a)} source words), identical")
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
