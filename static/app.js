const app = document.querySelector('#app');
const exampleTopics = ['Fitness', 'College Students', 'Subscriptions', 'Travel'];
let history = [];
let currentResult = null;
let activeProblem = null;
let closingProblem = null;
let drawerOpen = false;
let view = 'home';

const icon = (name, label = '') => `<img src="assets/${name}.svg" alt="${label}" />`;
const escapeHtml = (value = '') => String(value).replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);

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
  const screens = { home: renderHome, loading: renderLoading, results: renderResults, detail: renderDetail, error: renderError };
  app.innerHTML = `<section class="phone-frame">${screens[view]() }${drawerOpen ? renderDrawer() : ''}</section>`;
  bindEvents();
}

function renderHome() {
  return `<section class="screen home-screen">
    ${header('', 'menu', '<span class="avatar" aria-label="Current user">ME</span>')}
    <div class="hero">
      <div class="hero-copy"><p class="eyebrow">Opportunity Finder</p><h1>What problems are worth solving?</h1></div>
      <form id="search-form" class="search-form"><div class="search-box"><img src="assets/search.svg" alt="" /><input id="topic" name="topic" placeholder="Enter a topic, problem, or keyword…" autocomplete="off" /><button aria-label="Search" type="submit">${icon('arrow-right')}</button></div>
        <div class="search-options"><label class="focus-terms"><span>Refine with up to 3 terms <small>optional</small></span><input name="custom-signals" placeholder="e.g. dating apps, lonely, meeting people" autocomplete="off" /></label>
          <label class="smart-toggle"><input type="checkbox" name="smart-signals" /><span aria-hidden="true"></span><b>Smart signals</b><em>Uses one extra Gemini request</em></label>
        </div>
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
  return `<section class="screen results-screen">${header('Opportunities', 'home', button('icon-button', 'upload', 'Share results', 'share'))}
    <div class="screen-copy"><h1>Top Problems Discovered</h1><p>Search: ${escapeHtml(currentResult.topic)}</p></div>
    <div class="result-list">${problems.length ? problems.map((problem, index) => `<div class="result-entry">${problemCard(problem, index, false, activeProblem === problem)}${activeProblem === problem ? renderProblemDetails(problem) : closingProblem === problem ? renderProblemDetails(problem, true) : ''}</div>`).join('') : '<p class="empty-state">No recurring problems appeared in this set of discussions.</p>'}</div>
  </section>`;
}

function postFor(id) { return (currentResult.posts || []).find(post => post.id === id); }

function renderEvidence(problem) {
  const posts = (problem.representative_post_ids || []).map(postFor).filter(Boolean);
  if (!posts.length) return `<p>${problem.post_count || 0} discussion${problem.post_count === 1 ? '' : 's'} supported this recurring theme.</p>`;
  return `<ul class="evidence-list">${posts.map(post => `<li>${post.url ? `<a href="${escapeHtml(post.url)}" target="_blank" rel="noreferrer">${escapeHtml(post.title || post.subreddit || 'Reddit discussion')}</a>` : escapeHtml(post.title || post.subreddit || 'Discussion')} ${post.subreddit ? `<span>r/${escapeHtml(post.subreddit)}</span>` : ''}</li>`).join('')}</ul>`;
}

function renderProblemDetails(problem, closing = false) {
  return `<article class="inline-detail ${closing ? 'is-closing' : ''}">
      <section class="software-opportunity"><h2>Software Opportunity</h2><p>${escapeHtml(problem.potential_solution || 'This saved radar predates software-opportunity analysis. Run this topic again to generate one.')}</p></section>
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

function renderError() {
  return `<section class="screen error-screen">${header('Problem Radar', 'home')}<div class="message-panel"><h1>That radar didn’t complete</h1><p>${escapeHtml(currentResult?.error || 'Try again in a moment.')}</p><button class="primary-button" type="button" data-action="home">Return home</button></div></section>`;
}

function renderDrawer() {
  return `<div class="drawer-layer"><button class="drawer-scrim" data-action="toggle-drawer" aria-label="Close history"></button><aside class="drawer"><header><div><img src="assets/history.svg" alt="" /><strong>History</strong></div>${button('small-icon-button', 'close', 'Close history', 'toggle-drawer')}</header><div class="history-list">${history.length ? history.map(item => `<div class="history-row ${currentResult?.id === item.id ? 'selected' : ''}"><button type="button" class="history-item" data-history="${item.id}">${icon('message-circle')}<span>${escapeHtml(item.topic)}</span>${currentResult?.id === item.id ? '<i></i>' : ''}</button><button type="button" class="delete-history" data-delete-history="${item.id}" aria-label="Delete ${escapeHtml(item.topic)} from history">×</button></div>`).join('') : '<p class="history-empty">Your completed radars will appear here.</p>'}</div><footer>Radar Preferences</footer></aside></div>`;
}

function bindEvents() {
  document.querySelector('#search-form')?.addEventListener('submit', event => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const customSignals = String(data.get('custom-signals') || '').split(',').map(term => term.trim()).filter(Boolean);
    const signalMode = data.get('smart-signals') ? 'smart' : customSignals.length ? 'custom' : 'basic';
    startSearch(data.get('topic'), { signalMode, customSignals });
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
}

function handleAction(action) {
  if (action === 'toggle-drawer') { drawerOpen = !drawerOpen; render(); return; }
  if (action === 'home') { drawerOpen = false; activeProblem = null; view = 'home'; render(); return; }
  if (action === 'results') { view = 'results'; render(); return; }
  if (action === 'share') navigator.share?.({ title: 'Problem Radar', text: `Opportunities in ${currentResult.topic}` });
}

async function loadHistory() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 4000);
  try { history = await fetch('/api/history', { signal: controller.signal }).then(response => response.ok ? response.json() : []); } catch { history = []; } finally { clearTimeout(timeout); }
}

