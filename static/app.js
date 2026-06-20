let currentList = 'list-general-user';
let currentListContent = '';
let statusPollingTimer = null;
let activeTab = 'dashboard';

function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
}

function csrfFetch(url, options) {
    options = options || {};
    options.headers = options.headers || {};
    if (options.method === 'POST') {
        options.headers['X-CSRF-Token'] = getCsrfToken();
    }
    return window.fetch(url, options);
}

// === TOAST ===
function showToast(message, type) {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.className = 'toast toast-' + (type || 'success');
    toast.textContent = message;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('toast-visible'));
    setTimeout(() => {
        toast.classList.remove('toast-visible');
        setTimeout(() => toast.remove(), 200);
    }, 2000);
}

// === NAVIGATION ===
document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
        document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        item.classList.add('active');
        const tab = document.getElementById('tab-' + item.dataset.tab);
        if (tab) tab.classList.add('active');
        activeTab = item.dataset.tab;

        if (item.dataset.tab === 'dashboard') loadStatus();
        if (item.dataset.tab === 'strategy') loadStrategies();
        if (item.dataset.tab === 'service') loadServicePage();
        if (item.dataset.tab === 'settings') loadSettings();
        if (item.dataset.tab === 'lists') loadList(currentList);
        if (item.dataset.tab === 'tests') loadTestResults();
    });
});

// === STATUS POLLING (#3) ===
function startStatusPolling() {
    stopStatusPolling();
    statusPollingTimer = setInterval(() => {
        if (activeTab === 'dashboard') loadStatus();
    }, 5000);
}
function stopStatusPolling() {
    if (statusPollingTimer) { clearInterval(statusPollingTimer); statusPollingTimer = null; }
}

// === DASHBOARD ===
async function loadStatus() {
    try {
        const res = await csrfFetch('/api/status');
        const data = await res.json();
        if (data.installed === false) return;

        const card = document.getElementById('global-status-card');
        const badge = document.getElementById('status-badge');
        const winwsEl = document.getElementById('dash-winws');
        const serviceEl = document.getElementById('dash-service');
        const windivertEl = document.getElementById('dash-windivert');
        const strategyEl = document.getElementById('dash-strategy');

        if (data.winws_running) {
            card.className = 'card status-card running';
            badge.className = 'badge badge-success';
            badge.textContent = 'RUNNING';
            winwsEl.className = 'status-value running';
            winwsEl.textContent = 'RUNNING';
        } else {
            card.className = 'card status-card stopped';
            badge.className = 'badge badge-danger';
            badge.textContent = 'STOPPED';
            winwsEl.className = 'status-value stopped';
            winwsEl.textContent = 'STOPPED';
        }

        serviceEl.textContent = data.service_status;
        serviceEl.className = 'status-value ' + (data.service_status === 'RUNNING' ? 'running' : data.service_status === 'STOPPED' ? 'stopped' : '');
        windivertEl.textContent = data.windivert_status;
        windivertEl.className = 'status-value ' + (data.windivert_status === 'RUNNING' ? 'running' : data.windivert_status === 'STOPPED' ? 'stopped' : '');
        strategyEl.textContent = data.strategy || 'none';

        const verEl = document.getElementById('app-version');
        if (verEl && data.version) verEl.textContent = 'v' + data.version;
        document.getElementById('dash-game').textContent = data.game_filter;
        document.getElementById('dash-ipset').textContent = data.ipset_status;
        document.getElementById('dash-update').textContent = data.update_status;
    } catch (e) {
        console.error('Failed to load status:', e);
    }
}

