// MALE - WebSocket STOMP Client

let stompClient = null;
let connected = false;

const COLORS = {
    'Arquiteto': '#94e2d5', 'SRE': '#f38ba8', 'DevOps': '#a6e3a1',
    'DBA': '#f9e2af', 'Security': '#cba6f7', 'PO': '#89b4fa',
    'Scrum Master': '#cdd6f4', 'Gerente': '#fab387', 'Dev Senior': '#fab387'
};

// Connect on page load
document.addEventListener('DOMContentLoaded', connect);

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

function startDebate(e) {
    e.preventDefault();
    if (!connected) { alert('Nao conectado ao servidor.'); return false; }

    const topic = document.getElementById('topic').value.trim();
    if (!topic) return false;

    const model = document.getElementById('model').value;
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    const feedContainer = document.getElementById('feedContainer');

    startBtn.disabled = true;
    stopBtn.style.display = 'inline-block';
    feedContainer.style.display = 'block';
    document.getElementById('feed').innerHTML = '';
    document.getElementById('topicLabel').textContent = topic;
    document.getElementById('exportBtn').style.display = 'none';

    setStatus('running', 'Debate iniciando...');
    addEvent('Topico: ' + topic);

    stompClient.send('/app/debate/start', {}, JSON.stringify({
        mode: 'single',
        topic: topic,
        model: model,
        maxTurns: 25
    }));

    return false;
}

function stopDebate() {
    if (connected) {
        stompClient.send('/app/debate/stop', {}, '');
    }
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').style.display = 'none';
    setStatus('connected', 'Sessao interrompida.');
}

function handleEvent(evt) {
    const event = evt.event;
    const data = evt;

    switch (event) {
        case 'debate_start':
            addEvent('Debate iniciado: ' + (data.topic || ''));
            break;

        case 'turn_start':
            document.getElementById('turnBadge').textContent = 'Turno ' + data.turn;
            setStatus('running', 'Turno ' + data.turn + ' - ' + data.agent);
            break;

        case 'turn_end':
            addTurn(data);
            break;

        case 'debate_complete':
            addEvent('Encerrado: ' + (data.reason || '') + ' (' + (data.totalTurns || 0) + ' turnos)');
            document.getElementById('startBtn').disabled = false;
            document.getElementById('stopBtn').style.display = 'none';
            document.getElementById('exportBtn').style.display = 'inline-block';
            setStatus('connected', 'Debate finalizado.');
            break;

        case 'session_start':
            addEvent('Sessao autonoma: ' + data.sessionId + ' (' + data.durationHours + 'h)');
            setStatus('running', 'Sessao autonoma rodando...');
            break;

        case 'session_complete':
            addEvent('Sessao completa: ' + data.totalDebates + ' debates');
            document.getElementById('startBtn').disabled = false;
            document.getElementById('stopBtn').style.display = 'none';
            setStatus('connected', 'Sessao finalizada.');
            break;

        case 'session_stopped':
            document.getElementById('startBtn').disabled = false;
            document.getElementById('stopBtn').style.display = 'none';
            setStatus('connected', 'Interrompido.');
            break;

        case 'error':
            addEvent('Erro: ' + (data.message || 'desconhecido'));
            document.getElementById('startBtn').disabled = false;
            document.getElementById('stopBtn').style.display = 'none';
            document.getElementById('exportBtn').style.display = 'inline-block';
            setStatus('error', 'Erro: ' + (data.message || ''));
            break;
    }
}

function addTurn(d) {
    const feed = document.getElementById('feed');
    if (!feed) return;

    const color = COLORS[d.agent] || '#cdd6f4';
    const statusClass = (d.status || '').replace(' ', '-');
    const voteClass = d.vote === 'agree' ? 'vote-agree' : d.vote === 'disagree' ? 'vote-disagree' : '';

    const div = document.createElement('div');
    div.className = 'msg ' + statusClass;
    div.innerHTML =
        '<div class="msg-header">' +
            '<span class="agent-name" style="color:' + color + '">' + esc(d.agent) + '</span>' +
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

// History
async function loadHistory() {
    const modal = document.getElementById('historyModal');
    const list = document.getElementById('historyList');
    modal.style.display = 'flex';
    list.innerHTML = '<div class="empty-state">Carregando...</div>';

    try {
        const res = await fetch('/api/debates?limit=20');
        const data = await res.json();
        if (!data.debates || data.debates.length === 0) {
            list.innerHTML = '<div class="empty-state">Nenhum debate encontrado.</div>';
            return;
        }
        list.innerHTML = '';
        for (const d of data.debates) {
            const div = document.createElement('div');
            div.className = 'history-item';
            div.onclick = () => loadDebateMessages(d.conversationId, div);
            div.innerHTML =
                '<h3>' + esc(d.topic || 'Sem topico') + '</h3>' +
                '<p>' + esc(d.createdAt || '') + ' &middot; ' + (d.messageCount || 0) + ' mensagens</p>';
            list.appendChild(div);
        }
    } catch (e) {
        list.innerHTML = '<div class="empty-state">Erro ao carregar historico.</div>';
    }
}

async function loadDebateMessages(conversationId, parent) {
    const existing = parent.querySelector('.history-detail');
    if (existing) { existing.remove(); return; }

    try {
        const res = await fetch('/api/debates/' + conversationId + '/messages');
        const data = await res.json();
        const detail = document.createElement('div');
        detail.className = 'history-detail';
        for (const m of (data.messages || [])) {
            const msg = document.createElement('div');
            msg.className = 'history-msg';
            msg.innerHTML =
                '<div class="h-agent">' + esc(m.agentName) + ' (T' + (m.turnNumber || '?') + ')</div>' +
                '<div class="h-arg">' + esc(m.content) + '</div>';
            detail.appendChild(msg);
        }
        parent.appendChild(detail);
    } catch (e) {}
}

function closeHistory(e) {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.style.display = 'none';
    }
}

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
