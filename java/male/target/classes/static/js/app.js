// MALE - WebSocket STOMP Client

let stompClient = null;
let connected = false;
let loadingInterval = null;
let loadingStart = 0;
let currentMaxTurns = 25;

const COLORS = {
    'Arquiteto': '#94e2d5', 'SRE': '#f38ba8', 'DevOps': '#a6e3a1',
    'DBA': '#f9e2af', 'Security': '#cba6f7', 'PO': '#89b4fa',
    'Scrum Master': '#cdd6f4', 'Gerente': '#fab387', 'Dev Senior': '#fab387'
};

const SPINNER_FRAMES = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏'];

// Connect on page load
document.addEventListener('DOMContentLoaded', function() {
    connect();
    initModeToggle();
    loadHistorySidebar();
});

// ===== WEBSOCKET =====
function connect() {
    const socket = new SockJS('/ws');
    stompClient = Stomp.over(socket);
    stompClient.debug = null;

    stompClient.connect({}, function() {
        connected = true;
        setStatus('connected', 'Conectado. Pronto para debater.');

        stompClient.subscribe('/topic/debate/event', function(msg) {
            handleEvent(JSON.parse(msg.body));
        });
        stompClient.subscribe('/topic/error', function(msg) {
            addEvent('Erro: ' + JSON.parse(msg.body).message);
        });
    }, function() {
        connected = false;
        setStatus('error', 'Desconectado. Reconectando...');
        setTimeout(connect, 3000);
    });
}

function setStatus(state, text) {
    const dot = document.getElementById('statusDot');
    const txt = document.getElementById('statusText');
    if (dot) {
        dot.className = 'status-dot';
        if (state === 'connected') dot.classList.add('connected');
        else if (state === 'running') dot.classList.add('running');
    }
    if (txt) txt.textContent = text;
}

// ===== MODE TOGGLE =====
function initModeToggle() {
    document.querySelectorAll('input[name="mode"]').forEach(radio => {
        radio.addEventListener('change', function() {
            const dur = document.querySelector('.param-duration');
            if (dur) dur.style.display = this.value === 'autonomous' ? 'block' : 'none';
        });
    });
}

// ===== DEBATE CONTROL =====
function startDebate() {
    if (!connected) { alert('Nao conectado ao servidor.'); return; }

    const topic = document.getElementById('topic').value.trim();
    if (!topic) { document.getElementById('topic').focus(); return; }

    const mode = document.querySelector('input[name="mode"]:checked').value;
    const model = document.getElementById('model').value;
    const maxTurns = parseInt(document.getElementById('maxTurns').value) || 25;
    const duration = parseFloat(document.getElementById('duration').value) || 8;
    currentMaxTurns = maxTurns;

    document.getElementById('startBtn').disabled = true;
    document.getElementById('stopBtn').style.display = 'inline-block';
    document.getElementById('exportBtn').style.display = 'none';
    document.getElementById('topicLabel').textContent = topic;

    const feed = document.getElementById('feed');
    feed.innerHTML = '';
    document.getElementById('feedEmpty')?.remove();

    setStatus('running', 'Iniciando...');
    showLoading('Preparando debate...');

    const payload = { mode: mode, topic: topic, model: model, maxTurns: maxTurns };
    if (mode === 'autonomous') payload.durationHours = duration;

    stompClient.send('/app/debate/start', {}, JSON.stringify(payload));
}

function stopDebate() {
    if (connected) {
        stompClient.send('/app/debate/stop', {}, '');
    }
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').style.display = 'none';
    hideLoading();
    setStatus('connected', 'Interrompido.');
}

