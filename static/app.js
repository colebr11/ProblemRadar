const app = document.querySelector('#app');
const exampleTopics = ['Fitness', 'College Students', 'Subscriptions', 'Travel'];
let history = [];
let savedIdeas = [];
let currentResult = null;
let activeProblem = null;
let closingProblem = null;
let drawerOpen = false;
let view = 'home';
let aboutReturnView = 'home';
let resultsReturnView = 'home';
let homeTopic = '';
let homeModel = 'gemini-3.1-flash-lite';

const analysisModels = {
  'gemini-3.1-flash-lite': 'Gemini 3.1 Flash-Lite',
  'gemini-3.6-flash': 'Gemini 3.6 Flash',
};
const defaultModel = 'gemini-3.1-flash-lite';
const historyStorageKey = 'problem-radar-history-v1';
const savedIdeasStorageKey = 'problem-radar-saved-ideas-v1';
const maxHistoryItems = 20;
const maxSavedIdeas = 50;

const icon = (name, label = '') => `<img src="assets/${name}.svg" alt="${label}" />`;
const escapeHtml = (value = '') => String(value).replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);
const safeExternalUrl = (value) => {
  try {
    const url = new URL(String(value || ''));
    return url.protocol === 'https:' || url.protocol === 'http:' ? escapeHtml(url.href) : '';
  } catch { return ''; }
};

function readStoredList(key, isValidItem) {
  try {
    const stored = JSON.parse(localStorage.getItem(key) || '[]');
    return Array.isArray(stored) ? stored.filter(isValidItem) : [];
  } catch { return []; }
}

function writeStoredList(key, items) {
  try { localStorage.setItem(key, JSON.stringify(items)); return true; } catch { return false; }
}

function isHistoryItem(item) {
  return item && typeof item === 'object' && typeof item.id === 'string' && typeof item.topic === 'string' && Array.isArray(item.problems) && Array.isArray(item.posts);
}

function isSavedIdea(item) {
  return item && typeof item === 'object' && typeof item.id === 'string' && typeof item.key === 'string' && typeof item.topic === 'string' && item.problem && typeof item.problem === 'object';
}

function localId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function formatWait(seconds) {
  const minutes = Math.max(1, Math.ceil(Number(seconds || 0) / 60));
  return `${minutes} minute${minutes === 1 ? '' : 's'}`;
}

function button(className, iconName, label, action) {
  return `<button class="${className}" type="button" aria-label="${label}" data-action="${action}">${icon(iconName)}</button>`;
}

function header(title, leftAction = 'home', right = '') {
  const left = leftAction === 'menu'
    ? button('icon-button', 'menu', 'Open history', 'toggle-drawer')
    : button('icon-button', 'arrow-left', 'Back', leftAction);
  return `<header class="app-header"><div>${leftAction === 'menu' ? `${left}<strong class="wordmark">Problem Radar</strong>` : left}</div><strong class="page-title">${title}</strong>${right || '<span class="header-spacer"></span>'}</header>`;
}

function render() {
  const screens = { home: renderHome, loading: renderLoading, results: renderResults, detail: renderDetail, saved: renderSavedIdeas, about: renderAbout, error: renderError };
  app.innerHTML = `<section class="phone-frame">${screens[view]() }${drawerOpen ? renderDrawer() : ''}</section>`;
  bindEvents();
}

