# Reproducing this repository

Built on 2026-10-28 from PDFs retrieved from bermudalaws.bm on 2026-10-28, by the scripts in `tools/build/` (copied
there as run). The agent that wrote the scripts was Claude Opus 5.5 (claude-opus-5-5), run as a Claude Code agent. No model runs at build time.

| Script | sha256 |
| --- | --- |
| acts.py | `00293ca6d3cad3b49a279e00d3f157575e153abd021e7ee931451289db401d2c` |
| parse_pdf.py | `a837074524df72b959e286713ff36344d4be5b1c735bd05b01859e966a70ba88` |
| build.py | `b870cf424aa31510a20502a5727dd1fc897b77e7cef18878e456cdd6b2e04337` |
| docs.py | `d968198db8accdd019bc2d380296312bb01aa6f4307398c40061b0199c2d65c1` |
| check_text.py | `5022196a5074d2599230e483dce123086bdf8f19d942b361eb75e64df54ac551` |
| check_repo.py | `5729eea14f103727e03174181e2eb632a3c9c8b5f96135bb6e575245ad004ad7` |

## Steps

```sh
# the 6 retrieved PDFs (sha256 and address in data/source-sha256.tsv), where build.py reads them
python build.py ../bermuda-law --today 2026-10-28
python build.py ../bermuda-law --today 2026-10-28 --verify-rebuild   # two builds in temp folders, same HEAD
python check_text.py ../bermuda-law   # independent letters-and-digits check against pdftotext
python check_repo.py ../bermuda-law --today 2026-10-28
```

The PDFs are listed with their sha256 and address in `data/source-sha256.tsv`. The same PDFs give the same commit
hashes: the history is one `git fast-import` stream, sorted, with fixed dates, written as bytes (no carriage returns).

## Terms

These were checked on 2026-10-28.
The site's pages (Disclaimer, About, FAQ) set no terms of use. They say: "Crown Copyright ... All Rights Reserved",
and the consolidations "are provided for informational purposes only and do not yet have official sanction". There is
no bulk download. The list of consolidated laws is in the site's interactive search, which was not
used. Each PDF comes from its own address.

On 2026-11-26 the repository's owner confirmed that this repository stays public, with the legal text under the
site's own terms ("Crown Copyright ... All Rights Reserved"; Copyright and Designs Act 2004, s. 199) as LICENSE
states, and Lexifina's own contributions under CC0 1.0.

## What the build produced

- 6 laws, 725 section and schedule files, 400 history notes, 299 "Amended by" entries.
- 7 commits: 6 consolidated (one per law, by the publisher) and one documentation commit.
- Consolidation days from 2022-06-29 to 2026-10-19.

## Checks

```sh
git rev-list --merges --count main                      # 0
git log --format=%B main | tr -cd '\r' | wc -c          # 0
python tools/in_force_on.py 2026-10-28 motor-car-act-1951 section-7A
```

## 2026-11-26: every consolidated law, appended to main

main is append-only, so the expansion is added on top of the published history, not rebuilt:

```sh
# the catalogue of an earlier full search (data/catalogue.csv, 1,555 addresses), then each PDF
python fetch_fast.py --seed catalogue_seed.csv     # 1 request in flight ~1 s apart, +1 per 30 clean answers, max 5
python build.py ../bermuda-law-build --today 2026-11-26   # the whole build, flat <id>/ folders, in a scratch repo
python append.py ../bermuda-law-build ../bermuda-law --push
python catalogue.py                                # the site's search, for laws added since; then fetch and append
```

`append.py` (in `tools/build/` with the other scripts) adds to origin/main by one `git fast-import`, fast-forward only:
one pure-rename commit to the layout of [STRUCTURE.md](STRUCTURE.md) (`Kind: layout`), then one commit for each law
whose files differ from what main holds, in consolidation-day order (dated noon Bermuda time on the PDF's production
day, `In-force-basis:` saying so), then a data commit (laws.csv, data/paths.json, corpus.json, data tables). A law
whose PDF is unchanged makes no commit. The runner (`runner.py`, detached, below-normal priority) repeats this every
15 minutes while PDFs arrive. No OCR: a PDF with no text layer is listed in data/unreadable.csv.