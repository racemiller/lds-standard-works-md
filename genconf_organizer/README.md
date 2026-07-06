# General Conference → OpenWebUI pipeline

A small toolkit that turns the [`leezorba/generalconference_scraper`](https://github.com/leezorba/generalconference_scraper)
output into clean Markdown for an OpenWebUI knowledge collection.

These scripts do **not** scrape anything themselves — they wrap the scraper's
inputs and clean its outputs. The scraping step in the middle is the archived
`simple_gcscraper_byperiod.py` from that repo (verify it still runs against a
recent and an older conference before a full run, since the repo is read-only).

## Order of operations

1. **Generate the URL list**
   ```bash
   python generate_conference_urls.py --out urls.txt
   ```
   Produces one per-period URL per conference (April/October), 1971 → most
   recent conference that has actually happened. Use `--start-year`,
   `--end-year`, or `--through YYYY/MM` to narrow it.

2. **Run the scraper** (from the leezorba repo) on those URLs, using the
   "simple" path so you get plain JSON/TXT rather than the fine-tuning format.

3. **Convert to Markdown**
   ```bash
   python gc_json_to_markdown.py ./scraper_output --out ./markdown
   ```
   One `.md` per talk: YAML frontmatter (title, speaker, date, conference,
   source, needs_review) plus a plain title/byline header repeated in the body
   so the metadata stays searchable even if OpenWebUI ignores frontmatter. The
   date comes from the year/month in each talk's URL. Talks that look like they
   contain the duplicated-stanza artifact are tagged `needs_review: true`.

4. **Validate (and optionally clean)**
   ```bash
   python validate_talks.py ./markdown                 # report only
   python validate_talks.py ./markdown --fix ./cleaned  # conservative fix copies
   ```
   `--fix` collapses immediately-adjacent duplicate lines/sentences into a new
   directory (never overwrites originals). Anything reported as "still flagged"
   has duplication that's separated by other text — review those by hand.

5. **Ingest** the `markdown/` (or `cleaned/`) folder into your OpenWebUI
   knowledge collection.

## Files

| File | Purpose |
|------|---------|
| `generate_conference_urls.py` | Build the list of conference period URLs |
| `gc_json_to_markdown.py` | Scraper JSON → OpenWebUI Markdown |
| `validate_talks.py` | Flag / conservatively fix duplicated-text artifacts |
| `gc_common.py` | Shared helpers (used by the above) |

## Notes

- Field detection is intentionally forgiving about the scraper's exact key
  names. If a field comes through empty, check `gc_common.py`'s `_FIELD_ALIASES`
  and add the key the scraper actually uses.
- Only the English global site is supported by the upstream scraper.
- Keep the resulting collection private; this is for personal reference, not
  redistribution.