// ===== EVENT HANDLER =====
function handleEvent(evt) {
    const event = evt.event;
    const data = evt;

    switch (event) {
        case 'debate_start':
            addEvent('Debate: ' + (data.topic || ''));
            showLoading('Debate iniciado...');
            break;

        case 'turn_start':
            document.getElementById('turnBadge').textContent = 'Turno ' + data.turn;
            setStatus('running', 'Turno ' + data.turn + ' - ' + data.agent);
            showLoading(data.agent + ' analisando...');
            updateProgress(data.turn, currentMaxTurns);
            break;

        case 'turn_end':
            addTurn(data);
            break;

        case 'debate_complete':
            addEvent('Encerrado: ' + (data.reason || '') + ' (' + (data.totalTurns || 0) + ' turnos)');
            document.getElementById('startBtn').disabled = false;
            document.getElementById('stopBtn').style.display = 'none';
            document.getElementById('exportBtn').style.display = 'inline-block';
            hideLoading();
            setStatus('connected', 'Debate finalizado.');
            loadHistorySidebar();
            break;

        case 'session_start':
            addEvent('Sessao autonoma: ' + data.sessionId + ' (' + data.durationHours + 'h)');
            setStatus('running', 'Sessao autonoma...');
            showLoading('Sessao autonoma rodando...');
            break;

        case 'session_complete':
            addEvent('Sessao completa: ' + data.totalDebates + ' debates');
            document.getElementById('startBtn').disabled = false;
            document.getElementById('stopBtn').style.display = 'none';
            hideLoading();
            setStatus('connected', 'Sessao finalizada.');
            loadHistorySidebar();
            break;

        case 'session_stopped':
            document.getElementById('startBtn').disabled = false;
            document.getElementById('stopBtn').style.display = 'none';
            hideLoading();
            setStatus('connected', 'Interrompido.');
            break;

        case 'error':
            addEvent('Erro: ' + (data.message || 'desconhecido'));
            document.getElementById('startBtn').disabled = false;
            document.getElementById('stopBtn').style.display = 'none';
            document.getElementById('exportBtn').style.display = 'inline-block';
            hideLoading();
            setStatus('error', 'Erro: ' + (data.message || ''));
            break;
    }
}

// ===== FEED =====
function addTurn(d) {
    const feed = document.getElementById('feed');
    if (!feed) return;

    const color = COLORS[d.agent] || '#cdd6f4';
    const statusClass = (d.status || '').replace(' ', '-');
    const voteClass = d.vote === 'agree' ? 'vote-agree' : d.vote === 'disagree' ? 'vote-disagree' : 'vote-abstain';

    const div = document.createElement('div');
    div.className = 'msg ' + statusClass;
    div.innerHTML =
        '<div class="msg-header">' +
            '<div>' +
                '<span class="agent-name" style="color:' + color + '">' + esc(d.agent) + '</span>' +
                '<span class="agent-turn">T' + (d.turn || '?') + '</span>' +
            '</div>' +
            '<span class="status-badge ' + statusClass + '">' + esc(d.status) + '</span>' +
        '</div>' +
        '<div class="msg-content">' + esc(d.argument) + '</div>' +
        '<div class="msg-vote">voto: <span class="' + voteClass + '">' + esc(d.vote) + '</span></div>';

    feed.appendChild(div);
    feed.scrollTop = feed.scrollHeight;
}

function addEvent(text) {
    const feed = document.getElementById('feed');
    if (!feed) return;
    const div = document.createElement('div');
    div.className = 'event-msg';
    div.textContent = text;
    feed.appendChild(div);
    feed.scrollTop = feed.scrollHeight;
}

function esc(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

// ===== LOADING =====
function showLoading(msg) {
    const bar = document.getElementById('loadingBar');
    const msgEl = document.getElementById('loadingMsg');
    const timeEl = document.getElementById('loadingTime');
    bar.style.display = 'flex';
    msgEl.textContent = msg || 'Carregando...';
    loadingStart = Date.now();

    let frame = 0;
    if (loadingInterval) clearInterval(loadingInterval);
    loadingInterval = setInterval(function() {
        document.getElementById('spinner').textContent = SPINNER_FRAMES[frame % SPINNER_FRAMES.length];
        frame++;
        const elapsed = Math.floor((Date.now() - loadingStart) / 1000);
        timeEl.textContent = '(' + elapsed + 's)';
    }, 100);
}

function hideLoading() {
    if (loadingInterval) { clearInterval(loadingInterval); loadingInterval = null; }
    document.getElementById('loadingBar').style.display = 'none';
}

function updateProgress(turn, max) {
    const pct = Math.min(100, Math.round((turn / max) * 100));
    document.getElementById('progressBar').style.width = pct + '%';
    document.getElementById('progressText').textContent = pct + '%';
}

// ===== SIDEBAR =====
function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tabName));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + tabName));
    if (tabName === 'history') loadHistorySidebar();
    if (tabName === 'projects') loadProjects();
    if (tabName === 'knowledge') loadKnowledge();
}

function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('collapsed');
}

