# Reproducing this repository

Built on 2026-10-29 from PDFs retrieved from bermudalaws.bm on 2026-10-29, by the scripts in `tools/build/` (copied
there as run). The agent that wrote the scripts was Claude Opus 5.5 (claude-opus-5-5), run as a Claude Code agent. No model runs at build time.

| Script | sha256 |
| --- | --- |
| catalogue.py | `5a4616e04d7b5deb231c501f407b9a86da4cc216d74d4ce7a6f8a5b3c5d84c63` |
| acts.py | `3a85f8b3e0792b0c07fd4ea693f4218b45fadbf6817944dd950d021673f579ec` |
| fetch.py | `0dabd68fae02c782f4c59d62be07e577ea25945280b31904e0c519ebf0ece30b` |
| parse_pdf.py | `0f7d257ec3d12ee3270d3ff1f4f37c90570d98ee644fef08b73a465256bfd99d` |
| build.py | `df537200a53b136833fe13ed3eb7da76a13c42bad3249249619874a77d9d8da7` |
| docs.py | `93831feb38f5c0cbff858793f0d1d6241a616e937a45ff37d4a33aa45a1845f1` |
| check_text.py | `66185703ef65eee3ea293c43c2e8d423f42dbf0973aeb26d375d41532df22d4c` |
| check_repo.py | `b9f0fe3859cc47d89b3c454fce99da20b3e41af91c28147558f079b78f3183d8` |

## Steps

```sh
python catalogue.py                   # the list of consolidated laws, from the search pages, into .cache/catalogue.json
python fetch.py                       # 1555 PDFs into .cache/ (one request each, 1 s apart; cached, incl. failures)
python build.py ../bermuda-law --today 2026-10-29
python build.py ../bermuda-law --today 2026-10-29 --verify-rebuild   # two builds in temp folders, same HEAD
python check_text.py ../bermuda-law   # independent letters-and-digits check against pdftotext
python check_repo.py ../bermuda-law --today 2026-10-29
```

The PDFs are listed with their sha256 and address in `data/source-sha256.tsv`. The same PDFs give the same commit
hashes: the history is one `git fast-import` stream, sorted, with fixed dates, written as bytes (no carriage returns).

## robots.txt, terms and challenges

These were checked on 2026-10-29. `https://www.bermudalaws.bm/robots.txt` answers 404, so there are no rules,
The site's pages (Disclaimer, About, FAQ) set no terms of use. They say: "Crown Copyright ... All Rights Reserved",
and the consolidations "are provided for informational purposes only and do not yet have official sanction". There is
no bulk download and no sitemap. The list of consolidated laws was read from the site's search pages, which the server
renders as plain HTML (no browser session, no websocket): `catalogue.py` asks `Title:<year>` for every year from 1600
to 2026, splits a query with more than 40 results by a title-word initial until each part fits on one page,
and then asks for the titles with no year. The union, 1555 addresses, is
[`data/catalogue.csv`](data/catalogue.csv); the site's own refiner count was 1555. Each PDF was then asked for by
its address.

## Fetch rate

There is no Crawl-delay, because there is no robots.txt. `catalogue.py` makes one search request at a time, 2 s
apart (441 pages); `fetch.py` one PDF request at a time, 1 s apart (1555 PDFs), each with a
browser User-Agent and `curl --compressed`, and every answer cached, so a rerun asks for nothing again. Before that,
the first build read 6 PDFs, one for the Copyright and Designs Act 2004 (read for the copyright rule, not included) and
a handful of pages for the gates.

## What the build produced

- 1551 laws, 30062 section and schedule files, 8579 history notes, 5790 "Amended by" entries.
- 1552 commits: 1551 consolidated (one per law, by the publisher) and one documentation commit.
- Consolidation days from 2006-06-07 to 2026-10-21.

## Checks

```sh
git rev-list --merges --count main                      # 0
git log --format=%B main | tr -cd '\r' | wc -c          # 0
python tools/in_force_on.py 2026-10-29 motor-car-act-1951 section-7A
```
