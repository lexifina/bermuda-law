# Bermuda: law history in git


The law of Bermuda as a git history: one file per section or schedule, one commit per consolidation of a law, and the publisher of that consolidation as the commit's author. Bermuda Laws Online keeps only each law's current consolidation, so each law here has one version for now; later consolidations are added as new commits, and `git log` and `git blame` will then show what each one changed. Picking a date gives the text this record holds that day.

Part of [lexifina/global-law](https://github.com/lexifina/global-law), one git history for every country's law: this is Bermuda's national law, which global-law reads at `bermuda/national/acts/`.

**What is in it now:** six laws, each in its current consolidation, produced between 29 June 2022 and 19 October 2026: the Bermuda Constitution Order 1968, with the Constitution of Bermuda as its Schedule 2; the Interpretation Act 1951; the Motor Car Act 1951; the Bermuda Immigration and Protection Act 1956; the Human Rights Act 1981; and the Employment Act 2000. They make 725 section and schedule files, with the history notes printed under the sections (772 rows naming 174 amending laws, in [`data/amendments.csv`](data/amendments.csv)) and the laws' "Amended by" lists (299 entries, in [`data/amended-by.csv`](data/amended-by.csv)). [`laws.csv`](laws.csv) lists the six laws with their numbers and consolidation days.

Each Act is in `act/<year>/<short title>/`, one file per section or schedule (`act/2000/employment/section-12.md` is section 12, vacation leave, of the Employment Act 2000, 2000 : 38); the Constitution's sections are in `constitution/constitution/` and the Order's own in `constitution/constitution/order/`. Each law's `end.md` holds its "Amended by" list; `data/paths.json` maps each law's id (`employment-act-2000`, its folder before 10 November 2026) to its folder.

The text is in English, as the consolidated PDFs print it, one paragraph per line; each history note (`[Section 12 amended by 2019 : 39 s. 2 effective 1 January 2020]`) is a line of its own.

## Questions as git commands

| Question | Command |
| --- | --- |
| Every change to section 12 of the Employment Act | `git log --follow -p --word-diff -- act/2000/employment/section-12.md` |
| Which consolidation each line of section 12 comes from | `git blame act/2000/employment/section-12.md` |
| Every version of section 12, with its consolidation day | `git log --follow --diff-filter=AM --format="%h %(trailers:key=In-force,valueonly,separator=) %an" -- act/2000/employment/section-12.md` |
| Section 12 as it stood on 14 November 2026 | `python tools/in_force_on.py 2026-11-14 act/2000/employment section-12` |

**Outside git**, we also host this record publicly, for free:

- **[Ask Claude about Bermuda law](https://global-law.lexifina.com/v1/try_claude?country=bermuda)**: opens Claude with a first question ready.
- **[Ask ChatGPT](https://global-law.lexifina.com/v1/try_chatgpt?country=bermuda)**: the same question in ChatGPT.
- **[Call the API in your browser](https://global-law.lexifina.com/v1/search_law?query=vacation+leave&jurisdictions=bermuda)**: a search of Bermuda law for "vacation leave", returned as JSON. See the [documentation here](https://lexifina.com/api/global-law).

Both assistants read the record through the free Global law connector (MCP, `https://global-law.lexifina.com/mcp`); the first time, the chat gives you the link that adds it. Ask in English.

**Host it yourself easily.** All it takes is git and Python, and the tools run on your machine:

```sh
git clone --depth 1 https://github.com/lexifina/global-law && cd global-law
python3 tools/countries.py add bermuda/national/acts
python3 tools/law.py show 2026-11-14 bermuda/national/acts/act/2000/employment/section-12.md
```

Opened in Claude Code, Cursor, VS Code or Codex, the clone also starts a local MCP server with the same tools ([MCP.md](https://github.com/lexifina/global-law/blob/main/MCP.md)).

## Dates

Each commit is dated at noon, Bermuda time, on the day its consolidated PDF was produced, and carries that day in its `In-force:` and `Consolidated:` trailers (`Date-source: pdf-created`):

- it is the day of the consolidation, the law as amended up to then, not the day any amendment took effect;
- the days amendments took effect are in the history notes and `data/amendments.csv`, and each law's latest is in its `Latest-note-effective:` trailer; for all six it is earlier than the commit's day (the Constitution's latest change, by BR 122 / 2017, took effect on 21 August 2020; its PDF was produced on 19 October 2026), and these days are not applied to the commits or to `tools/in_force_on.py`;
- for a day before a law's consolidation, `tools/in_force_on.py` says there is no version, because the source keeps none;
- the site prints text not yet in force in green; none of these six PDFs has any, and the build stops if a later one does.

Every law commit is credited to the publisher, `Attorney-General's Chambers, Bermuda (Bermuda Laws Online)`, with `Kind: consolidated`: no line is credited to an amending law, because without the earlier text nobody can tell which words an amendment wrote. When later consolidations arrive, a change will be credited to an amending law only where a new history note names one.

## How it is checked

- `tools/build/check_text.py` reads every PDF again with poppler's `pdftotext`, not the PyMuPDF reader the build uses: the letters and digits of each law's files, in `index.txt` order, equal those of its PDF, word for word (the crest, running header and page numbers excepted).
- `tools/build/check_repo.py` checks that every trailer parses, every commit carries `In-force:`, there are no merges or carriage returns, dates never go backwards and none is after the build day, and the date tool prints the stored text.
- Two builds from the same PDFs gave the same HEAD, and global-law's `check_corpus.py` passes. [`data/source-sha256.tsv`](data/source-sha256.tsv) lists each PDF's sha256 and address, and [`REPRODUCE.md`](REPRODUCE.md) the steps.

## What it does not show

- **Earlier text.** Bermuda Laws Online keeps no earlier consolidations, so each history starts at the current one. The Annual Laws (Acts and statutory instruments as made, from 1993) are on the site but not used, and no amendment is replayed.
- **The rest of Bermuda's law.** These six laws are a sample: the site lists its consolidated laws only through an interactive search, so each was asked for by its address. No other law and no case law.
- **The Motor Car Act's latest change.** Its text, produced on 16 July 2026, lacks what 2026 : 38 s. 2 changed from 19 October 2026 in seven files: `contents.md`, `end.md` and sections 54, 55, 59, 80 and 86.
- **Formatting.** Italics, bold and the PDF layout are lost; schedule tables are flattened to one line per printed row, so a cell that wraps can come after the next cell.
- **The authoritative text.** The site says its consolidations "are provided for informational purposes only and do not yet have official sanction"; the authoritative text is the 1989 Revised Laws with replacement pages, the Annual Laws and the Gazette.

## Sources

| Source | Kind | Past versions | Notes |
| --- | --- | --- | --- |
| [Bermuda Laws Online](https://www.bermudalaws.bm) (Attorney-General's Chambers) | Consolidated laws, as PDFs | no, only the current consolidation | Each PDF from its own address (`/Laws/Consolidated Law/<year>/<title>`); the history notes and "Amended by" lists name each amending law and the day it took effect |

## Licence

See [`LICENSE`](LICENSE). The legal text is Crown copyright (Copyright and Designs Act 2004, s. 199(1): "Her Majesty is entitled to copyright in every Act of the Legislature"); the site says "This website and its contents are Crown Copyright The Government of Bermuda - All Rights Reserved", sets no terms of use, and has given no licence to reuse it. Lexifina's own contributions (the tools, the arrangement into files, the commit messages and the data tables) are CC0 1.0.

No AI model wrote or changed legal text, and none runs at build time; the scripts were written by an AI model, Claude Opus 5.5 (see [`REPRODUCE.md`](REPRODUCE.md)).

## More

From [lexifina/global-law](https://github.com/lexifina/global-law):

- [FEATURES.md](https://github.com/lexifina/global-law/blob/main/FEATURES.md): every feature, and what every corpus must support (`git blame`, `law.py`, the MCP tools)
- [FAQ.md](https://github.com/lexifina/global-law/blob/main/FAQ.md): questions and answers · [CONTRIBUTING.md](https://github.com/lexifina/global-law/blob/main/CONTRIBUTING.md): proposing changes · [MCP.md](https://github.com/lexifina/global-law/blob/main/MCP.md): the MCP server · [REPRODUCE.md](https://github.com/lexifina/global-law/blob/main/REPRODUCE.md): how it was built · [CHANGELOG.md](https://github.com/lexifina/global-law/blob/main/CHANGELOG.md)
- [FRESHNESS.md](https://github.com/lexifina/global-law/blob/main/FRESHNESS.md): how current each corpus is · [Monitoring](https://github.com/lexifina/global-law/tree/main/monitoring): whether updates are running · [WATCHING.md](https://github.com/lexifina/global-law/blob/main/WATCHING.md): how each official source is watched for changes
- [performance/](https://github.com/lexifina/global-law/tree/main/performance): how fast the tools are, measured
- [visualisations/](https://github.com/lexifina/global-law/tree/main/visualisations): charts and bridges across the world's law
- [Vulnerabilities](https://github.com/lexifina/global-law/tree/main/vulnerabilities): mistakes in legislation as published
