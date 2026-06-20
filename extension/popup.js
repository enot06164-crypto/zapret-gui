let API_BASE = 'http://127.0.0.1:8080';
let currentDomain = '';
let currentList = 'list-general-user';
let userDomains = [];

const $ = (s) => document.querySelector(s);

async function loadSettings() {
  const data = await chrome.storage.local.get(['apiHost']);
  if (data.apiHost) API_BASE = data.apiHost;
}

async function saveSettings() {
  const host = $('#input-host').value.replace(/\/+$/, '');
  API_BASE = host;
  await chrome.storage.local.set({ apiHost: host });
  showToast('Настройки сохранены', 'ok');
  switchScreen('main');
  checkConnection();
}

function switchScreen(name) {
  $('#screen-main').style.display = name === 'main' ? '' : 'none';
  $('#screen-settings').style.display = name === 'settings' ? '' : 'none';
}

function showToast(msg, type) {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();
  const el = document.createElement('div');
  el.className = 'toast toast-' + type;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 2000);
}

async function checkConnection() {
  const statusBox = $('#connection-status');
  const connText = $('#conn-text');
  const dot = $('#status-dot');
  try {
    const res = await fetch(API_BASE + '/api/status', { signal: AbortSignal.timeout(3000) });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    if (data.installed && data.winws_running) {
      statusBox.className = 'info-box info-ok';
      connText.textContent = 'Подключено · zapret работает';
      dot.className = 'dot dot-on';
      dot.title = 'Подключено';
    } else if (data.installed) {
      statusBox.className = 'info-box info-warn';
      connText.textContent = 'Подключено · zapret не активен';
      dot.className = 'dot dot-partial';
      dot.title = 'Запрет не активен';
    } else {
      statusBox.className = 'info-box info-err';
      connText.textContent = 'GUI подключён, но zapret не установлен';
      dot.className = 'dot dot-off';
    }
    $('#btn-add').disabled = false;
    $('#btn-remove').disabled = false;
    updateActionButtons();
  } catch (e) {
    statusBox.className = 'info-box info-err';
    connText.textContent = 'Нет подключения к GUI';
    dot.className = 'dot dot-off';
    dot.title = 'Отключено';
    $('#btn-add').disabled = true;
    $('#btn-remove').disabled = true;
  }
}

async function getCurrentTab() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url) return null;
    const url = new URL(tab.url);
    if (url.protocol === 'http:' || url.protocol === 'https:') {
      return url.hostname;
    }
  } catch (e) {}
  return null;
}

async function loadUserList() {
  try {
    const res = await fetch(API_BASE + '/api/lists/' + currentList, { signal: AbortSignal.timeout(3000) });
    if (!res.ok) return;
    const data = await res.json();
    const content = data.content || '';
    userDomains = content.split('\n').map(s => s.trim()).filter(Boolean);
    renderDomainList();
    updateActionButtons();
  } catch (e) {}
}

function renderDomainList() {
  const container = $('#user-list');
  const badge = $('#count-badge');
  badge.textContent = userDomains.length;
  while (container.firstChild) container.removeChild(container.firstChild);
  if (userDomains.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-list';
    empty.textContent = 'Список пуст';
    container.appendChild(empty);
    return;
  }
  userDomains.forEach(d => {
    const item = document.createElement('div');
    item.className = 'domain-item';

    const name = document.createElement('span');
    name.className = 'domain-name';
    name.title = d;
    name.textContent = d;

    const btn = document.createElement('button');
    btn.className = 'domain-remove';
    btn.dataset.domain = d;
    btn.title = 'Удалить';

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', '12');
    svg.setAttribute('height', '12');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', 'M18 6L6 18M6 6l12 12');
    svg.appendChild(path);
    btn.appendChild(svg);

    item.appendChild(name);
    item.appendChild(btn);
    container.appendChild(item);
  });
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function updateActionButtons() {
  const inList = currentDomain && userDomains.includes(currentDomain);
  $('#btn-add').style.display = inList ? 'none' : '';
  $('#btn-remove').style.display = inList ? '' : 'none';
}

async function addDomain(domain) {
  if (!domain) return;
  try {
    const res = await fetch(API_BASE + '/api/lists/' + currentList + '/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entry: domain })
    });
    const data = await res.json();
    if (res.status === 409 && data.duplicate) {
      showToast(domain + ' уже в списке', 'ok');
    } else if (data.success) {
      showToast(domain + ' добавлен', 'ok');
    } else {
      showToast('Ошибка: ' + (data.error || 'unknown'), 'err');
    }
    loadUserList();
  } catch (e) {
    showToast('Ошибка сети', 'err');
  }
}

async function removeDomain(domain) {
  if (!domain) return;
  try {
    const res = await fetch(API_BASE + '/api/lists/' + currentList + '/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entry: domain })
    });
    const data = await res.json();
    if (data.success) {
      showToast(domain + ' удалён', 'ok');
    } else {
      showToast('Ошибка: ' + (data.error || 'unknown'), 'err');
    }
    loadUserList();
  } catch (e) {
    showToast('Ошибка сети', 'err');
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  await loadSettings();

  currentDomain = await getCurrentTab();
  $('#current-domain').textContent = currentDomain || '—';

  await checkConnection();
  await loadUserList();

  $('#list-picker').addEventListener('change', (e) => {
    currentList = e.target.value;
    loadUserList();
  });

  $('#btn-add').addEventListener('click', () => {
    if (currentDomain) addDomain(currentDomain);
  });

  $('#btn-remove').addEventListener('click', () => {
    if (currentDomain) removeDomain(currentDomain);
  });

  $('#user-list').addEventListener('click', (e) => {
    const btn = e.target.closest('.domain-remove');
    if (btn) removeDomain(btn.dataset.domain);
  });

  $('#link-settings').addEventListener('click', (e) => {
    e.preventDefault();
    switchScreen('settings');
    $('#input-host').value = API_BASE;
  });

  $('#btn-back').addEventListener('click', () => switchScreen('main'));
  $('#btn-save-settings').addEventListener('click', saveSettings);
});