function renderHome() {
  return `<section class="screen home-screen">
    ${header('', 'menu', '<button type="button" class="saved-nav" data-action="saved"><span aria-hidden="true">★</span>Saved ideas</button>')}
    <div class="hero">
      <div class="hero-copy"><p class="eyebrow">Opportunity Finder</p><h1>What problems are worth solving?</h1></div>
      <form id="search-form" class="search-form"><div class="search-box"><img src="assets/search.svg" alt="" /><input id="topic" name="topic" value="${escapeHtml(homeTopic)}" placeholder="Enter a topic or problem…" autocomplete="off" /><button aria-label="Search" type="submit">${icon('arrow-right')}</button></div>
        <details class="advanced-tools"><summary><span>Advanced search tools</span><small>Optional</small><i aria-hidden="true">⌄</i></summary><div class="search-options"><label class="model-picker"><span>Analysis model</span><select name="model" aria-label="Gemini analysis model"><option value="gemini-3.1-flash-lite" ${homeModel === 'gemini-3.1-flash-lite' ? 'selected' : ''}>Gemini 3.1 Flash-Lite — Default · Faster</option><option value="gemini-3.6-flash" ${homeModel === 'gemini-3.6-flash' ? 'selected' : ''}>Gemini 3.6 Flash — More capable · May be slower</option></select><small>3.1 Flash-Lite is the faster default. Choose 3.6 Flash for deeper analysis when available.</small></label><label class="focus-terms"><span>Refine with up to 3 terms <small>optional</small></span><input name="custom-signals" placeholder="e.g. dating apps, lonely, meeting people" autocomplete="off" /></label>
          <label class="smart-toggle"><input type="checkbox" name="smart-signals" /><span aria-hidden="true"></span><b>Smart signals</b><em>Uses one extra Gemini request</em></label>
        </div></details>
      </form>
      <section class="examples"><p>Popular radars this week</p><div>${exampleTopics.map(topic => `<button type="button" class="topic-pill" data-topic="${topic}">${topic}</button>`).join('')}</div></section>
    </div>
  </section>`;
}

function renderLoading() {
  const topic = escapeHtml(currentResult?.topic || 'your topic');
  const job = currentResult?.job || {};
  const stages = job.signal_mode === 'smart'
    ? [['signals', 'Choose signals'], ['searching', 'Search discussions'], ['analyzing', 'Analyze patterns'], ['ranking', 'Rank opportunities']]
    : [['searching', job.signal_mode === 'custom' ? 'Use focus terms' : 'Search discussions'], ['analyzing', 'Analyze patterns'], ['ranking', 'Rank opportunities']];
  const active = Math.max(0, stages.findIndex(([stage]) => stage === job.stage));
  const keywords = (job.keywords || []).map(keyword => `<span>${escapeHtml(keyword)}</span>`).join('');
  return `<section class="screen loading-screen">${header('Analyzing', 'home')}
    <div class="loading-center"><span class="radar-ring">${icon('radar')}</span><div><p class="loading-topic">Building a radar for “${topic}”</p><h1>${escapeHtml(job.message || 'Preparing your search…')}</h1></div>
      <div class="progress-block"><div class="loading-line" aria-label="Search progress"><span style="width:${((active + 1) / stages.length) * 100}%"></span></div><p>Step ${active + 1} of ${stages.length}</p></div>
      <ol class="stage-list">${stages.map(([stage, label], index) => `<li class="${index < active ? 'complete' : index === active ? 'active' : ''}"><i>${index < active ? '✓' : index + 1}</i><span>${label}</span></li>`).join('')}</ol>
      ${keywords ? `<div class="keyword-feedback"><p>${escapeHtml(job.keyword_source || 'Search signals')}</p><div>${keywords}</div></div>` : ''}
    </div>
  </section>`;
}

function problemCard(problem, index, compact = false, expanded = false) {
  const title = escapeHtml(problem.title);
  const description = escapeHtml(problem.description || 'Open to view the supporting analysis.');
  const score = Number(problem.opportunity_score || 0);
  return `<button type="button" class="problem-card ${compact ? 'compact' : ''} ${expanded ? 'is-expanded' : ''}" data-problem="${index}" aria-expanded="${expanded}"><span class="rank">${index + 1}</span><span class="problem-copy"><strong>${title}</strong><small>${description}</small></span><span class="score" aria-label="Opportunity score ${score} out of 100"><strong>${score}</strong><em>/100</em></span></button>`;
}

