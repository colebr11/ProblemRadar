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
let homeTopic = '';

const icon = (name, label = '') => `<img src="assets/${name}.svg" alt="${label}" />`;
const escapeHtml = (value = '') => String(value).replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);
const safeExternalUrl = (value) => {
  try {
    const url = new URL(String(value || ''));
    return url.protocol === 'https:' || url.protocol === 'http:' ? escapeHtml(url.href) : '';
  } catch { return ''; }
};

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
        <details class="advanced-tools"><summary><span>Advanced search tools</span><small>Optional</small><i aria-hidden="true">⌄</i></summary><div class="search-options"><fieldset class="source-picker"><legend>Source</legend><label><input type="radio" name="source" value="reddit" checked /><span>Reddit</span></label><small>More sources coming soon</small></fieldset><label class="focus-terms"><span>Refine with up to 3 terms <small>optional</small></span><input name="custom-signals" placeholder="e.g. dating apps, lonely, meeting people" autocomplete="off" /></label>
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
  const sourceLabel = 'Reddit';
  const signals = currentResult.signals || [];
  return `<section class="screen results-screen">${header('Opportunities', 'home', button('icon-button', 'upload', 'Share results', 'share'))}
    <div class="screen-copy"><h1>Top Problems Discovered</h1><p>Search: ${escapeHtml(currentResult.topic)}</p><div class="result-meta"><span>${sourceLabel}</span><span>${signalLabel}</span>${signals.length ? `<small>${signals.map(escapeHtml).join(' · ')}</small>` : ''}</div></div>
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

function renderSavedIdeas() {
  return `<section class="screen saved-screen">${header('Saved ideas', 'home')}
    <div class="screen-copy"><p class="eyebrow">Your shortlist</p><h1>Ideas worth revisiting</h1><p>${savedIdeas.length ? 'Saved opportunities stay here even if you clear your search history.' : 'Bookmark a promising software opportunity to build your shortlist.'}</p></div>
    <div class="saved-list">${savedIdeas.length ? savedIdeas.map(item => `<article class="saved-idea"><button type="button" class="saved-idea-open" data-open-saved="${item.id}"><span class="saved-topic">${escapeHtml(item.topic)}</span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.description || 'Open saved opportunity')}</small><span class="saved-score">${Number(item.opportunity_score || 0)}<em>/100</em></span></button><button type="button" class="remove-saved" data-delete-saved="${item.id}" aria-label="Remove ${escapeHtml(item.title)} from saved ideas">×</button></article>`).join('') : '<section class="saved-empty"><span aria-hidden="true">☆</span><h2>No saved ideas yet</h2><p>Open a result and choose “Save idea” to keep its full opportunity analysis here.</p><button type="button" data-action="home">Explore opportunities</button></section>'}</div>
  </section>`;
}

function renderAbout() {
  return `<section class="screen about-screen">${header('How it works', 'about-back')}
    <div class="about-copy"><p class="eyebrow">Problem Radar</p><h1>From conversation to opportunity</h1><p class="about-intro">Problem Radar helps you spot recurring problems people are already discussing, then turns them into software opportunities worth investigating.</p>
      <section class="about-section"><h2>What happens in a radar</h2><ol class="process-list"><li><b>1</b><span><strong>Choose a search lens</strong><small>Enter a topic, then optionally add Custom terms or use Smart signals.</small></span></li><li><b>2</b><span><strong>Find relevant discussions</strong><small>Problem Radar searches public Reddit conversations related to that lens.</small></span></li><li><b>3</b><span><strong>Identify recurring problems</strong><small>Gemini looks for themes that appear across multiple discussions.</small></span></li><li><b>4</b><span><strong>Rank software opportunities</strong><small>The strongest recurring themes are presented as opportunities to explore.</small></span></li></ol></section>
      <section class="about-section rating-section"><h2>How ratings work</h2><p>A rating is an estimate, not a guarantee. Gemini considers how often a problem appears, how painful it seems, who experiences it, current workarounds, and whether software could credibly improve the outcome.</p><div class="rating-note"><strong>A higher score means</strong><span>Stronger evidence of a recurring, painful problem with a clearer software opportunity.</span></div></section>
      <section class="about-section"><h2>How to get better results</h2><p>Start with a specific topic. Use Custom terms when you want to focus the discussion, or Smart signals when you want Gemini to choose a more tailored search lens.</p></section>
      <section class="about-section about-limit"><h2>Keep in mind</h2><p>Results depend on the Reddit discussions available and Gemini’s analysis. Use a radar as a starting point for validation, not as proof of market demand.</p></section>
    </div>
  </section>`;
}

function renderError() {
  return `<section class="screen error-screen">${header('Problem Radar', 'home')}<div class="message-panel"><h1>That radar didn’t complete</h1><p>${escapeHtml(currentResult?.error || 'Try again in a moment.')}</p><button class="primary-button" type="button" data-action="home">Return home</button></div></section>`;
}

function renderDrawer() {
  return `<div class="drawer-layer"><button class="drawer-scrim" data-action="toggle-drawer" aria-label="Close history"></button><aside class="drawer"><header><div><img src="assets/history.svg" alt="" /><strong>History</strong></div>${button('small-icon-button', 'close', 'Close history', 'toggle-drawer')}</header><div class="history-list">${history.length ? history.map(item => `<div class="history-row ${currentResult?.id === item.id ? 'selected' : ''}"><button type="button" class="history-item" data-history="${item.id}">${icon('message-circle')}<span>${escapeHtml(item.topic)}</span>${currentResult?.id === item.id ? '<i></i>' : ''}</button><button type="button" class="delete-history" data-delete-history="${item.id}" aria-label="Delete ${escapeHtml(item.topic)} from history">×</button></div>`).join('') : '<p class="history-empty">Your completed radars will appear here.</p>'}</div><button type="button" class="drawer-footer" data-action="about"><span aria-hidden="true">ⓘ</span><strong>How Problem Radar works</strong><i aria-hidden="true">›</i></button></aside></div>`;
}

function bindEvents() {
  document.querySelector('#search-form')?.addEventListener('submit', event => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const customSignals = String(data.get('custom-signals') || '').split(',').map(term => term.trim()).filter(Boolean);
    const signalMode = data.get('smart-signals') ? 'smart' : customSignals.length ? 'custom' : 'basic';
    startSearch(data.get('topic'), { source: data.get('source'), signalMode, customSignals });
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
  if (action === 'results') { view = 'results'; render(); return; }
  if (action === 'saved') { view = 'saved'; render(); return; }
  if (action === 'about') { aboutReturnView = view; drawerOpen = false; view = 'about'; render(); return; }
  if (action === 'about-back') { view = aboutReturnView; render(); return; }
  if (action === 'edit-topic' || action === 'add-focus-terms') {
    homeTopic = currentResult?.topic || '';
    view = 'home';
    render();
    document.querySelector(action === 'add-focus-terms' ? '[name="custom-signals"]' : '#topic')?.focus();
    return;
  }
  if (action === 'try-smart') { startSearch(currentResult?.topic, { source: currentResult?.source, signalMode: 'smart' }); return; }
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
  homeTopic = topic;
  const source = options.source || 'reddit';
  const signalMode = options.signalMode || 'basic';
  const customSignals = options.customSignals || [];
  currentResult = { topic, job: { stage: 'queued', source, signal_mode: signalMode, keywords: signalMode === 'custom' ? customSignals : [], message: 'Preparing your search…' } };
  view = 'loading'; render();
  try {
    const response = await fetch('/api/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ topic, source, signal_mode: signalMode, custom_signals: customSignals }) });
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

async function loadSavedIdeas() {
  try { savedIdeas = await fetch('/api/saved').then(response => response.ok ? response.json() : []); } catch { savedIdeas = []; }
}

async function saveProblem(index) {
  const problem = currentResult?.problems?.[index];
  if (!problem) return;
  try {
    const response = await fetch('/api/saved', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ topic: currentResult.topic, source: currentResult.source, signal_mode: currentResult.signal_mode, signals: currentResult.signals, problem, posts: currentResult.posts || [] }) });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Unable to save that idea.');
    savedIdeas = [payload.item, ...savedIdeas.filter(item => item.key !== payload.item.key)];
    render();
  } catch { /* Keep the current result usable if local saving is unavailable. */ }
}

async function openSavedIdea(id) {
  try {
    const response = await fetch(`/api/saved/${encodeURIComponent(id)}`);
    if (!response.ok) throw new Error();
    const saved = await response.json();
    currentResult = { id: `saved:${saved.id}`, topic: saved.topic, source: saved.source || 'reddit', signal_mode: saved.signal_mode, signals: saved.signals || [], problems: [saved.problem], posts: saved.posts || [] };
    activeProblem = null;
    view = 'results';
    render();
  } catch { await loadSavedIdeas(); render(); }
}

async function deleteSavedIdea(id) {
  try {
    const response = await fetch(`/api/saved/${encodeURIComponent(id)}`, { method: 'DELETE' });
    if (!response.ok) throw new Error();
    savedIdeas = savedIdeas.filter(item => item.id !== id);
    render();
  } catch { await loadSavedIdeas(); render(); }
}

Promise.all([loadHistory(), loadSavedIdeas()]).finally(render);
