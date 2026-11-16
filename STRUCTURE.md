# Structure

One folder per law, by type and year; one file per section or schedule. No folder holds more than 1,000 entries.

```
constitution/                                  Bermuda Constitution Order 1968: the Constitution (Schedule 2) at the top
constitution/order/                            the Order's own sections
acts/<year>/<number>-<short title>/            Acts (PDF subject "Statute"); e.g. acts/1981/59-companies/
statutory-instruments/<year>/<number>-<short title>/
                                               regulations, rules, orders and notices; e.g. statutory-instruments/2017/br-99-...
data/                                          tables: amendments, amended-by, catalogue, paths, source sha256, unreadable
laws.csv                                       every law held: title, number, folder, consolidation day, source
corpus.json                                    bm/national/acts, read by lexifina/global-law
```

- `<year>` is the year in the law's title (the Act's year), else the year folder Bermuda Laws Online files it under,
  else `undated`.
- `<number>` is the Act number (`59` for 1981 : 59) or the statutory instrument number (`br-99` for BR 99 / 2017,
  `gn-…` for a Government Notice). The older laws of the 1989 Revision print no number; their folder has none.
- `<short title>` is the title in lower case with hyphens, without its closing "Act <year>" or "<year>".
- `data/paths.json` maps each law's id (its title as a slug, the name of its folder in the build) to its folder.

Inside a law's folder: `title.md` (title and number), `contents.md` (the printed table of contents), one
`section-<n>.md` per section (`section-12A.md`), one `schedule-<n>.md` per schedule, `end.md` (assent and operation
dates and the "Amended by" list) and `index.txt` (the files in printed order). One paragraph per line; each history
note printed under a section (`[Section 12 amended by 2019 : 39 s. 2 effective 1 January 2020]`) is a line of its own.

## Commits

One commit per consolidation of a law, dated noon Bermuda time on the day its consolidated PDF was produced (the
PDF's CreationDate), with these trailers:

- `In-force:` that day, and `In-force-basis:` saying so: the text is the law as amended up to that consolidation;
- `Consolidated:`, `Date-source: pdf-created`, `Law:`, `Number:`, `Latest-note-effective:` (the newest day a
  history note gives), `Source:` (the PDF), `Law-id:` and `Path:`;
- the author is the last amending law in the law's "Amended by" list (`1988 : 19 (latest amending law listed)`),
  or the law itself when it lists none (`Author-basis:` says which).

Bermuda Laws Online keeps only the current consolidation of each law, so each law has one version so far; a later
consolidation will be a new commit on top. main is append-only: never rewritten, never force-pushed.