// === STRATEGIES ===
async function loadStrategies() {
    try {
        const res = await csrfFetch('/api/strategies');
        const strategies = await res.json();
        const list = document.getElementById('strategy-list');
        if (strategies.length === 0) {
            list.innerHTML = '<div class="list-empty"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg><span>No strategy files found. Check the zapret directory.</span></div>';
            return;
        }
        list.innerHTML = '';
        strategies.forEach(s => {
            const row = document.createElement('div');
            row.className = 'list-row' + (s.active ? ' active' : '');
            row.innerHTML =
                '<span class="mono">' + escapeHtml(s.name) + '</span>' +
                '<span class="text-secondary">' + escapeHtml(s.filename) + '</span>' +
                '<span class="badge ' + (s.active ? 'badge-success' : 'badge-neutral') + '">' + (s.active ? 'ACTIVE' : 'IDLE') + '</span>';
            row.addEventListener('click', () => {
                list.querySelectorAll('.list-row').forEach(r => r.classList.remove('active'));
                row.classList.add('active');
            });
            row.dataset.bat = s.filename;
            list.appendChild(row);
        });
    } catch (e) {
        console.error('Failed to load strategies:', e);
    }
}

async function startStrategy() {
    const btn = document.getElementById('btn-start');
    const activeRow = document.querySelector('#strategy-list .list-row.active');
    if (!activeRow) { alert('Select a strategy first'); return; }
    const bat = activeRow.dataset.bat;
    btn.disabled = true;
    btn.textContent = 'Starting...';
    try {
        const res = await csrfFetch('/api/start', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({bat: bat})
        });
        const data = await res.json();
        if (data.success) {
            loadStrategies();
            loadStatus();
            showToast('Strategy started', 'success');
        } else {
            showToast(data.error || data.message || 'Failed to start', 'error');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg> Start';
    }
}

async function stopStrategy() {
    const btn = document.getElementById('btn-stop');
    btn.disabled = true;
    btn.textContent = 'Stopping...';
    try {
        const res = await csrfFetch('/api/stop', {method: 'POST'});
        const data = await res.json();
        loadStrategies();
        loadStatus();
        if (data.success) {
            showToast('Strategy stopped', 'success');
        } else {
            showToast(data.message || data.error || 'Failed to stop', 'error');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg> Stop';
    }
}

// === SERVICE ===
async function loadServicePage() {
    const select = document.getElementById('service-bat-select');
    try {
        const res = await csrfFetch('/api/strategies');
        const strategies = await res.json();
        select.innerHTML = '';
        strategies.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.filename;
            opt.textContent = s.name;
            select.appendChild(opt);
        });
        const statusRes = await csrfFetch('/api/status');
        const status = await statusRes.json();
        const display = document.getElementById('service-status-display');
        display.textContent = '';
        const t1 = document.createTextNode('Service status: ');
        const s1 = document.createElement('strong');
        s1.textContent = status.service_status || 'unknown';
        const br = document.createElement('br');
        const t2 = document.createTextNode('WinDivert: ');
        const s2 = document.createElement('strong');
        s2.textContent = status.windivert_status || 'unknown';
        display.append(t1, s1, br, t2, s2);
    } catch (e) {
        console.error('Failed to load service page:', e);
    }
}

async function installService() {
    const btn = document.getElementById('btn-service-install');
    const select = document.getElementById('service-bat-select');
    const bat = select.value;
    if (!bat) return;
    btn.disabled = true;
    btn.textContent = 'Installing...';
    try {
        const res = await csrfFetch('/api/service/install', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({bat: bat})
        });
        const data = await res.json();
        const display = document.getElementById('service-status-display');
        display.textContent = '';
        const span = document.createElement('span');
        span.style.color = data.success ? 'var(--color-success)' : 'var(--color-danger)';
        span.textContent = data.success ? data.message : (data.error || 'Failed');
        display.appendChild(span);
        if (data.success) {
            showToast('Service installed', 'success');
        }
        loadServicePage();
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Install Service';
    }
}

async function removeService() {
    if (!confirm('Remove zapret service?')) return;
    const btn = document.getElementById('btn-service-remove');
    btn.disabled = true;
    btn.textContent = 'Removing...';
    try {
        const res = await csrfFetch('/api/service/remove', {method: 'POST'});
        const data = await res.json();
        const display = document.getElementById('service-status-display');
        display.textContent = '';
        const span = document.createElement('span');
        span.style.color = data.success ? 'var(--color-success)' : 'var(--color-danger)';
        span.textContent = data.success ? data.message : (data.message || data.error || 'Failed');
        display.appendChild(span);
        if (data.success) {
            showToast('Service removed', 'success');
        } else {
            showToast(data.message || data.error || 'Failed to remove', 'error');
        }
        loadServicePage();
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg> Remove Service';
    }
}

