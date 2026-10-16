# Chat 7 Summary — GroqCloud Integration

## Overview

Chat 7 added GroqCloud as Problem Radar's default AI provider while preserving
the existing Gemini choices. The default route now uses OpenAI GPT-OSS 120B on
Groq and automatically continues with GPT-OSS 20B when the larger model is
temporarily unavailable. Gemini remains available only when a visitor selects
it directly.

## Completed work

### Groq-first analysis

- Added Groq's official Python SDK and the server-side `GROQ_API_KEY`
  configuration.
- Made `openai/gpt-oss-120b` the default analysis model.
- Reused the existing Problem Radar system prompt, JSON parser, and result
  model instead of changing the Reddit or opportunity-ranking pipeline.
- Kept the API keys on the server and out of browser responses and project
  files.

### Automatic 120B-to-20B fallback

- Added `openai/gpt-oss-20b` as an internal automatic fallback for the default
  Groq route.
- Temporary 120B overloads, rate limits, timeouts, connection failures, server
  errors, truncated responses, and unusable JSON can continue through 20B
  without ending the search.
- Missing or rejected credentials and other configuration problems are not
  hidden by automatic fallback.
- Removed Gemini from the automatic fallback chain. Gemini 3.1 Flash-Lite and
  Gemini 3.6 Flash remain available as direct selections under Advanced search
  tools.
- Completed radars record the provider and model that actually produced the
  analysis. A 20B result is labeled as a fallback in Results, History, and Saved
  Ideas.

### Visible fallback progress and cooldowns

- The loading screen reports when GPT-OSS 120B is unavailable and Problem
  Radar continues with GPT-OSS 20B.
- Added a short, model-specific Groq cooldown that honors a numeric
  `Retry-After` response when available and otherwise uses a bounded fallback
  delay.
- A cooling-down 120B model is skipped temporarily so searches can proceed to
  20B without repeating the same failed request.
- Smart Signals uses the same 120B-to-20B sequence. If both Groq models fail to
  produce signals, the existing built-in problem terms keep the Reddit search
  moving.

### Consistent analysis set

- Reddit can still return up to 75 discussions for local relevance ranking and
  evidence links.
- Every selectable model analyzes the same 25 highest-ranked discussions.
- Groq uses shorter post excerpts and low reasoning effort to stay within its
  free-tier token allowance; direct Gemini analysis keeps its existing excerpt
  size.
- Basic search uses Reddit's relevance order. Custom and Smart searches add the
  existing local score for topic and signal matches before taking the first 25.

### Interface and documentation

- Simplified the default selector label to **Groq GPT-OSS 120B — Default**.
- Kept the 20B fallback out of the selector because it is an internal recovery
  path, not a separate user choice.
- Updated the About screen, provider error screen, local setup instructions,
  environment example, and README provider descriptions.
- Preserved compatibility with older browser History and Saved Ideas records
  that contain only Gemini model metadata.

## Configuration

Install dependencies and set the Groq key before starting the local web app:

```bash
pip install -r requirements.txt
export GROQ_API_KEY="your_groq_api_key_here"
python3 web.py
```

`GEMINI_API_KEY` is optional and is used only when Gemini 3.1 Flash-Lite or
Gemini 3.6 Flash is selected directly.

## Validation

- Automated tests cover Groq primary success, 120B-to-20B fallback, cooldown
  routing, Smart Signal fallback, direct Gemini selection, the shared 25-post
  limit, provider metadata, and private public-facing errors.
- Python compilation, frontend JavaScript syntax validation, and clean-diff
  validation are run before release.
- A live local Groq 120B radar completed quickly and returned useful results.

## Git and deployment status

- The Chat 7 changes are included in the Groq provider-routing update.
- `GROQ_API_KEY` has been added through Render's private environment settings.
- The commit still needs to be pushed before Render can deploy this version.

## Remaining wrap-up

1. Run a final local Basic and Smart radar with the Groq route.
2. Confirm the visible 20B fallback using a controlled test or temporary model
   failure rather than waiting for a real overload.
3. Push the approved commit and wait for Render's automatic deployment.
4. Verify the deployed default route and manual Gemini choices.
