# Problem Radar

A mobile-friendly web app for discovering real problems from Reddit discussions
and exploring software opportunities worth building.

**[Try the live demo](https://problem-radar-w1zr.onrender.com)**

## What it does

Enter a topic, and Problem Radar searches public Reddit posts and uses AI
analysis to identify recurring frustrations. Each radar presents up to three
ranked opportunities, with descriptions, potential software solutions, current
workarounds, and links to the original discussions.

- **Basic search:** explore a topic directly.
- **Custom search:** refine a topic with up to three focus terms.
- **Smart signals:** let the selected AI route choose relevant search terms.
- **History and Saved Ideas:** reopen searches and keep interesting opportunities.
- **Mobile-friendly interface:** follow search progress and share the app.

Results are a starting point for further research, not proof of market demand.

## Built with

Python, vanilla JavaScript, HTML/CSS, Reddit RSS, GroqCloud, and Google Gemini.
Hosted on Render, with Groq GPT-OSS 120B as the default model and GPT-OSS 20B
as its automatic fallback. Gemini 3.1 Flash-Lite and Gemini 3.6 Flash remain
available as direct selections.

## Run locally

Requires Python 3.11 or later and a Groq API key for the default route. A Gemini
API key is optional and enables the two manual Gemini choices.

```bash
git clone https://github.com/colebr11/ProblemRadar.git
cd ProblemRadar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY="your_groq_api_key_here"
export GEMINI_API_KEY="your_api_key_here"
python3 web.py
```

Open [localhost:8000](http://127.0.0.1:8000). Keep your API key private and out
of version control.

## Demo notes

- The free Render service may take about a minute to wake after inactivity.
- Each network visitor can complete three searches per 15 minutes. Failed
  searches do not count. Reddit cooldowns show a retry countdown; service
  limits or outages may temporarily prevent results.
- Every model analyzes the same 25 highest-ranked discussions. Groq uses
  shorter excerpts as an additional safeguard for its free-tier token allowance.
- The default route tries GPT-OSS 120B first and automatically continues with
  GPT-OSS 20B after a temporary overload, rate limit, timeout, or server error.
  It does not automatically switch to Gemini.
- Search topics are sent to Reddit and the selected AI provider. API keys stay
  on the server.
- History and Saved Ideas stay in your browser, survive refreshes, and do not
  sync across devices. Clearing browser storage removes them.

## Development

The search pipeline lives in `reddit_client.py` and `analyzer.py`; `web.py`
serves the interface in `static/`.

Run the automated checks with:

```bash
python3 -m unittest discover -s tests
node --check static/app.js
```
