# Reproducing this repository

Built on 2026-10-28 from PDFs retrieved from bermudalaws.bm on 2026-10-28, by the scripts in `tools/build/` (copied
there as run). The agent that wrote the scripts was Claude Opus 5.5 (claude-opus-5-5), run as a Claude Code agent. No model runs at build time.

| Script | sha256 |
| --- | --- |
| acts.py | `00293ca6d3cad3b49a279e00d3f157575e153abd021e7ee931451289db401d2c` |
| fetch.py | `5404464f69a3112a61bcd906bb34ebe0bd668506342fb9068eeaf11c3119bc42` |
| parse_pdf.py | `a837074524df72b959e286713ff36344d4be5b1c735bd05b01859e966a70ba88` |
| build.py | `b870cf424aa31510a20502a5727dd1fc897b77e7cef18878e456cdd6b2e04337` |
| docs.py | `d968198db8accdd019bc2d380296312bb01aa6f4307398c40061b0199c2d65c1` |
| check_text.py | `5022196a5074d2599230e483dce123086bdf8f19d942b361eb75e64df54ac551` |
| check_repo.py | `5729eea14f103727e03174181e2eb632a3c9c8b5f96135bb6e575245ad004ad7` |

## Steps

```sh
python fetch.py                       # 6 PDFs into .cache/ (one request each, 2 s apart; cached, incl. failures)
python build.py ../bermuda-law --today 2026-10-28
python build.py ../bermuda-law --today 2026-10-28 --verify-rebuild   # two builds in temp folders, same HEAD
python check_text.py ../bermuda-law   # independent letters-and-digits check against pdftotext
python check_repo.py ../bermuda-law --today 2026-10-28
```

The PDFs are listed with their sha256 and address in `data/source-sha256.tsv`. The same PDFs give the same commit
hashes: the history is one `git fast-import` stream, sorted, with fixed dates, written as bytes (no carriage returns).

## robots.txt, terms and challenges

These were checked on 2026-10-28. `https://www.bermudalaws.bm/robots.txt` answers 404, so there are no rules,
The site's pages (Disclaimer, About, FAQ) set no terms of use. They say: "Crown Copyright ... All Rights Reserved",
and the consolidations "are provided for informational purposes only and do not yet have official sanction". There is
no bulk download. The list of consolidated laws is behind the site's interactive (Blazor Server) search, which was not
used. Each PDF was asked for by its address.

## Fetch rate

There is no Crawl-delay, because there is no robots.txt. `fetch.py` makes one request at a time, 2 s apart, with a
browser User-Agent and `curl --compressed`. That was 6 law PDFs, plus one for the Copyright and Designs Act
2004 (read for the copyright rule, not included) and a handful of page reads for the gates. That is under 20 requests
in all.

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
