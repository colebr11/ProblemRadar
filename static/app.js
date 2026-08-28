const app = document.querySelector('#app');
const exampleTopics = ['Fitness', 'College Students', 'Subscriptions', 'Travel'];
let history = [];
let currentResult = null;
let activeProblem = null;
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
      <form class="search-box" id="search-form"><img src="assets/search.svg" alt="" /><input id="topic" name="topic" placeholder="Enter a topic, problem, or keyword…" autocomplete="off" /><button aria-label="Search" type="submit">${icon('arrow-right')}</button></form>
      <section class="examples"><p>Popular radars this week</p><div>${exampleTopics.map(topic => `<button type="button" class="topic-pill" data-topic="${topic}">${topic}</button>`).join('')}</div></section>
    </div>
  </section>`;
}

function renderLoading() {
  const topic = escapeHtml(currentResult?.topic || 'your topic');
  return `<section class="screen loading-screen">${header('Analyzing', 'home')}
    <div class="loading-center"><span class="radar-ring">${icon('radar')}</span><div><h1>Searching discussions about “${topic}”...</h1><p id="analysis-stage">Finding relevant discussions…</p></div><div class="loading-line" aria-hidden="true"><span></span></div></div>
  </section>`;
}

function problemCard(problem, index, compact = false) {
  const title = escapeHtml(problem.title);
  const description = escapeHtml(problem.description || 'Open to view the supporting analysis.');
  return `<button type="button" class="problem-card ${compact ? 'compact' : ''}" data-problem="${index}"><span class="rank">${index + 1}</span><span class="problem-copy"><strong>${title}</strong><small>${description}</small></span><span class="score">${Number(problem.opportunity_score || 0)}/100</span></button>`;
}

function renderResults() {
  const problems = currentResult.problems || [];
  return `<section class="screen results-screen">${header('Opportunities', 'home', button('icon-button', 'upload', 'Share results', 'share'))}
    <div class="screen-copy"><h1>Top Problems Discovered</h1><p>Search: ${escapeHtml(currentResult.topic)}</p></div>
    <div class="result-list">${problems.length ? problems.map(problemCard).join('') : '<p class="empty-state">No recurring problems appeared in this set of discussions.</p>'}</div>
  </section>`;
}

function postFor(id) { return (currentResult.posts || []).find(post => post.id === id); }

function renderEvidence(problem) {
  const posts = (problem.representative_post_ids || []).map(postFor).filter(Boolean);
  if (!posts.length) return `<p>${problem.post_count || 0} discussion${problem.post_count === 1 ? '' : 's'} supported this recurring theme.</p>`;
  return `<ul class="evidence-list">${posts.map(post => `<li>${post.url ? `<a href="${escapeHtml(post.url)}" target="_blank" rel="noreferrer">${escapeHtml(post.title || post.subreddit || 'Reddit discussion')}</a>` : escapeHtml(post.title || post.subreddit || 'Discussion')} ${post.subreddit ? `<span>r/${escapeHtml(post.subreddit)}</span>` : ''}</li>`).join('')}</ul>`;
}

function renderDetail() {
  const problem = activeProblem;
  const index = currentResult.problems.indexOf(problem);
  return `<section class="screen detail-screen">${header('Detail', 'results', button('icon-button', 'upload', 'Share result', 'share'))}
    <div class="detail-heading"><h1>Opportunities in ${escapeHtml(currentResult.topic)}</h1></div>
    <article class="detail-card">${problemCard(problem, index)}<hr />
      <section class="software-opportunity"><h2>Software Opportunity</h2><p>${escapeHtml(problem.potential_solution || 'This saved radar predates software-opportunity analysis. Run this topic again to generate one.')}</p></section>
      <section><h2>The Problem</h2><p>${escapeHtml(problem.description || 'No description was returned for this problem.')}</p></section>
      <section><h2>Why It Matters</h2><p>${escapeHtml(problem.score_reasoning || `Reported across ${problem.post_count || 0} discussions, with a pain level of ${problem.pain_level || 'not scored'} out of 10.`)}</p></section>
      <section><h2>Who Experiences This</h2><p>${escapeHtml(problem.who_experiences || 'The analysis did not specify an audience.')}</p></section>
      <section class="workarounds"><h2>Current Workarounds</h2><p>${escapeHtml(problem.existing_workarounds || 'The analysis did not identify a current workaround.')}</p></section>
      <section class="evidence-section"><h2>Discussions</h2>${renderEvidence(problem)}</section>
    </article>
    <div class="result-list compact-list">${currentResult.problems.map((item, itemIndex) => item === problem ? '' : problemCard(item, itemIndex, true)).join('')}</div>
  </section>`;
}

function renderError() {
  return `<section class="screen error-screen">${header('Problem Radar', 'home')}<div class="message-panel"><h1>That radar didn’t complete</h1><p>${escapeHtml(currentResult?.error || 'Try again in a moment.')}</p><button class="primary-button" type="button" data-action="home">Return home</button></div></section>`;
}

function renderDrawer() {
  return `<div class="drawer-layer"><button class="drawer-scrim" data-action="toggle-drawer" aria-label="Close history"></button><aside class="drawer"><header><div><img src="assets/history.svg" alt="" /><strong>History</strong></div>${button('small-icon-button', 'close', 'Close history', 'toggle-drawer')}</header><div class="history-list">${history.length ? history.map(item => `<button type="button" class="history-item ${currentResult?.id === item.id ? 'selected' : ''}" data-history="${item.id}">${icon('message-circle')}<span>${escapeHtml(item.topic)}</span>${currentResult?.id === item.id ? '<i></i>' : ''}</button>`).join('') : '<p class="history-empty">Your completed radars will appear here.</p>'}</div><footer>Radar Preferences</footer></aside></div>`;
}

function bindEvents() {
  document.querySelector('#search-form')?.addEventListener('submit', event => { event.preventDefault(); startSearch(new FormData(event.currentTarget).get('topic')); });
  document.querySelectorAll('[data-topic]').forEach(button => button.addEventListener('click', () => startSearch(button.dataset.topic)));
  document.querySelectorAll('[data-action]').forEach(element => element.addEventListener('click', () => handleAction(element.dataset.action)));
  document.querySelectorAll('[data-problem]').forEach(element => element.addEventListener('click', () => { activeProblem = currentResult.problems[Number(element.dataset.problem)]; view = 'detail'; render(); }));
  document.querySelectorAll('[data-history]').forEach(element => element.addEventListener('click', () => openHistory(element.dataset.history)));
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

async function startSearch(topic) {
  topic = String(topic || '').trim();
  if (!topic) return document.querySelector('#topic')?.focus();
  currentResult = { topic };
  view = 'loading'; render();
  const stages = ['Finding relevant discussions…', 'Analyzing recurring problems…'];
  let stage = 0;
  const timer = setInterval(() => { const label = document.querySelector('#analysis-stage'); if (label) { label.textContent = stages[stage++ % stages.length]; } }, 2600);
  try {
    const response = await fetch('/api/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ topic }) });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Search failed.');
    // Render as soon as the completed analysis arrives. History is secondary;
    // it must never hold the user on the loading screen.
    currentResult = payload; activeProblem = null; view = 'results';
    clearInterval(timer); render();
    loadHistory();
    return;
  } catch (error) { currentResult = { error: error.message }; view = 'error'; }
  clearInterval(timer); render();
}

async function openHistory(id) {
  try { const response = await fetch(`/api/history/${encodeURIComponent(id)}`); if (!response.ok) throw new Error(); currentResult = await response.json(); drawerOpen = false; activeProblem = null; view = 'results'; render(); } catch { await loadHistory(); render(); }
}

loadHistory().finally(render);