// === SETTINGS ===
async function loadSettings() {
    try {
        const res = await csrfFetch('/api/settings');
        const data = await res.json();
        if (data.installed === false) return;
        document.querySelectorAll('#game-filter-group .toggle-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.mode === data.game_filter);
        });
        document.querySelectorAll('#ipset-filter-group .toggle-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.mode === data.ipset_status);
        });
        document.getElementById('auto-update-switch').checked = data.update_status === 'enabled';
    } catch (e) {
        console.error('Failed to load settings:', e);
    }
}

async function setGameFilter(mode) {
    try {
        const res = await csrfFetch('/api/settings/game', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({mode: mode})
        });
        const data = await res.json();
        if (data.success) {
            loadSettings();
            showToast('Game filter: ' + mode, 'success');
        } else {
            showToast(data.error || 'Failed to save', 'error');
        }
    } catch (e) {
        showToast('Failed to save', 'error');
    }
}

async function setIpsetFilter(mode) {
    try {
        const res = await csrfFetch('/api/settings/ipset', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({mode: mode})
        });
        const data = await res.json();
        if (data.success) {
            loadSettings();
            showToast('IPSet filter: ' + mode, 'success');
        } else {
            showToast(data.error || 'Failed to save', 'error');
        }
    } catch (e) {
        showToast('Failed to save', 'error');
    }
}

async function setAutoUpdate(enabled) {
    try {
        const res = await csrfFetch('/api/settings/update', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({enabled: enabled})
        });
        const data = await res.json();
        if (data.success) {
            showToast('Auto-update: ' + (enabled ? 'enabled' : 'disabled'), 'success');
        } else {
            showToast(data.error || 'Failed to save', 'error');
        }
    } catch (e) {
        showToast('Failed to save', 'error');
    }
}

// === LISTS ===
function selectList(el) {
    document.querySelectorAll('.list-file-item').forEach(i => i.classList.remove('active'));
    el.classList.add('active');
    currentList = el.dataset.list;
    document.getElementById('current-list-name').textContent = el.textContent.trim();
    loadList(currentList);
}

async function loadList(name) {
    try {
        const res = await csrfFetch('/api/lists/' + name);
        const data = await res.json();
        const editor = document.getElementById('list-editor');
        editor.value = data.content || '';
        currentListContent = data.content || '';
        updateLineCount();
    } catch (e) {
        console.error('Failed to load list:', e);
    }
}

function updateLineCount() {
    const editor = document.getElementById('list-editor');
    const lines = editor.value.split('\n').filter(l => l.trim()).length;
    document.getElementById('list-line-count').textContent = lines + ' lines';
}

document.getElementById('list-editor').addEventListener('input', updateLineCount);