function renderResults() {
  const problems = currentResult.problems || [];
  const signalMode = currentResult.signal_mode || 'basic';
  const signalLabel = signalMode === 'smart' ? 'Smart signals' : signalMode === 'custom' ? 'Custom terms' : 'Basic search';
  const modelLabel = analysisModels[currentResult.model] || analysisModels[defaultModel];
  const signals = currentResult.signals || [];
  return `<section class="screen results-screen">${header('Opportunities', 'results-back', button('icon-button', 'upload', 'Share results', 'share'))}
    <div class="screen-copy"><h1>Top Problems Discovered</h1><p>Search: ${escapeHtml(currentResult.topic)}</p><div class="result-meta"><span>${signalLabel}</span><span>${escapeHtml(modelLabel)}</span>${signals.length ? `<small>${signals.map(escapeHtml).join(' · ')}</small>` : ''}</div></div>
    <div class="result-list">${problems.length ? problems.map((problem, index) => `<div class="result-entry">${problemCard(problem, index, false, activeProblem === problem)}${activeProblem === problem ? renderProblemDetails(problem, false, index) : closingProblem === problem ? renderProblemDetails(problem, true, index) : ''}</div>`).join('') : renderEmptyState()}</div>
  </section>`;
}

function renderEmptyState() {
  return `<section class="empty-state"><span class="empty-state-icon" aria-hidden="true">⌁</span><h2>No clear recurring problem yet</h2><p>Try a different lens—the discussions may be too broad, too narrow, or simply not contain a repeating pain point.</p><div class="empty-actions"><button type="button" data-action="edit-topic">Try a broader topic</button><button type="button" data-action="add-focus-terms">Add focus terms</button><button type="button" class="empty-smart" data-action="try-smart">Try Smart signals</button></div></section>`;
}

function postFor(id) { return (currentResult.posts || []).find(post => post.id === id); }

function renderEvidence(problem) {
  const posts = (problem.representative_post_ids || []).map(postFor).filter(Boolean);
  if (!posts.length) return `<p>${problem.post_count || 0} discussion${problem.post_count === 1 ? '' : 's'} supported this recurring theme.</p>`;
  return `<ul class="evidence-list">${posts.map(post => {
    const url = safeExternalUrl(post.url);
    const label = escapeHtml(post.title || post.subreddit || 'Reddit discussion');
    const source = post.subreddit ? `r/${post.subreddit}` : 'Reddit';
    return `<li>${url ? `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>` : label} <span>${escapeHtml(source)}</span></li>`;
  }).join('')}</ul>`;
}

function ideaKey(topic, problem) {
  return `${String(topic || '').trim().toLowerCase()}::${String(problem?.title || '').trim().toLowerCase()}`;
}

function renderProblemDetails(problem, closing = false, index = -1) {
  const saved = savedIdeas.some(item => item.key === ideaKey(currentResult?.topic, problem));
  return `<article class="inline-detail ${closing ? 'is-closing' : ''}">
      <section class="software-opportunity"><div class="opportunity-heading"><h2>Software Opportunity</h2>${index >= 0 ? `<button type="button" class="save-idea ${saved ? 'is-saved' : ''}" data-save-problem="${index}" ${saved ? 'disabled' : ''}>${saved ? 'Saved' : '☆ Save idea'}</button>` : ''}</div><p>${escapeHtml(problem.potential_solution || 'This saved radar predates software-opportunity analysis. Run this topic again to generate one.')}</p></section>
      <section><h2>The Problem</h2><p>${escapeHtml(problem.description || 'No description was returned for this problem.')}</p></section>
      <section><h2>Why It Matters</h2><p>${escapeHtml(problem.score_reasoning || `Reported across ${problem.post_count || 0} discussions, with a pain level of ${problem.pain_level || 'not scored'} out of 10.`)}</p></section>
      <section><h2>Who Experiences This</h2><p>${escapeHtml(problem.who_experiences || 'The analysis did not specify an audience.')}</p></section>
      <section class="workarounds"><h2>Current Workarounds</h2><p>${escapeHtml(problem.existing_workarounds || 'The analysis did not identify a current workaround.')}</p></section>
      <section class="evidence-section"><h2>Discussions</h2>${renderEvidence(problem)}</section>
    </article>`;
}

