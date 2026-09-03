# Problem Radar

Problem Radar finds recurring, software-solvable problems in Reddit
discussions. It searches for relevant posts, asks Gemini to group repeated
frustrations, and presents product opportunities in either the terminal or a
browser UI.

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

The `run` command keeps up to 75 posts, the prompt, and Gemini response in
memory. It prints the result to the console and does not create `posts.json`,
`prompt.txt`, or archive files.

### Browser UI

The browser UI uses the same live Reddit → Gemini pipeline as `run`, with a
mobile-first results experience, History, and Saved Ideas.

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
  Reddit is searched. It favors terms associated with repeated, software-solvable
  pain points. This uses one extra Gemini request; Reddit searches still use
  only one RSS request.

Under **Advanced search tools**, you can also choose the Gemini model used for
Smart Signals and opportunity analysis. The app offers a small, server-approved
set of models—Gemini 3.7 Flash, Gemini 3.6 Flash (the default), and Gemini 3.1
Flash-Lite—so each completed radar records the model that produced it and older
saved results remain easy to compare.

Problem Radar uses Reddit as its single discussion source today. Adding other
consumer-discussion sources is a possible future extension, but the current
interface intentionally focuses on one source. Custom terms, Smart Signals,
and model choice are grouped under the collapsible **Advanced search tools**
section on the home screen.

The loading screen shows actual pipeline stages and the Custom or Smart terms
being used. Completed searches and Saved Ideas stay in the current browser,
where they can be reopened or deleted without being shared with other visitors.
History holds up to 20 radars and Saved Ideas holds up to 50 opportunities;
new items replace the oldest when a collection is full.

If Gemini is temporarily busy or a selected model reaches a temporary limit,
the app keeps the topic in place and offers a simple way to switch models or
try again later.

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

1. Problem Radar searches Reddit’s public RSS feeds for up to 75 posts about a
   topic.
2. It sends a capped excerpt of the posts to Gemini—up to 1,500 body characters
   per post and 60,000 body characters per radar—or creates a prompt for you to
   use with an LLM manually.
3. Gemini returns up to three recurring problems for which software can
   meaningfully address the core outcome; it excludes primarily physical,
   policy, or compliance problems.
4. Problem Radar ranks the opportunities and presents the results in the CLI
   or browser UI.

The automated workflow uses the default model configured in `analyzer.py`:
`gemini-3.6-flash`.

## Project files

- `main.py` — command-line interface and report formatting.
- `web.py` — browser server that exposes the existing automated pipeline to
  the UI.
- `static/` — mobile-first HTML, CSS, JavaScript, and Figma-exported icons.
- `reddit_client.py` — Reddit RSS search and problem-signal queries.
- `analyzer.py` — prompt construction, Gemini integration, and response parsing.
- `models.py` — post and problem data models.
- `mock_data.py` — sample posts used as a fallback when parsing a response
  without a matching `posts.json` file.

## Notes

- Each radar makes one Reddit RSS request. Results can still be rate-limited
  by Reddit, so the app does not send follow-up Reddit searches automatically.
- The manual workflow does not need an API key or third-party Python package.
- The automated workflow requires the `google-genai` package and a Gemini API
  key.
- Keep `GEMINI_API_KEY` in your shell environment or another secret manager;
  do not commit it to the repository.
- The public demo allows up to three searches per visitor in each 15-minute
  window to protect the shared Gemini API quota.
- Completed browser searches are stored only in that browser. They are not
  synced across devices or shared with other visitors.