// #6 Domain validation
function validateEntry(entry) {
    entry = entry.trim().replace(/^https?:\/\//, '').replace(/\/+$/, '');
    if (!entry) return {valid: false, cleaned: '', reason: 'Empty entry'};
    if (/^PING:/i.test(entry)) {
        const ip = entry.replace(/^PING:/i, '');
        if (/^\d{1,3}(\.\d{1,3}){3}$/.test(ip)) return {valid: true, cleaned: entry};
        return {valid: false, cleaned: entry, reason: 'Invalid ping target'};
    }
    if (/^[\d\.\/]+$/.test(entry)) {
        if (/^\d{1,3}(\.\d{1,3}){3}(\/\d{1,2})?$/.test(entry)) return {valid: true, cleaned: entry};
        return {valid: false, cleaned: entry, reason: 'Invalid IP address'};
    }
    if (/^[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+$/.test(entry)) {
        return {valid: true, cleaned: entry};
    }
    return {valid: false, cleaned: entry, reason: 'Invalid domain format'};
}

async function addListEntry() {
    const input = document.getElementById('list-add-input');
    const feedback = document.getElementById('list-feedback');
    const rawEntry = input.value.trim();

    if (!rawEntry) {
        feedback.textContent = 'Enter a domain or IP';
        feedback.className = 'list-feedback error';
        return;
    }

    const validation = validateEntry(rawEntry);
    if (!validation.valid) {
        input.classList.add('duplicate');
        feedback.textContent = validation.reason;
        feedback.className = 'list-feedback error';
        setTimeout(() => input.classList.remove('duplicate'), 2000);
        return;
    }
    const entry = validation.cleaned;

    const existing = document.getElementById('list-editor').value.split('\n').map(l => l.trim()).filter(l => l);
    if (existing.includes(entry)) {
        input.classList.add('duplicate');
        feedback.textContent = 'Already exists in list';
        feedback.className = 'list-feedback error';
        setTimeout(() => input.classList.remove('duplicate'), 2000);
        return;
    }

    try {
        const res = await csrfFetch('/api/lists/' + currentList + '/add', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({entry: entry})
        });
        const data = await res.json();
        if (data.success) {
            feedback.textContent = 'Added: ' + entry;
            feedback.className = 'list-feedback success';
            input.value = '';
            input.classList.remove('duplicate');
            await loadList(currentList);
        } else if (data.duplicate) {
            input.classList.add('duplicate');
            feedback.textContent = 'Already exists';
            feedback.className = 'list-feedback error';
            setTimeout(() => input.classList.remove('duplicate'), 2000);
        } else {
            feedback.textContent = data.error || 'Error';
            feedback.className = 'list-feedback error';
        }
    } catch (e) {
        feedback.textContent = 'Network error';
        feedback.className = 'list-feedback error';
    }
    setTimeout(() => { feedback.textContent = ''; feedback.className = 'list-feedback'; }, 3000);
}

function clearListEditor() {
    document.getElementById('list-editor').value = '';
    updateLineCount();
}

async function saveList() {
    const btn = document.getElementById('btn-list-save');
    const editor = document.getElementById('list-editor');
    const feedback = document.getElementById('list-feedback');
    btn.disabled = true;
    btn.textContent = 'Saving...';
    try {
        const res = await csrfFetch('/api/lists/' + currentList, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({content: editor.value})
        });
        const data = await res.json();
        if (data.success) {
            feedback.textContent = 'Saved';
            feedback.className = 'list-feedback success';
            showToast('List saved', 'success');
        } else {
            feedback.textContent = data.error || 'Error saving';
            feedback.className = 'list-feedback error';
        }
    } catch (e) {
        feedback.textContent = 'Network error';
        feedback.className = 'list-feedback error';
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> Save';
    }
    setTimeout(() => { feedback.textContent = ''; feedback.className = 'list-feedback'; }, 3000);
}

document.getElementById('list-add-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') addListEntry();
});

// === DIAGNOSTICS (#4, #5) ===
const SVG_OK = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:4px"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>';
const SVG_WARN = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:4px"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
const SVG_FAIL = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:4px"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';

async function runDiagnostics() {
    const btn = document.getElementById('btn-diagnostics');
    const output = document.getElementById('diagnostics-output');
    const autoScroll = document.getElementById('autoscroll-diagnostics');
    btn.disabled = true;
    btn.textContent = 'Running...';
    output.innerHTML = '';
    try {
        const response = await csrfFetch('/api/diagnostics');
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            const text = decoder.decode(value, {stream: true});
            const lines = text.split('\n');
            lines.forEach(line => {
                if (!line) return;
                const span = document.createElement('span');
                let icon = '';
                if (line.startsWith('[OK]')) {
                    span.className = 'line-success';
                    icon = SVG_OK;
                } else if (line.startsWith('[FAIL]')) {
                    span.className = 'line-error';
                    icon = SVG_FAIL;
                } else if (line.startsWith('[WARN]')) {
                    span.className = 'line-warning';
                    icon = SVG_WARN;
                } else if (line.startsWith('---')) {
                    span.className = 'line-info';
                }
                span.innerHTML = icon + escapeHtml(line) + '\n';
                output.appendChild(span);
            });
            if (autoScroll.checked) output.scrollTop = output.scrollHeight;
        }
    } catch (e) {
        const span = document.createElement('span');
        span.className = 'line-error';
        span.innerHTML = SVG_FAIL + escapeHtml('Error: ' + e.message) + '\n';
        output.appendChild(span);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg> Run Diagnostics';
    }
}

