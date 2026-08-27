# Problem Radar

Problem Radar is a Python command-line tool for finding recurring software
problems in Reddit discussions. It searches for relevant posts, asks an LLM
to group repeated frustrations, and prints product-opportunity reports.

Each report includes a problem description, the people affected, existing
workarounds, a pain level, an opportunity score, and representative posts.

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
3. The LLM returns only repeated problems, not one-off complaints, as
   structured JSON.
4. Problem Radar prints the results as an easy-to-read report or JSON.

The automated workflow uses the default model configured in `analyzer.py`:
`gemini-3.6-flash`.

## Project files

- `main.py` — command-line interface and report formatting.
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
