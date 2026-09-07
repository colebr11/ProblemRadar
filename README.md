# Problem Radar

Problem Radar finds recurring, software-solvable problems in Reddit
discussions. It searches relevant public posts, asks Gemini to identify repeated
frustrations, and turns the strongest themes into ranked software opportunities.

**Live demo:** [Open Problem Radar](https://problem-radar-w1zr.onrender.com)

> The demo runs on Render's free hosting tier. After a period of inactivity,
> the first visit can take about a minute while the service wakes up.

Each completed radar includes a concise problem description, a specific
software opportunity, the people affected, current workarounds, an opportunity
score, and links to representative discussions.

## Features

- Three search lenses:
  - **Basic** searches Reddit broadly for the entered topic.
  - **Custom** adds up to three user-provided focus terms.
  - **Smart** asks Gemini to choose up to three problem-oriented search signals.
- Gemini 3.6 Flash analysis, with Gemini 3.1 Flash-Lite as a faster alternative.
- Up to three ranked, software-solvable opportunities per radar.
- Expandable evidence links to the original Reddit discussions.
- Browser-private History and Saved Ideas with no account or database required.
- Mobile-first interface with clear loading stages and recovery screens.
- Separate handling for Reddit rate limits, Gemini quota limits, and temporary
  Gemini availability issues.
- CLI workflows for automated Gemini analysis or manual use with another LLM.

## How it works

1. Problem Radar makes one Reddit RSS search query and collects up to 75
   relevant posts, retrying that request only when Reddit rate-limits it.
2. Basic searches use the topic directly. Custom searches add user-provided
   terms, while Smart searches use one preliminary Gemini request to select
   topic-specific problem signals.
3. The app sends capped post excerpts to Gemini: no more than 1,500 body
   characters per post and 60,000 body characters per radar.
4. Gemini identifies recurring problems, proposes credible software
   opportunities, and scores the three strongest results.
5. The browser presents the ranked results and stores completed History and
   Saved Ideas in that browser only.

## Run locally

### Requirements

- Python 3.10 or later
- A Gemini API key for the automated CLI and browser UI

### Browser UI

```bash
git clone https://github.com/colebr11/ProblemRadar.git
cd ProblemRadar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY="your_api_key_here"
python3 web.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000), enter a topic, and
optionally open **Advanced search tools** to select a model, add Custom terms,
or enable Smart Signals.

Keep `GEMINI_API_KEY` in your environment or another secret manager. Never
commit it to the repository.

### Automated CLI

Search Reddit, analyze the posts with Gemini, and print the report:

```bash
python3 main.py run "apartment hunting"
python3 main.py run "apartment hunting" --subreddit=NYCapartments
python3 main.py run "apartment hunting" --json
```

`run-api` is supported as an alias for `run`. The automated command keeps the
posts, prompt, and Gemini response in memory; it does not create root output or
archive files.

### Manual CLI

The manual workflow requires only Python. It creates a self-contained prompt
that you can paste into an LLM yourself:

```bash
python3 main.py generate "apartment hunting" --signals

# Paste prompt.txt into an LLM and save its JSON response as response.txt.
python3 main.py parse response.txt
```

`generate` writes `posts.json` and `prompt.txt` to the current directory. The
posts file allows `parse` to connect the model's findings to the original post
titles.

## Public demo behavior

- The demo allows up to three searches per network visitor in each 15-minute
  window to protect the shared API quota.
- Reddit may temporarily limit anonymous RSS searches. Problem Radar retries
  before showing a Reddit-specific recovery screen and displays Reddit's wait
  estimate when one is provided.
- Gemini quota and temporary high-demand errors have separate recovery screens.
- History stores up to 20 completed radars and Saved Ideas stores up to 50
  opportunities. New items replace the oldest when a collection is full.
- History and Saved Ideas use browser `localStorage`. They persist through page
  refreshes and Render restarts, but do not sync across browsers or devices.
- The free Render service spins down after inactivity, so the first visit after
  a quiet period can have a cold-start delay.

## Tech stack

- Python standard-library HTTP server and background job handling
- Reddit public RSS search
- Google Gemini through the official `google-genai` SDK
- Vanilla HTML, CSS, and JavaScript
- Browser `localStorage` for private client-side persistence
- Render for the public web service

## Project structure

- `main.py` — CLI commands and report formatting
- `web.py` — browser server and public-demo request handling
- `reddit_client.py` — Reddit RSS retrieval and problem-signal queries
- `analyzer.py` — prompt construction, Gemini integration, and response parsing
- `models.py` — post and problem data models
- `static/` — browser interface and visual assets
- `tests/` — focused automated coverage for the public-demo pipeline
- `archives/` — preserved example datasets and responses from development
- `sprints/` — project progress summaries and design decisions

## Validation

```bash
python3 -m unittest tests/test_model_selection.py
python3 -m py_compile main.py web.py analyzer.py reddit_client.py models.py mock_data.py
node --check static/app.js
```

The current suite covers model validation, selected-model wiring, prompt caps,
public-demo limits, background-job cleanup, deployment binding, safe error
handling, and distinct Reddit and Gemini failure paths.