function copyLog(elementId) {
    const el = document.getElementById(elementId);
    const text = el.textContent || el.innerText;
    navigator.clipboard.writeText(text).then(() => showToast('Copied to clipboard', 'success'));
}

// === TESTS (#1 - formatTestOutput) ===
function formatTestOutput(rawText) {
    if (!rawText) return '';
    const lines = rawText.split('\n');
    return lines.map(line => {
        let colored = escapeHtml(line);
        colored = colored.replace(/\b(OK)\b/g, '<span class="line-success">$1</span>');
        colored = colored.replace(/(HTTP:OK|TLS1\.2:OK|TLS1\.3:OK)/g, '<span class="line-success">$1</span>');
        colored = colored.replace(/\b(ERROR|FAIL|SSL)\b/g, '<span class="line-error">$1</span>');
        colored = colored.replace(/(HTTP:ERROR)/g, '<span class="line-error">$1</span>');
        colored = colored.replace(/\b(UNSUP|UNSUPPORTED)\b/g, '<span class="line-warning">$1</span>');
        colored = colored.replace(/\b(LIKELY_BLOCKED)\b/g, '<span class="line-error">$1</span>');
        colored = colored.replace(/\b(RUNNING|STOPPED|FOUND|passed|enabled)\b/gi, '<span class="line-success">$1</span>');
        colored = colored.replace(/(Best config:|Best strategy:)/g, '<span class="line-info" style="font-weight:700">$1</span>');
        if (/^(={3,}|-{3,}|Config:|\s*Target:)/.test(line)) {
            colored = '<span class="line-info">' + colored + '</span>';
        }
        return colored;
    }).join('\n');
}

// === TESTS ===