async function startSearch(topic, options = {}) {
  topic = String(topic || '').trim();
  if (!topic) return document.querySelector('#topic')?.focus();
  const signalMode = options.signalMode || 'basic';
  const customSignals = options.customSignals || [];
  currentResult = { topic, job: { stage: 'queued', signal_mode: signalMode, keywords: signalMode === 'custom' ? customSignals : [], message: 'Preparing your search…' } };
  view = 'loading'; render();
  try {
    const response = await fetch('/api/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ topic, signal_mode: signalMode, custom_signals: customSignals }) });
    const job = await response.json();
    if (!response.ok) throw new Error(job.error || 'Search failed.');
    await watchJob(job.id);
  } catch (error) { currentResult = { error: error.message }; view = 'error'; }
  render();
}

async function watchJob(id) {
  while (true) {
    const response = await fetch(`/api/jobs/${encodeURIComponent(id)}`);
    const job = await response.json();
    if (!response.ok) throw new Error(job.error || 'Search status was unavailable.');
    if (job.status === 'failed') throw new Error(job.error || 'Search failed.');
    if (job.status === 'complete') { currentResult = job.result; activeProblem = null; view = 'results'; loadHistory(); return; }
    currentResult.job = job; render();
    await new Promise(resolve => setTimeout(resolve, 800));
  }
}

async function openHistory(id) {
  try { const response = await fetch(`/api/history/${encodeURIComponent(id)}`); if (!response.ok) throw new Error(); currentResult = await response.json(); drawerOpen = false; activeProblem = null; view = 'results'; render(); } catch { await loadHistory(); render(); }
}

async function deleteHistory(id) {
  try {
    const response = await fetch(`/api/history/${encodeURIComponent(id)}`, { method: 'DELETE' });
    if (!response.ok) throw new Error();
    history = history.filter(item => item.id !== id);
    render();
  } catch {
    await loadHistory();
    render();
  }
}

loadHistory().finally(render);