function renderDetail() {
  return renderResults();
}

function renderSavedIdeaCard(item) {
  const problem = item.problem || {};
  const title = problem.title || item.title || 'Saved opportunity';
  const description = problem.description || item.description || 'Open saved opportunity';
  const score = Number(problem.opportunity_score ?? item.opportunity_score ?? 0);
  const id = escapeHtml(item.id);
  return `<article class="saved-idea"><button type="button" class="saved-idea-open" data-open-saved="${id}"><span class="saved-topic">${escapeHtml(item.topic)}</span><strong>${escapeHtml(title)}</strong><small>${escapeHtml(description)}</small><span class="saved-score">${score}<em>/100</em></span></button><button type="button" class="remove-saved" data-delete-saved="${id}" aria-label="Remove ${escapeHtml(title)} from saved ideas">×</button></article>`;
}

function renderSavedIdeas() {
  return `<section class="screen saved-screen">${header('Saved ideas', 'home')}
    <div class="screen-copy"><p class="eyebrow">Your shortlist</p><h1>Ideas worth revisiting</h1><p>${savedIdeas.length ? 'Saved opportunities stay here even if you clear your search history.' : 'Bookmark a promising software opportunity to build your shortlist.'}</p><small class="storage-note">Stored in this browser · Up to 50 saved ideas. New saves replace the oldest when full.</small></div>
    <div class="saved-list">${savedIdeas.length ? savedIdeas.map(renderSavedIdeaCard).join('') : '<section class="saved-empty"><span aria-hidden="true">☆</span><h2>No saved ideas yet</h2><p>Open a result and choose “Save idea” to keep its full opportunity analysis here.</p><button type="button" data-action="home">Explore opportunities</button></section>'}</div>
  </section>`;
}

function renderAbout() {
  return `<section class="screen about-screen">${header('How it works', 'about-back')}
    <div class="about-copy"><p class="eyebrow">Problem Radar</p><h1>From conversation to opportunity</h1><p class="about-intro">Problem Radar helps you spot recurring problems people are already discussing, then turns them into software opportunities worth investigating.</p>
      <section class="about-section"><h2>What happens in a radar</h2><ol class="process-list"><li><b>1</b><span><strong>Choose a search lens</strong><small>Enter a topic, then optionally add Custom terms or use Smart signals.</small></span></li><li><b>2</b><span><strong>Find relevant discussions</strong><small>Problem Radar searches public Reddit conversations related to that lens.</small></span></li><li><b>3</b><span><strong>Identify recurring problems</strong><small>Gemini looks for themes that appear across multiple discussions.</small></span></li><li><b>4</b><span><strong>Rank software opportunities</strong><small>The strongest recurring themes are presented as opportunities to explore.</small></span></li></ol></section>
      <section class="about-section rating-section"><h2>How ratings work</h2><p>A rating is an estimate, not a guarantee. Gemini considers how often a problem appears, how painful it seems, who experiences it, current workarounds, and whether software could credibly improve the outcome.</p><div class="rating-note"><strong>A higher score means</strong><span>Stronger evidence of a recurring, painful problem with a clearer software opportunity.</span></div></section>
      <section class="about-section"><h2>How to get better results</h2><p>Start with a specific topic. Use Custom terms when you want to focus the discussion, or Smart signals when you want Gemini to choose a more tailored search lens.</p></section>
      <section class="about-section"><h2>Choose your analysis model</h2><p>Under Advanced search tools, you can select the Gemini model used to choose Smart signals and analyze the discussions. Each completed radar records the model used, so you can compare results later.</p></section>
      <section class="about-section about-limit"><h2>Keep in mind</h2><p>Results depend on the Reddit discussions available and Gemini’s analysis. Use a radar as a starting point for validation, not as proof of market demand. To keep the public demo available, each visitor can complete up to 3 successful searches every 15 minutes. Failed searches do not count.</p></section>
    </div>
  </section>`;
}