async function runTests() {
    const btn = document.getElementById('btn-run-tests');
    btn.disabled = true;
    btn.textContent = 'Launching...';
    try {
        const res = await csrfFetch('/api/tests/run', {method: 'POST'});
        const data = await res.json();
        if (data.success) {
            showToast('Tests launched in PowerShell', 'success');
        } else {
            showToast(data.error || 'Failed to launch tests', 'error');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg> Run Tests';
    }
}

async function loadTestResults() {
    try {
        const res = await csrfFetch('/api/test-results');
        const results = await res.json();
        const list = document.getElementById('test-results-list');
        if (results.length === 0) {
            list.innerHTML = '<div class="list-empty"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></svg><span>No test results found</span></div>';
            return;
        }
        list.innerHTML = '';
        results.forEach(r => {
            const row = document.createElement('div');
            row.className = 'list-row';
            row.innerHTML =
                '<span class="mono">' + escapeHtml(r.name) + '</span>' +
                '<span class="text-secondary">' + escapeHtml(r.date) + '</span>' +
                '<span class="text-secondary">' + formatSize(r.size) + '</span>';
            row.addEventListener('click', () => viewTestResult(r.name));
            list.appendChild(row);
        });
    } catch (e) {
        console.error('Failed to load test results:', e);
    }
}

async function viewTestResult(name) {
    const viewer = document.getElementById('test-result-viewer');
    const nameEl = document.getElementById('test-result-name');
    const output = document.getElementById('test-result-output');
    viewer.style.display = 'block';
    nameEl.textContent = name;
    output.innerHTML = 'Loading...';
    try {
        const res = await csrfFetch('/api/test-results/' + encodeURIComponent(name));
        const data = await res.json();
        output.innerHTML = formatTestOutput(data.content || data.error || 'Empty');
    } catch (e) {
        output.innerHTML = '<span class="line-error">Error loading result: ' + escapeHtml(e.message) + '</span>';
    }
}

// === UTILITIES ===
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// === SETUP / INSTALL ===
async function checkSetup() {
    try {
        const res = await csrfFetch('/api/setup/status');
        const data = await res.json();
        if (!data.installed) {
            document.getElementById('setup-screen').style.display = 'flex';
            document.querySelector('.layout').style.display = 'none';
        } else {
            document.getElementById('setup-screen').style.display = 'none';
            document.querySelector('.layout').style.display = 'flex';
            loadStatus();
            startStatusPolling();
            checkUpdate();
        }
    } catch (e) {
        console.error('Setup check failed:', e);
        const setupTitle = document.querySelector('.setup-title');
        const setupText = document.querySelector('#setup-screen .text-secondary');
        if (setupTitle) setupTitle.textContent = 'Server not running';
        if (setupText) setupText.textContent = 'Failed to connect to Flask server. Make sure zapret_gui.py is running.';
        document.getElementById('setup-screen').style.display = 'flex';
        document.querySelector('.layout').style.display = 'none';
    }
}

async function downloadZapret() {
    const btn = document.getElementById('btn-download');
    const progressDiv = document.getElementById('setup-progress');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');
    btn.disabled = true;
    btn.textContent = 'Starting...';
    progressDiv.style.display = 'block';
    try {
        await csrfFetch('/api/setup/download', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({mode: 'install'})
        });
        const sse = new EventSource('/api/setup/progress');
        sse.onmessage = (e) => {
            const data = JSON.parse(e.data);
            progressFill.style.width = data.percent + '%';
            progressText.textContent = data.message;
            if (data.status === 'done') {
                sse.close();
                progressText.textContent = 'Installation complete. Reloading...';
                setTimeout(() => location.reload(), 1500);
            } else if (data.status === 'error') {
                sse.close();
                btn.disabled = false;
                btn.textContent = 'Retry';
                progressText.textContent = 'Error: ' + data.message;
                progressFill.style.background = 'var(--color-danger)';
            }
        };
        sse.onerror = () => {
            sse.close();
            btn.disabled = false;
            btn.textContent = 'Retry';
            progressText.textContent = 'Connection lost. Try again.';
        };
    } catch (e) {
        btn.disabled = false;
        btn.textContent = 'Retry';
        progressText.textContent = 'Error: ' + e.message;
    }
}

async function updateZapret() {
    const btn = document.getElementById('btn-update');
    const banner = document.getElementById('update-banner');
    const statusText = document.getElementById('update-text');
    btn.disabled = true;
    btn.textContent = 'Updating...';
    try {
        await csrfFetch('/api/setup/download', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({mode: 'update'})
        });
        const sse = new EventSource('/api/setup/progress');
        sse.onmessage = (e) => {
            const data = JSON.parse(e.data);
            statusText.textContent = data.message;
            if (data.status === 'done') {
                sse.close();
                banner.style.display = 'none';
                loadStatus();
                showToast('Zapret updated', 'success');
            } else if (data.status === 'error') {
                sse.close();
                btn.disabled = false;
                btn.textContent = 'Retry';
                statusText.textContent = 'Error: ' + data.message;
            }
        };
        sse.onerror = () => {
            sse.close();
            btn.disabled = false;
            btn.textContent = 'Retry';
            statusText.textContent = 'Connection lost. Try again.';
        };
    } catch (e) {
        btn.disabled = false;
        btn.textContent = 'Retry';
        statusText.textContent = 'Error: ' + e.message;
    }
}

async function checkUpdate() {
    try {
        const res = await csrfFetch('/api/setup/update-check');
        const data = await res.json();
        if (data.update_available) {
            const banner = document.getElementById('update-banner');
            const text = document.getElementById('update-text');
            text.textContent = 'New version available: ' + (data.remote_version || '') + ' (current: ' + (data.local_version || '') + ')';
            banner.style.display = 'flex';
        }
    } catch (e) {
        console.log('Update check failed:', e);
    }
}

// === INIT ===
document.addEventListener('DOMContentLoaded', () => {
    checkSetup();
});
