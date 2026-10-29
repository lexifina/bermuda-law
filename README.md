# The laws of Bermuda, as a git repository

Every consolidated law on [Bermuda Laws Online](https://www.bermudalaws.bm), the Attorney-General's Chambers' site:
1551 laws, Acts and statutory instruments, from the Bermuda Constitution Order 1968 (with the Constitution of
Bermuda, its Schedule 2) to the newest regulations. There is one file per section or schedule (30062 files), with
one paragraph per line, so `git blame` and `git diff` work line by line. It follows the shared design of
[lexifina/global-law](https://github.com/lexifina/global-law), which places it at `bm/national/acts`.

**What this repository is not, yet: a history.** Bermuda Laws Online publishes only the current consolidated text of
each law and keeps no earlier consolidations. So each law is a single commit holding its whole current text
(`Kind: consolidated`). There is no line-by-line history before the consolidation date. Later consolidations will be
added from now on as new commits, so the history grows forward from here. The amendment history the site prints is
kept: every history note under a section (`[Section 7A inserted by 2008:44 s.4 effective 23 December 2008]`) and each
law's "Amended by" list are in the files, and both are listed in [`data/amendments.csv`](data/amendments.csv).

| Kind (the PDF's own Subject) | Laws |
| --- | --- |
| Statutory instrument | 693 |
| Laws of Bermuda | 455 |
| Act (Statute) | 319 |
| unknown | 59 |
| Bill | 20 |
| AG3/106-RM/sd | 1 |
| Bermuda International Conciliation and Arbitration Act 1993 | 1 |
| Justice Protection Act 2010 | 1 |
| Legislature (Appointment, Election and Membership Controversies) Act 1968 | 1 |
| Parliament Act 1957 | 1 |

Each law is in a folder named after its title (`motor-car-act-1951/`); [`laws.csv`](laws.csv) lists them all with
their number, folder, consolidation day, files and notes. The site listed 1555 consolidated laws on 2026-10-29;
1551 are here, and 4 could not be read (listed with the reason in [`data/unreadable.csv`](data/unreadable.csv)).
The record holds 1551 laws, consolidated between 2006-06-07 and 2026-10-21, in 1552 commits.

## A lawyer's questions as git commands

| Question | Command |
| --- | --- |
| What does section 7A of the Motor Car Act 1951 say? | `python tools/in_force_on.py 2026-10-29 motor-car-act-1951 section-7A` |
| The whole of a law, in printed order | `python tools/in_force_on.py 2026-10-29 human-rights-act-1981` |
| Section 1 of the Constitution of Bermuda | `cat constitution/section-1.md` |
| Section 4 of the Constitution Order itself | `cat constitution/order/section-4.md` |
| Which laws amended an Act ("Amended by") | `cat employment-act-2000/end.md` |
| What a section's history notes say | `grep -h '^\[' motor-car-act-1951/section-2.md` |
| Every section an amending law touched, by its notes | `grep '2008:44' data/amendments.csv` |
| What changed in a law since this build (after later builds) | `git log -p -- motor-car-act-1951` |
| The list of laws, with their dates | [`laws.csv`](laws.csv) |

Each file starts with any Part or Chapter headings above it (`## PART II`), then the section heading as printed
(`# Interpretation`), then its paragraphs, one per line. The section number comes first on the first paragraph, as
in the margin of the PDF (`2 (1) In this Act ...`). Labels come before their text (`(a) ...`). A history note is a
paragraph of its own, copied as printed. Schedules are one file each (`schedule-1B.md`); their tables are flattened to
one line per printed row, with ` | ` between cells. Each law's `title.md` has its title and number, `contents.md` the
printed table of contents, `end.md` the assent date, the operative date where printed, and the "Amended by" list, and
`index.txt` lists the files in printed order.

## The dates, and which one we use

Each consolidated PDF carries the date it was produced (its CreationDate, for example `D:20260716145002-04'00'` for
the Motor Car Act 1951). **Each commit is dated by that day**, at noon Bermuda time (UTC-4, or UTC-3 in daylight
time), and the day is in the `In-force:` and `Consolidated:` trailers (`Date-source: pdf-created`). It is the day of
the consolidation, so the text is the law as amended up to then. It is not the day any amendment took effect. Those
days are in the history notes (`effective 23 December 2008`) and in [`data/amendments.csv`](data/amendments.csv),
which does not turn one kind of date into the other. The latest effective day in each law's notes is in its
`Latest-note-effective:` trailer. None of them is after the consolidation day. The site says it is "updated
regularly" and gave "Laws amended up to: Friday, 16th October 2026" on the day of retrieval (2026-10-29).

The site prints text that is not yet in force in colour (green). 12 of the 1551 PDFs have some: their main commit leaves the coloured text out, and the `future` branch (never merged) adds one commit per such law with the whole printed text, coloured parts included. `main` holds only what was in force on the consolidation day.

`tools/in_force_on.py` answers for any day on or after a law's consolidation day. For an earlier day it says there is
no version, because the source has none.

## What "author" means

Every law commit has the same author: `Attorney-General's Chambers, Bermuda (Bermuda Laws Online)
<bermuda-laws-online@bermudalaws-bm.invalid>`, with `Kind: consolidated`. The address cannot exist. The author is the
publisher of the consolidation, not a lawmaker. No line is credited to an amending law, because without the earlier
text nobody can tell which words an amendment wrote. In this design, a change is credited to an amending law only when
the source shows the text before and after it. When later consolidations are added, a change will be credited to an
amending law only where a new history note names one. Otherwise it is labelled `Kind: unexplained` and authored by the
publisher. The history notes name 2398 distinct amending laws in 14726 rows, and
the "Amended by" lists hold 5790 entries.

## What it does not show

- Any text before the current consolidation. Bermuda Laws Online has none. The "Annual Laws" (Acts and statutory
  instruments as made, from 1993) are on the site but are not used here, and no amendment is replayed.
- Laws the site does not list as consolidated law (repealed laws, the Annual Laws as made); 4 listed laws whose PDF could not be read, in [`data/unreadable.csv`](data/unreadable.csv) with the reason.
- Text formatting: italics, bold and the PDF's layout. Tables in the schedules are flattened to one line per printed
  row, so a cell that wraps onto a second line can come after the next cell.
- The crest, the running header and the page numbers.

This is a research aid. The site says its consolidations "are provided for informational purposes only and do not yet
have official sanction"; the authoritative text is the 1989 Revised Laws with replacement pages, the Annual Laws and
the Gazette. The same is true of this repository.

## How it is checked

`tools/build/` holds the build as it was run, and [`data/source-sha256.tsv`](data/source-sha256.tsv) the sha256 of
every PDF it read. Before publishing, the build was checked for these things:
- an independent word check (`tools/build/check_text.py`). The PDFs are read again with poppler's `pdftotext`, not
  with the PyMuPDF reader the build uses, and the letters and digits of each law's files, in `index.txt` order, are
  compared with those of its PDF (the crest, the running headers, "1989 Revision" and the page numbers excepted).
  Each law gets one of three results: identical in order (the title page, contents and tables may be in any order),
  the same letters with some words in another order (the two readers place a margin number, a table cell or a
  column differently), or different. 
- `tools/build/check_repo.py`: every trailer parses, `In-force` is on every commit, there are no merges, dates never
  go backwards, no date is after the build day, there are no carriage returns, and the on-date tool prints the
  stored text;
- two builds from the same cache give the same HEAD;
- global-law's `check_corpus.py` passes.

## How it is built

`fetch.py` asks for each PDF by its address, `/Laws/Consolidated Law/<year>/<title>`. That is one request per law,
1551 in all, made one at a time and 2 s apart. `parse_pdf.py` reads each PDF's lines with their position and
font. It finds headings (bold), section numbers (in the margin), labels and paragraphs (by the gap above a line), and
history notes (italic 8pt). `build.py` writes one commit per law with `git fast-import`. The agent that wrote these
scripts was Claude Opus 5.5 (claude-opus-5-5), run as a Claude Code agent. No AI model takes part in building or checking, and no model wrote any legal text.

## Licence

Source: Bermuda Laws Online (https://www.bermudalaws.bm), Attorney-General's Chambers, Government of Bermuda. The site
says: "This website and its contents are Crown Copyright The Government of Bermuda - All Rights Reserved". Bermuda law
has no exclusion for official texts. The Copyright and Designs Act 2004, s. 199(1), says "Her Majesty is entitled to
copyright in every Act of the Legislature", and s. 199(2) says the copyright lasts for 50 years from the end of the
year of Assent. The site has no terms of use forbidding automated reading, and it has no robots.txt. The wording was
not changed; it was only split into files and lines. **This repository is private, and it must stay private unless
the Government of Bermuda gives permission.** Lexifina's own contributions (the tools, the arrangement and the commit
messages) are CC0. See [`LICENSE`](LICENSE) and [`SOURCES.md`](SOURCES.md).
