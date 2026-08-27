# Chat 2 Summary — Problem Radar

## Overview

Chat 2 moved Problem Radar from a manual proof of concept to an automated
command-line workflow. It added live Reddit search, Gemini analysis, smarter
search signals, and archived example datasets.

## Completed work

### Automated `run` command

`python3 main.py run "topic"` now fetches Reddit posts, analyzes them with
Gemini, and prints a formatted report or JSON.

- Requires `GEMINI_API_KEY` and `google-genai`.
- Uses signal-based Reddit searching by default.
- Supports `--subreddit=<name>` and `--json`.
- Keeps the posts, prompt, and Gemini response in memory. It does not create
  root output files or new archive files.

### Better Reddit searches

- Added a Boolean signal query using frustration and unmet-need keywords.
- Added topic-specific signal keywords from Gemini when an API key is
  available, with built-in keywords as a fallback.
- Added a broad-search fallback for thin single-word signal searches.
- Filtered several noisy subreddits from results.

### Parsing and data handling

- `parse` can match an archived response file with its corresponding posts
  file, then falls back to `posts.json` or mock data when necessary.
- Added `Post` and `Problem` data models, prompt construction, JSON response
  parsing, and clear errors for missing Gemini credentials or truncated output.

### Example datasets

Historical test datasets are preserved in `archives/` for subscriptions,
apartment hunting, study tips, finding friends, and cooking. They are examples
only; new `run` commands do not add to this folder.

## Current commands

```bash
# Automated: Reddit search → Gemini analysis → console report
python3 main.py run "study tips"
python3 main.py run "apartment hunting" --subreddit=NYCapartments
python3 main.py run "finding friends" --json

# Manual: writes posts.json and prompt.txt for an LLM you use yourself
python3 main.py generate "apartment hunting" --signals
python3 main.py parse response.txt

# Parse a historical archived result
python3 main.py parse archives/finding_friends_20260826_163453_response.txt
```

## Follow-up cleanup completed after Chat 2

- Removed automatic root-file and timestamped archive writing from `run`.
- Deleted the obsolete archive-path helper.
- Simplified and corrected the README.
- Fixed manual signal searches so they work without Gemini installed or an API
  key.
- Ignored PyCharm settings and generated manual-workflow files in Git.

## Next step: Chat 3

Build a simple web dashboard where a user can enter a topic, optionally choose
a subreddit, run the analysis, and browse problem cards with scores and
representative Reddit posts.
