# Problem Radar

A high-performance CLI tool and AI pipeline that feeds **live Reddit discussion data into Gemini LLMs to surface genuinely recurring software opportunities, unmet needs, and high-friction user pain points**, complete with opportunity scoring, pain ratings, and representative post references.

---

## 🏗️ Architecture & Data Flow

```
Reddit RSS Search API (1 Request, High-Intent Boolean Signals)
                       │
                       ▼
               reddit_client.py ──► models.save_posts() ──► posts.json
                       │
                       ▼
                  analyzer.py ──► prompt.txt
                       │
                       ▼
              (Gemini 3.6 Flash / LLM) ──► response.txt
                       │
                       ▼
             main.py parse ──► Formatted Problem Report (or JSON)
```

### Core Components
* **[`models.py`](file:///Users/bcole/Downloads/Projects/problem_radar/models.py)**: Data contracts for `Post` and `Problem`, plus `save_posts()` and `load_posts()` for local JSON serialization.
* **[`reddit_client.py`](file:///Users/bcole/Downloads/Projects/problem_radar/reddit_client.py)**: High-performance, single-request Reddit RSS search engine. Supports Boolean intent queries (`--signals`), subreddit filtering (`--subreddit`), and automated noise filtering.
* **[`analyzer.py`](file:///Users/bcole/Downloads/Projects/problem_radar/analyzer.py)**: Prompt engineering instructions (`build_full_prompt`), response JSON parser (`parse_response`), and automated Gemini API client (`analyze_posts_via_api`).
* **[`main.py`](file:///Users/bcole/Downloads/Projects/problem_radar/main.py)**: CLI entry point supporting `generate`, `--signals`, `--subreddit`, `parse`, and automated Gemini `run` (`run-api` retained for compatibility).
* **[`archives/`](file:///Users/bcole/Downloads/Projects/problem_radar/archives)**: Storage directory for past test runs and benchmark datasets.

---

## ✨ Key Features

* 🚀 **1-Request Boolean Signal Search**: Combines search topics with frustration keywords (`wish`, `track`, `annoying`, `alternative`, `recommend`, `frustrating`, `hate`) in **1 single HTTP call**, completing in <2 seconds with **0 HTTP 429 rate limit risk**.
* 🧹 **Automated Noise Subreddit Filtering**: Automatically excludes non-software mega-repost subreddits (`r/BestofRedditorUpdates`, `r/movies`, `r/AITAH`, `r/natureismetal`) to ensure high-density, relevant datasets.
* 💾 **Local Post Persistence**: Automatically saves real Reddit posts to `posts.json` and infers matching archives during parsing.
* 📊 **Structured Problem Reports**: Outputs recurring problem clusters with Pain Levels (1–10), Opportunity Scores (1–100), Target Audiences, Existing Workarounds, and representative Reddit post titles/IDs.

---

## 🚀 Getting Started

No third-party packages are required for the default manual CLI — built using standard-library Python 3.10+.

### 1. Generate Prompt from Live Reddit Search

```bash
# Broad search (default topic: "tracking subscriptions")
python3 main.py generate "tracking subscriptions"

# High-intent Boolean problem signal search (Recommended)
python3 main.py generate "apartment hunting" --signals

# Subreddit-targeted search
python3 main.py generate "apartment hunting" --subreddit=NYCapartments
```

This fetches real posts, saves them to `posts.json`, and writes `prompt.txt`.

### 2. Run AI Analysis (Manual Workflow)

1. Open your preferred LLM chat interface.
2. Paste the entire contents of `prompt.txt`.
3. Copy the reply (JSON array) and save it to `response.txt`.

### 3. Parse & Display Report

```bash
# Formatted CLI report
python3 main.py parse response.txt

# Parse past archived test runs
python3 main.py parse archives/apartment_hunting_signals_response.txt

# Export raw JSON
python3 main.py parse response.txt --json
```

---

## 🤖 Automated Gemini Workflow

Install dependencies and create an API key in [Google AI Studio](https://aistudio.google.com/apikey). Then set it in your shell environment:

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="your_api_key_here"
python3 main.py run "apartment hunting"
```

The `run` command collects live posts, sends the structured analysis prompt directly to Gemini, parses its JSON response, and prints the formatted problem report in a single automated step. `run-api` is retained as a compatibility alias.

> [!NOTE]
> The default model is **`gemini-3.6-flash`**, providing high speed and structured outputs.

---

## 📂 Past Test Archives (`archives/`)

| Test Topic | Search Strategy | Archived Response File |
| :--- | :--- | :--- |
| **Subscriptions** | Plain Search | [`archives/subscriptions_response.txt`](file:///Users/bcole/Downloads/Projects/problem_radar/archives/subscriptions_response.txt) |
| **Apartment Hunting** | Plain Search (Baseline) | [`archives/apartment_hunting_response.txt`](file:///Users/bcole/Downloads/Projects/problem_radar/archives/apartment_hunting_response.txt) |
| **Apartment Hunting** | High-Intent Signals | [`archives/apartment_hunting_signals_response.txt`](file:///Users/bcole/Downloads/Projects/problem_radar/archives/apartment_hunting_signals_response.txt) |

