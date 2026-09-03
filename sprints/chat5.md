# Chat 5 Summary — Problem Radar

## Overview

Chat 5 prepared Problem Radar for a small public demo while keeping it a
personal portfolio project rather than turning it into a full product. The
biggest changes focused on making the browser experience clearer, more useful,
and more resilient when Gemini is slow, busy, or temporarily unavailable.

## Completed work

### Gemini model choice and clearer results

- Added an **Analysis model** selector under **Advanced search tools**.
- The available choices are Gemini 3.7 Flash, Gemini 3.6 Flash (the default),
  and Gemini 3.1 Flash-Lite.
- The selected model is used for both Smart Signals and opportunity analysis.
- Each completed radar displays its model and retains it in History and Saved
  Ideas, making results easier to compare later.
- Removed the unused source-selection interface and the redundant visible
  Reddit label from result metadata. Reddit remains the single discussion
  source today.

### Better recovery when Gemini cannot finish

- Reduced each completed radar to the three strongest opportunities, preventing
  Gemini responses from being cut off by overly long JSON output.
- Added a helpful screen when Gemini reaches a temporary quota limit, with a
  direct option to switch models.
- Added a separate helpful screen for Gemini's temporary high-demand errors,
  again encouraging the visitor to try another model or retry shortly.
- Kept the selected topic available when one of those errors occurs, so a
  visitor does not need to retype it.

### Browser-first History and Saved Ideas

- Moved History and Saved Ideas from server files to the current browser's
  local storage.
- History is limited to 20 completed radars; Saved Ideas is limited to 50
  opportunities. The app explains both limits where they appear.
- New items replace the oldest item when a collection reaches its limit.
- This keeps one visitor's History and Saved Ideas private from other visitors
  without needing accounts or a database.

### Public-demo guardrails

- Added a public-demo allowance of three searches per visitor every 15 minutes.
- The app shows a clear wait screen when that allowance is reached instead of a
  confusing generic failure.
- Limited the Reddit text sent to Gemini to 1,500 body characters per post and
  60,000 body characters per radar, while preserving the full post data for
  the results screen.

### Reliability and cleanup

- Updated the server to use a hosting platform's assigned port when one is
  provided, while staying local-only during normal development.
- Completed and failed temporary search jobs now clear from server memory after
  15 minutes. This does not delete browser History or Saved Ideas.
- Unexpected server errors now write detailed private tracebacks to server
  logs, while visitors receive a simple retry message.

## Validation

- Ran Python compilation, JavaScript syntax, and clean-diff checks.
- Added focused automated coverage for the model allowlist, selected-model
  pipeline, output caps, input caps, rate limit, temporary-job cleanup,
  friendly Gemini errors, host-port behavior, and private error logging.
- All 9 automated tests pass.
- Manually confirmed successful radars with Gemini 3.6 Flash and Gemini 3.7
  Flash, including their model labels in the results and History.

## Current usage

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="your_api_key_here"
python3 web.py
```

Open `http://127.0.0.1:8000`, enter a topic, and optionally open **Advanced
search tools** to choose a model, add Custom terms, or enable Smart Signals.

## Recommended next steps

1. Deploy the browser app on Render and add `GEMINI_API_KEY` as a private
   environment variable.
2. Run a complete public-link testing pass: test Basic, Custom, and Smart
   searches; complete a radar with each Gemini model; confirm the model label
   in results and History; and verify Saved Ideas, browser refresh, and the
   demo-limit screen. The Gemini model testing was cut short locally, so this
   is the most important remaining validation.
3. **Optional:** import the pre-browser-storage local History into the new
   browser History. It is safe to leave the old local file alone as a backup;
   importing it is only useful if those earlier radars are worth keeping.
4. Capture a few polished screenshots and write the personal-project post.