function renderError() {
  const rateLimited = currentResult?.errorType === 'rate_limit';
  const redditRateLimited = currentResult?.errorType === 'reddit_rate_limit';
  const quotaError = currentResult?.errorType === 'quota';
  const modelBusy = currentResult?.errorType === 'model_busy';
  const modelLabel = analysisModels[currentResult?.model] || analysisModels[defaultModel];
  if (rateLimited) return `<section class="screen error-screen">${header('Demo limit reached', 'home')}<div class="message-panel quota-panel"><span class="message-icon" aria-hidden="true">◌</span><h1>Take a quick breather</h1><p>Problem Radar allows 3 successful searches every 15 minutes to keep the public demo available. Failed searches do not count. Try again in about ${escapeHtml(formatWait(currentResult?.retryAfter))}.</p><button class="primary-button" type="button" data-action="home">Return home</button></div></section>`;
  if (redditRateLimited) {
    const waitMessage = currentResult?.retryAfter ? `Try again in about ${formatWait(currentResult.retryAfter)}.` : 'Try again in a few minutes.';
    return `<section class="screen error-screen">${header('Reddit search paused', 'home')}<div class="message-panel quota-panel"><span class="message-icon" aria-hidden="true">◌</span><h1>Reddit needs a quick breather</h1><p>Reddit is temporarily limiting discussion searches. Your topic is still saved. ${escapeHtml(waitMessage)}</p><button class="primary-button" type="button" data-action="home">Return home</button></div></section>`;
  }
  if (quotaError) {
    return `<section class="screen error-screen">${header('Gemini limit reached', 'home')}<div class="message-panel quota-panel"><span class="message-icon" aria-hidden="true">⌁</span><h1>That model needs a breather</h1><p>${escapeHtml(modelLabel)} has reached its current Gemini limit. Your topic is still saved below—try a different model or come back in a little while.</p><button class="primary-button" type="button" data-action="switch-model">Switch model</button><button class="secondary-button" type="button" data-action="home">Return home</button></div></section>`;
  }
  if (modelBusy) return `<section class="screen error-screen">${header('Gemini is busy', 'home')}<div class="message-panel quota-panel"><span class="message-icon" aria-hidden="true">⌁</span><h1>That model is busy right now</h1><p>${escapeHtml(modelLabel)} is experiencing high demand. Your topic is still saved below—try a different model or come back in a few minutes.</p><button class="primary-button" type="button" data-action="switch-model">Switch model</button><button class="secondary-button" type="button" data-action="home">Return home</button></div></section>`;
  return `<section class="screen error-screen">${header('Problem Radar', 'home')}<div class="message-panel"><h1>That radar didn’t complete</h1><p>${escapeHtml(currentResult?.error || 'Try again in a moment.')}</p><button class="primary-button" type="button" data-action="home">Return home</button></div></section>`;
}

function renderDrawer() {
  return `<div class="drawer-layer"><button class="drawer-scrim" data-action="toggle-drawer" aria-label="Close history"></button><aside class="drawer"><header><div><img src="assets/history.svg" alt="" /><strong>History</strong></div>${button('small-icon-button', 'close', 'Close history', 'toggle-drawer')}</header><div class="history-list">${history.length ? history.map(item => { const id = escapeHtml(item.id); return `<div class="history-row ${currentResult?.id === item.id ? 'selected' : ''}"><button type="button" class="history-item" data-history="${id}">${icon('message-circle')}<span>${escapeHtml(item.topic)}<small>${escapeHtml(analysisModels[item.model] || analysisModels[defaultModel])}</small></span>${currentResult?.id === item.id ? '<i></i>' : ''}</button><button type="button" class="delete-history" data-delete-history="${id}" aria-label="Delete ${escapeHtml(item.topic)} from history">×</button></div>`; }).join('') : '<p class="history-empty">Your completed radars will appear here.</p>'}</div><p class="storage-note history-storage-note">Stored in this browser · Up to 20 radars. New searches replace the oldest when full.</p><button type="button" class="drawer-footer" data-action="about"><span aria-hidden="true">ⓘ</span><strong>How Problem Radar works</strong><i aria-hidden="true">›</i></button></aside></div>`;
}