async function loadHistorySidebar() {
    const list = document.getElementById('historyList');
    if (!list) return;
    list.innerHTML = '<div class="empty-state"><p>Carregando...</p></div>';

    try {
        const res = await fetch('/api/debates?limit=20');
        const data = await res.json();
        if (!data.debates || data.debates.length === 0) {
            list.innerHTML = '<div class="empty-state"><p>Nenhum debate ainda</p></div>';
            return;
        }
        list.innerHTML = '';
        for (const d of data.debates) {
            const div = document.createElement('div');
            div.className = 'history-item';
            div.onclick = () => loadDebateMessages(d.conversationId, div);
            const icon = d.consensus ? '&#x2713;' : '...';
            div.innerHTML =
                '<span class="status-icon">' + icon + '</span>' +
                '<h4>' + esc(d.topic || 'Sem topico') + '</h4>' +
                '<p>' + esc(d.createdAt || '') + ' &middot; ' + (d.messageCount || 0) + ' msgs</p>';
            list.appendChild(div);
        }
    } catch (e) {
        list.innerHTML = '<div class="empty-state"><p>Erro ao carregar</p></div>';
    }
}

async function loadDebateMessages(conversationId, parent) {
    const existing = parent.querySelector('.history-detail');
    if (existing) { existing.remove(); return; }

    document.querySelectorAll('.history-item').forEach(i => i.classList.remove('active'));
    parent.classList.add('active');

    try {
        const res = await fetch('/api/debates/' + conversationId + '/messages');
        const data = await res.json();
        const detail = document.createElement('div');
        detail.className = 'history-detail';
        for (const m of (data.messages || [])) {
            const msg = document.createElement('div');
            msg.className = 'history-msg';
            const color = COLORS[m.agentName] || '#cdd6f4';
            msg.innerHTML =
                '<div class="h-agent" style="color:' + color + '">' + esc(m.agentName) + ' (T' + (m.turnNumber || '?') + ')</div>' +
                '<div class="h-arg">' + esc(m.content) + '</div>';
            detail.appendChild(msg);
        }
        parent.appendChild(detail);
    } catch (e) {}
}

async function loadProjects() {
    const list = document.getElementById('projectList');
    if (!list) return;
    list.innerHTML = '<div class="empty-state"><p>Em breve...</p></div>';
}

async function loadKnowledge() {
    const list = document.getElementById('knowledgeList');
    if (!list) return;
    list.innerHTML = '<div class="empty-state"><p>Em breve...</p></div>';
}

// ===== SCENARIO =====
async function generateScenario() {
    const input = document.getElementById('topic');
    input.value = 'Gerando...';
    input.disabled = true;
    try {
        const res = await fetch('/api/scenario');
        const data = await res.json();
        input.value = data.topic || 'Microservicos vs Monolito';
    } catch (e) {
        const fallback = [
            'Microservicos vs Monolito: quando a complexidade nao compensa',
            'Event sourcing: quando vale a pena implementar?',
            'CI/CD com GitHub Actions vs GitLab CI: pros e contras',
            'Kafka vs RabbitMQ: qual fila de mensagens escolher?',
            'Git flow vs trunk-based development: qual adotar?'
        ];
        input.value = fallback[Math.floor(Math.random() * fallback.length)];
    } finally {
        input.disabled = false;
        input.focus();
    }
}

// ===== EXPORT =====
function exportChat() {
    const feed = document.getElementById('feed');
    const topic = document.getElementById('topicLabel').textContent;
    if (!feed || !feed.children.length) return;

    let md = '# Debate: ' + topic + '\n\n';
    for (const child of feed.children) {
        if (child.classList.contains('event-msg')) {
            md += '> ' + child.textContent + '\n\n';
        } else if (child.classList.contains('msg')) {
            const agent = child.querySelector('.agent-name')?.textContent || '';
            const content = child.querySelector('.msg-content')?.textContent || '';
            const vote = child.querySelector('.msg-vote')?.textContent || '';
            const status = child.querySelector('.status-badge')?.textContent || '';
            md += '## ' + agent + ' [' + status + ']\n\n';
            md += content + '\n\n';
            md += '*' + vote + '*\n\n---\n\n';
        }
    }

    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'debate-' + topic.replace(/[^a-zA-Z0-9]/g, '-').substring(0, 50) + '.md';
    a.click();
    URL.revokeObjectURL(url);
}
