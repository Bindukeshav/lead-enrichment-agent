# Autonomous Lead Enrichment Agent

A Python agent that takes a list of company domains, crawls their public
web presence with a headless browser, and uses an LLM to extract structured
company/lead intelligence (overview, ICP, contacts, team, confidence score).

## Architecture

```
main.py                 CLI entry point
src/
  scraper.py             Playwright-based crawler: homepage + relevant
                          subpages (about/team/contact/pricing), JS-rendered
  cleaner.py              Strips scripts/styles/nav/footer, converts to
                          markdown, caps size per page to control token spend
  extractor.py            Groq + Instructor structured-output extraction,
                          with token usage / estimated cost tracking
  search_fallback.py      Optional: Tavily search to fill in missing
                          founder LinkedIn URLs
  agent.py                Orchestrates the above per domain, with
                          per-domain error isolation (one failure never
                          kills the whole run)
  models.py                Pydantic schemas for the structured output
```

## Setup

1. **Clone and create a virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   Then edit `.env` and add your `GROQ_API_KEY` (free tier available at
   https://console.groq.com). `TAVILY_API_KEY` is optional, only needed for
   the `--linkedin-fallback` bonus feature.

## Run

```bash
python main.py --domains postman.com supabase.com vapi.ai --format json
```

Options:
- `--format json|csv` — output format (default: json)
- `--out path/to/file` — custom output path (default: `output/output.<format>`)
- `--linkedin-fallback` — use Tavily to search for missing founder LinkedIn URLs
- `--verbose` — debug-level logging

Output is written to `output/output.json` (or `.csv`), and a run summary
(successes/failures/token usage) is printed to the terminal.

Domains are processed **concurrently** (bounded thread pool, default 3
workers) since scraping + LLM calls are I/O-bound — a 3-domain run finishes
in roughly the time of the slowest single domain, not the sum of all three.

### Visual dashboard (optional)

```bash
streamlit run dashboard.py
```
Opens a browser view of `output/output.json` — confidence scores, contacts,
and team members per domain, instead of reading raw JSON.

## Design notes

- **Token optimization**: raw HTML is never sent to the LLM. `cleaner.py`
  strips `<script>`, `<style>`, `<svg>`, `<nav>`, `<footer>`, `<form>` tags,
  converts to markdown, and caps each page's contribution to ~6000 chars
  before it's combined into the LLM context.
- **Structured outputs**: extraction uses `instructor` + Groq's tool-calling
  to guarantee the response matches the `LeadEnrichmentResult` Pydantic
  schema — no manual JSON parsing/regex.
- **Resilience**: every domain is processed inside its own try/except at
  both the fetch and extract stages. A 404, bot block, or timeout on one
  domain is logged as a `ScrapeError` and the pipeline continues to the
  next domain rather than crashing.
- **Cost tracking**: token counts and an estimated USD cost (based on
  configurable per-1M-token pricing) are tracked per extraction and
  summarized at the end of the run.

## Sample output

See `output/sample_output.json` for the expected shape of a real run
against the three test domains (`postman.com`, `supabase.com`, `vapi.ai`).

## Known limitations

- Sites with aggressive bot-detection (Cloudflare challenges, etc.) may
  block the headless browser; these are caught and reported as
  `ScrapeError`s rather than crashing the run.
- LinkedIn URL discovery relies on either the page content itself or the
  optional Tavily fallback — it does not scrape LinkedIn directly.
