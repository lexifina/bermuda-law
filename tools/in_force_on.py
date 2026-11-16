"""Print a Bermuda law, or one file of it, as this repository has it on a date.

    python tools/in_force_on.py 2026-11-26 acts/1951/89-motor-car               # the whole Act, in printed order
    python tools/in_force_on.py 2026-11-26 acts/1951/89-motor-car section-7A    # section 7A
    python tools/in_force_on.py 2026-11-26 constitution section-1               # the Constitution, section 1
    python tools/in_force_on.py 2026-11-26 constitution order/section-4         # the Constitution Order, section 4

Reads the `In-force:` trailer (the real date; commit dates before 1970 would be clamped). Bermuda Laws Online keeps
only the current consolidation, so a date before a law's first consolidation here has no version. Files are followed
across the layout moves (`git log --follow`), so older versions are read at the path they had then.
Standard library only.
"""
import subprocess
import sys


def git(*args: str) -> str:
    return subprocess.run(['git', *args], capture_output=True, text=True, encoding='utf-8', check=True).stdout


def commit_on(day: str, path: str) -> tuple[str | None, str | None, str | None]:
    """The last version on or before `day` of `path` (followed across renames): (commit, its path then, earliest
    date known). Commits without an In-force or Consolidated trailer (pure layout moves) are passed over."""
    fmt = '%x1e%H%x1f%(trailers:key=In-force,valueonly,separator=)%x1f%(trailers:key=Consolidated,valueonly,separator=)%x1f%(trailers:key=Kind,valueonly,separator=)'
    earliest = None
    found = None
    out = git('log', '--follow', '--name-only', f'--format={fmt}', 'main', '--', path)
    for block in out.split('\x1e')[1:]:
        head, _, names = block.partition('\n')
        h, inforce, consolidated, kind = (head.split('\x1f') + ['', '', ''])[:4]
        p = next((n for n in names.split('\n') if n.strip()), path)
        d = (inforce or consolidated).strip()
        if not d or kind.strip() in ('layout', 'documentation'):
            continue
        earliest = d
        if found is None and d <= day:
            found = (h, p)
    return (found[0], found[1], earliest) if found else (None, None, earliest)


def main() -> None:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')  # the laws use dashes and quotes outside the console code page
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    day, law = sys.argv[1], sys.argv[2].strip('/')
    unit = sys.argv[3] if len(sys.argv) > 3 else None
    if unit and unit.endswith('.md'):
        unit = unit[:-3]
    path = f'{law}/{unit}.md' if unit else f'{law}/index.txt'
    h, then, earliest = commit_on(day, path)
    if not h:
        if earliest:
            sys.exit(f'{path}: no version on or before {day}; the record starts at {earliest}, '
                     'the consolidation Bermuda Laws Online publishes (it keeps no earlier text)')
        sys.exit(f'{path}: not found')
    if unit:
        sys.stdout.buffer.write((git('show', f'{h}:{then}')).encode("utf-8"))
        return
    folder = then.rsplit('/', 1)[0]
    names = [n for n in git('show', f'{h}:{folder}/index.txt').splitlines() if n]
    for n in names:
        sys.stdout.buffer.write((git('show', f'{h}:{folder}/{n}') + '\n').encode("utf-8"))


if __name__ == '__main__':
    main()
