# Problem Radar

Problem Radar finds recurring, software-solvable problems in Reddit
discussions. It searches for relevant posts, asks Gemini to group repeated
frustrations, and presents product opportunities in either the terminal or a
local browser UI.

Each report includes a problem description, a concrete software opportunity,
the people affected, current workarounds, an opportunity score, and supporting
discussions.

## Quick start

Problem Radar has two workflows.

### Manual workflow

Use this when you want to paste the generated prompt into any LLM yourself.
It requires only Python 3.10 or later.

```bash
# Search Reddit and create posts.json plus prompt.txt
python3 main.py generate "apartment hunting" --signals

# Paste prompt.txt into an LLM, save its JSON reply as response.txt, then:
python3 main.py parse response.txt
```

`generate` writes `posts.json` and `prompt.txt` to the current folder. The
posts file lets the parser show the original post titles in the final report.

### Automated Gemini workflow

Use this to search, analyze, and print a report in one command.

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="your_api_key_here"
python3 main.py run "apartment hunting"
```

The `run` command keeps the posts, prompt, and Gemini response in memory. It
prints the result to the console and does not create `posts.json`, `prompt.txt`,
or archive files.

### Local web UI

The browser UI uses the same live Reddit → Gemini pipeline as `run`, while
adding search history and a mobile-first results experience.

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="your_api_key_here"
python3 web.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Enter a topic, wait for
the analysis to finish, then open a ranked problem to see its proposed software
solution first. The results remain in rank order as details expand in place.

The browser offers three search lenses:

- **Basic** — a broad Reddit search for the topic, followed by Gemini analysis.
- **Custom** — up to three user-entered refinement terms for a more focused
  Reddit query.
- **Smart** — Gemini chooses up to three topic-specific search signals before
  Reddit is searched. This uses one extra Gemini request.

The loading screen shows actual pipeline stages and the Custom or Smart terms
being used. Completed searches are saved locally in
`problem_radar_history.json` (which is ignored by Git), can be reopened from
the History drawer, and can be deleted there one at a time.

## Commands

```bash
# Broad Reddit search and prompt generation
python3 main.py generate "tracking subscriptions"

# Search with problem-signal keywords such as “wish” and “frustrating”
python3 main.py generate "apartment hunting" --signals

# Limit a search to one subreddit
python3 main.py generate "apartment hunting" --subreddit=NYCapartments

# Analyze an existing manual LLM response
python3 main.py parse response.txt

# Print a raw JSON report instead of the formatted report
python3 main.py parse response.txt --json
python3 main.py run "apartment hunting" --json
```

`run-api` is also supported as an alias for `run`.

## How it works

1. Problem Radar searches Reddit’s public RSS feeds for posts about a topic.
2. It sends the posts to Gemini, or creates a prompt for you to use with an
   LLM manually.
3. Gemini returns only recurring problems for which software can meaningfully
   address the core outcome; it excludes primarily physical, policy, or
   compliance problems.
4. Problem Radar ranks the opportunities and presents the results in the CLI
   or browser UI.

The automated workflow uses the default model configured in `analyzer.py`:
`gemini-3.1-flash-lite`.

## Project files

- `main.py` — command-line interface and report formatting.
- `web.py` — local HTTP server that exposes the existing automated pipeline to
  the browser UI.
- `static/` — mobile-first HTML, CSS, JavaScript, and Figma-exported icons.
- `reddit_client.py` — Reddit RSS search and problem-signal queries.
- `analyzer.py` — prompt construction, Gemini integration, and response parsing.
- `models.py` — post and problem data models.
- `mock_data.py` — sample posts used as a fallback when parsing a response
  without a matching `posts.json` file.

## Notes

- Reddit search results and availability can vary, and anonymous RSS requests
  can be rate-limited.
- The manual workflow does not need an API key or third-party Python package.
- The automated workflow requires the `google-genai` package and a Gemini API
  key.
- Keep `GEMINI_API_KEY` in your shell environment or another secret manager;
  do not commit it to the repository.