function bindEvents() {
  document.querySelector('#search-form')?.addEventListener('submit', event => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const customSignals = String(data.get('custom-signals') || '').split(',').map(term => term.trim()).filter(Boolean);
    const signalMode = data.get('smart-signals') ? 'smart' : customSignals.length ? 'custom' : 'basic';
    startSearch(data.get('topic'), { signalMode, customSignals, model: data.get('model') });
  });
  document.querySelector('[name="smart-signals"]')?.addEventListener('change', event => {
    const input = document.querySelector('[name="custom-signals"]');
    input.disabled = event.currentTarget.checked;
    input.closest('.focus-terms').classList.toggle('disabled', event.currentTarget.checked);
  });
  document.querySelectorAll('[data-topic]').forEach(button => button.addEventListener('click', () => startSearch(button.dataset.topic)));
  document.querySelectorAll('[data-action]').forEach(element => element.addEventListener('click', () => handleAction(element.dataset.action)));
  document.querySelectorAll('[data-problem]').forEach(element => element.addEventListener('click', () => {
    const problem = currentResult.problems[Number(element.dataset.problem)];
    const previous = activeProblem;
    if (previous) closingProblem = previous;
    activeProblem = previous === problem ? null : problem;
    view = 'results'; render();
    if (previous) {
      setTimeout(() => {
        if (closingProblem === previous) { closingProblem = null; render(); }
      }, 220);
    }
  }));
  document.querySelectorAll('[data-history]').forEach(element => element.addEventListener('click', () => openHistory(element.dataset.history)));
  document.querySelectorAll('[data-delete-history]').forEach(element => element.addEventListener('click', () => deleteHistory(element.dataset.deleteHistory)));
  document.querySelectorAll('[data-save-problem]').forEach(element => element.addEventListener('click', () => saveProblem(Number(element.dataset.saveProblem))));
  document.querySelectorAll('[data-open-saved]').forEach(element => element.addEventListener('click', () => openSavedIdea(element.dataset.openSaved)));
  document.querySelectorAll('[data-delete-saved]').forEach(element => element.addEventListener('click', () => deleteSavedIdea(element.dataset.deleteSaved)));
}

function handleAction(action) {
  if (action === 'toggle-drawer') { drawerOpen = !drawerOpen; render(); return; }
  if (action === 'home') { drawerOpen = false; activeProblem = null; view = 'home'; render(); return; }
  if (action === 'results-back') { activeProblem = null; view = resultsReturnView; render(); return; }
  if (action === 'results') { view = 'results'; render(); return; }
  if (action === 'saved') { view = 'saved'; render(); return; }
  if (action === 'about') { aboutReturnView = view; drawerOpen = false; view = 'about'; render(); return; }
  if (action === 'about-back') { view = aboutReturnView; render(); return; }
  if (action === 'switch-model') {
    homeTopic = currentResult?.topic || '';
    homeModel = analysisModels[currentResult?.model] ? currentResult.model : defaultModel;
    view = 'home';
    render();
    const tools = document.querySelector('.advanced-tools');
    if (tools) tools.open = true;
    document.querySelector('[name="model"]')?.focus();
    return;
  }
  if (action === 'edit-topic' || action === 'add-focus-terms') {
    homeTopic = currentResult?.topic || '';
    view = 'home';
    render();
    document.querySelector(action === 'add-focus-terms' ? '[name="custom-signals"]' : '#topic')?.focus();
    return;
  }
  if (action === 'try-smart') { startSearch(currentResult?.topic, { signalMode: 'smart', model: currentResult?.model }); return; }
  if (action === 'share') navigator.share?.({ title: 'Problem Radar', text: `Opportunities in ${currentResult.topic}` });
}

