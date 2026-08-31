# Chat 4 Summary — Problem Radar

## Overview

Chat 4 focused on making Problem Radar's existing Reddit-to-app-idea workflow
more useful and polished without adding new data-source costs or extra Reddit
requests. The project now gathers a larger single-request sample, uses a more
intentional Smart Signals prompt, handles Gemini JSON responses more reliably,
and has a cleaner mobile-first search and history experience.

## Completed work

### Stronger single-request Reddit search

- Increased the default radar sample from 50 to **75 posts**.
- Kept each radar to one Reddit RSS request, avoiding extra rate-limit pressure.
- Updated Smart and Custom searches so the topic can match a post title or body
  rather than requiring a title-only match.
- Ranked the returned posts locally for topical and problem-signal relevance.
- Disabled the automatic broad-search fallback by default so a thin result set
  does not silently make a second Reddit request.

### Smarter software-problem signals

- Reworked the Smart Signals prompt to choose short terms likely to appear in
  real Reddit complaints.
- Added an explicit requirement that the repeated problem should be one that
  software could plausibly improve.
- Kept Smart Signals to one additional Gemini request only; Basic and Custom
  searches do not make that preliminary Gemini request.

### More reliable Gemini analysis

- Switched the default model to `gemini-3.6-flash`.
- Limited the analysis to the five strongest recurring opportunities so long
  responses are less likely to be truncated.
- Made response parsing tolerant of Gemini's occasional invalid escaped
  field-name underscores, such as `post\_count`.
- Strengthened truncation detection so incomplete responses surface as a useful
  model-output error instead of a misleading generic parsing failure.

### Search and history UI polish

- Moved Source, Custom terms, and Smart Signals into a collapsed **Advanced
  search tools** section, keeping the default search screen simple.
- Kept Reddit as the active consumer source while preserving the source-choice
  structure for a future supported addition.
- Made the History drawer's list independently scrollable while its header and
  help action remain visible.
- Fixed compact-screen details: the Problem Radar wordmark no longer wraps,
  the main search placeholder fits smaller screens, and the advanced controls
  do not overflow horizontally.

### Validation

- Verified Python modules with `py_compile`.
- Verified frontend JavaScript syntax and clean patch formatting.
- Visually checked the home screen, expanded Advanced search tools, responsive
  phone layout, and a populated, scrollable History drawer in the local app.
- Verified the 75-post limit reaches the browser analysis pipeline without
  needing a live Reddit request during validation.

## Current usage

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="your_api_key_here"
python3 web.py
```

Open `http://127.0.0.1:8000`, enter a consumer topic, and optionally open
**Advanced search tools** to add Custom terms or enable Smart Signals. Each
radar uses one Reddit RSS request and analyzes up to 75 returned posts with
Gemini 3.6 Flash.

## Recommended next steps

1. **Validate search quality** — test a small set of consumer topics and keep
   notes on whether the top opportunities are specific, evidence-backed, and
   genuinely software-solvable. Add the planned repeated natural-phrase
   extraction only after this baseline is understood.
2. **Accounts** — add account creation and sign-in when users need their saved
   ideas and radar history to follow them across devices.
3. **Real persistence** — move local History and Saved Ideas storage to
   Supabase or another production database, with user-owned records and clear
   retention rules.
4. **Deployment** — host the app on a persistent server with environment-based
   secrets, request handling, observability, and safeguards around Reddit rate
   limits and Gemini errors.
5. **Evidence clarity** — make repeated consumer wording and cross-subreddit
   support more visible in each opportunity without overwhelming the app idea.
