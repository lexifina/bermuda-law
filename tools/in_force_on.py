"""Print a Bermuda law, or one file of it, as this repository has it on a date.

    python tools/in_force_on.py 2026-10-28 motor-car-act-1951               # the whole Act, in printed order
    python tools/in_force_on.py 2026-10-28 motor-car-act-1951 section-7A    # section 7A
    python tools/in_force_on.py 2026-10-28 constitution section-1           # the Constitution, section 1
    python tools/in_force_on.py 2026-10-28 constitution order/section-4     # the Constitution Order, section 4

Reads the `In-force:` trailer (the real date; commit dates before 1970 would be clamped). Bermuda Laws Online keeps
only the current consolidation, so a date before a law's consolidation date has no version here.
Standard library only.
"""
import subprocess
import sys


def git(*args: str) -> str:
    return subprocess.run(['git', *args], capture_output=True, text=True, encoding='utf-8', check=True).stdout


def commit_on(day: str, path: str) -> tuple[str | None, str | None]:
    """The last commit on or before `day` that touched `path`, and the earliest date known for it."""
    fmt = '%H%x1f%(trailers:key=In-force,valueonly,separator=)%x1f%(trailers:key=Consolidated,valueonly,separator=)'
    earliest = None
    for line in git('log', '--first-parent', f'--format={fmt}', 'main', '--', path).splitlines():
        h, inforce, consolidated = (line.split('\x1f') + ['', ''])[:3]
        d = (inforce or consolidated).strip()
        if not d:
            continue
        earliest = d
        if d <= day:
            return h, d
    return None, earliest


def main() -> None:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')  # the laws use dashes and quotes outside the console code page
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    day, law = sys.argv[1], sys.argv[2].strip('/')
    unit = sys.argv[3] if len(sys.argv) > 3 else None
    if unit and unit.endswith('.md'):
        unit = unit[:-3]
    path = f'{law}/{unit}.md' if unit else law
    h, earliest = commit_on(day, path)
    if not h:
        if earliest:
            sys.exit(f'{path}: no version on or before {day}; the record starts at {earliest}, '
                     'the consolidation Bermuda Laws Online publishes (it keeps no earlier text)')
        sys.exit(f'{path}: not found')
    if unit:
        sys.stdout.buffer.write((git('show', f'{h}:{path}')).encode("utf-8"))
        return
    try:
        names = [n for n in git('show', f'{h}:{law}/index.txt').splitlines() if n]
    except subprocess.CalledProcessError:
        names = sorted(n.rsplit('/', 1)[-1] for n in git('ls-tree', '--name-only', h, f'{law}/').split())
    # one `git cat-file --batch` for the whole law (one `git show` per file is slow on Windows)
    specs = ''.join(f'{h}:{law}/{n}\n' for n in names).encode('utf-8')
    out = subprocess.run(['git', 'cat-file', '--batch'], input=specs, capture_output=True, check=True).stdout
    pos = 0
    for _ in names:
        end = out.index(b'\n', pos)
        head = out[pos:end].split()
        pos = end + 1
        if head[1] == b'missing':
            continue
        size = int(head[2])
        sys.stdout.buffer.write(out[pos:pos + size] + b'\n')
        pos += size + 1


if __name__ == '__main__':
    main()