function loadHistory() {
  history = readStoredList(historyStorageKey, isHistoryItem).slice(0, maxHistoryItems);
}

function saveHistory(item) {
  history = [item, ...history.filter(existing => existing.id !== item.id)].slice(0, maxHistoryItems);
  writeStoredList(historyStorageKey, history);
}

async function startSearch(topic, options = {}) {
  topic = String(topic || '').trim();
  if (!topic) return document.querySelector('#topic')?.focus();
  homeTopic = topic;
  const signalMode = options.signalMode || 'basic';
  const customSignals = options.customSignals || [];
  const model = analysisModels[options.model] ? options.model : defaultModel;
  homeModel = model;
  resultsReturnView = 'home';
  currentResult = { topic, model, job: { stage: 'queued', model, signal_mode: signalMode, keywords: signalMode === 'custom' ? customSignals : [], message: 'Preparing your search…' } };
  view = 'loading'; render();
  try {
    const response = await fetch('/api/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ topic, model, signal_mode: signalMode, custom_signals: customSignals }) });
    const job = await response.json();
    if (!response.ok) {
      const error = new Error(job.error || 'Search failed.');
      error.type = job.error_type;
      error.retryAfter = job.retry_after;
      throw error;
    }
    await watchJob(job.id);
  } catch (error) { currentResult = { topic, model, error: error.message, errorType: error.type, retryAfter: error.retryAfter }; view = 'error'; }
  render();
}

async function watchJob(id) {
  while (true) {
    const response = await fetch(`/api/jobs/${encodeURIComponent(id)}`);
    const job = await response.json();
    if (!response.ok) throw new Error(job.error || 'Search status was unavailable.');
    if (job.status === 'failed') {
      const error = new Error(job.error || 'Search failed.');
      error.type = job.error_type;
      error.retryAfter = job.retry_after;
      throw error;
    }
    if (job.status === 'complete') { currentResult = job.result; saveHistory(job.result); activeProblem = null; view = 'results'; return; }
    currentResult.job = job; render();
    await new Promise(resolve => setTimeout(resolve, 800));
  }
}

function openHistory(id) {
  const item = history.find(entry => entry.id === id);
  if (!item) return;
  currentResult = item;
  resultsReturnView = 'home';
  drawerOpen = false;
  activeProblem = null;
  view = 'results';
  render();
}

function deleteHistory(id) {
  history = history.filter(item => item.id !== id);
  writeStoredList(historyStorageKey, history);
  render();
}

function loadSavedIdeas() {
  savedIdeas = readStoredList(savedIdeasStorageKey, isSavedIdea).slice(0, maxSavedIdeas);
}

function saveProblem(index) {
  const problem = currentResult?.problems?.[index];
  if (!problem) return;
  const item = {
    id: localId(),
    key: ideaKey(currentResult.topic, problem),
    topic: currentResult.topic,
    model: currentResult.model || defaultModel,
    signal_mode: currentResult.signal_mode,
    signals: currentResult.signals || [],
    saved_at: new Date().toISOString(),
    problem,
    posts: currentResult.posts || [],
  };
  if (savedIdeas.some(existing => existing.key === item.key)) return;
  savedIdeas = [item, ...savedIdeas].slice(0, maxSavedIdeas);
  writeStoredList(savedIdeasStorageKey, savedIdeas);
  render();
}

function openSavedIdea(id) {
  const saved = savedIdeas.find(item => item.id === id);
  if (!saved) return;
  currentResult = { id: `saved:${saved.id}`, topic: saved.topic, model: saved.model || defaultModel, signal_mode: saved.signal_mode, signals: saved.signals || [], problems: [saved.problem], posts: saved.posts || [] };
  resultsReturnView = 'saved';
  activeProblem = null;
  view = 'results';
  render();
}

function deleteSavedIdea(id) {
  savedIdeas = savedIdeas.filter(item => item.id !== id);
  writeStoredList(savedIdeasStorageKey, savedIdeas);
  render();
}

loadHistory();
loadSavedIdeas();
render();
