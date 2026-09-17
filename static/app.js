/**
 * VisionAI FaceShield — Frontend Application Logic
 * Real-time updates via SSE (/api/events) + light stats polling.
 */

let currentTab = 'live';
let videoSource = 'server';
let browserStream = null;
let browserCamInterval = null;
let allPeopleCache = [];
let allLogsCache = [];
let eventSource = null;
let audioAlertsEnabled = true;
let audioCtx = null;

// ─── Audio Chimes (Web Audio API) ────────────────────────────

function playAudioChime(type = 'known') {
    if (!audioAlertsEnabled) return;
    try {
        if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
        if (audioCtx.state === 'suspended') {
            audioCtx.resume();
        }
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.connect(gain);
        gain.connect(audioCtx.destination);

        const now = audioCtx.currentTime;
        if (type === 'new') {
            osc.frequency.setValueAtTime(587.33, now); // D5
            osc.frequency.exponentialRampToValueAtTime(880.00, now + 0.15); // A5
            gain.gain.setValueAtTime(0.15, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
            osc.start(now);
            osc.stop(now + 0.35);
        } else {
            osc.frequency.setValueAtTime(523.25, now); // C5
            osc.frequency.exponentialRampToValueAtTime(659.25, now + 0.1); // E5
            gain.gain.setValueAtTime(0.08, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
            osc.start(now);
            osc.stop(now + 0.25);
        }
    } catch (e) {
        console.debug('Audio chime error:', e);
    }
}

function toggleAudioAlerts() {
    audioAlertsEnabled = !audioAlertsEnabled;
    const icon = document.getElementById('audio-toggle-icon');
    const checkbox = document.getElementById('setting-audio-alerts');
    if (checkbox) checkbox.checked = audioAlertsEnabled;
    if (icon) {
        icon.setAttribute('data-lucide', audioAlertsEnabled ? 'volume-2' : 'volume-x');
        if (window.lucide) lucide.createIcons();
    }
    showToast(`Alertas sonoros ${audioAlertsEnabled ? 'ativados' : 'desativados'}.`, 'info');
}

// ─── Initialization ──────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    if (window.lucide) lucide.createIcons();

    setupTabNavigation();
    startClock();
    pollStats();
    setInterval(pollStats, 4000);
    setInterval(fetchInsights, 6000);
    fetchInsights();
    loadRuntimeSettings();
    loadPeople();
    loadRTSPStreams();
    loadLogsTable();
    subscribeEvents();
});

// ─── Real-time events (SSE) ──────────────────────────────────

function subscribeEvents() {
    if (!window.EventSource) return;

    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource('/api/events');

    eventSource.onmessage = (event) => {
        let data;
        try { data = JSON.parse(event.data); } catch { return; }

        if (data.type === 'person_registered') {
            playAudioChime('new');
            showToast(`Nova pessoa registrada: ${data.name}`, 'success');
            loadPeople();
            openNamingPrompt(data.person_id, data.name);
        } else if (data.type === 'recognition' && data.status === 'known') {
            playAudioChime('known');
        } else if (data.type === 'presence_ended') {
            loadPeople();
        }
    };

    eventSource.onerror = () => {
        // EventSource auto-reconnects; nothing else to do.
    };
}

function openNamingPrompt(personId, defaultName) {
    const name = prompt(`Nomear ${defaultName || 'nova pessoa'}:`, '');
    if (name && name.trim()) renamePerson(personId, name.trim());
}

async function renamePerson(personId, name) {
    try {
        const res = await fetch(`/api/v1/persons/${personId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (res.ok) {
            showToast(`Pessoa renomeada para "${name}".`, 'success');
            loadPeople();
        } else {
            const err = await res.json();
            showToast(err.detail || 'Erro ao renomear.', 'danger');
        }
    } catch (e) {
        showToast('Erro de conexão ao renomear.', 'danger');
    }
}

// ─── Toast notifications ─────────────────────────────────────

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ─── Clock & Header ───────────────────────────────────────────

function startClock() {
    const clock = document.getElementById('header-clock');
    const update = () => {
        if (clock) clock.innerText = new Date().toLocaleTimeString('pt-BR');
    };
    update();
    setInterval(update, 1000);
}

// ─── Tab Navigation ──────────────────────────────────────────

function setupTabNavigation() {
    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.getAttribute('data-tab')));
    });
}

function switchTab(tabId) {
    currentTab = tabId;

    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-tab') === tabId);
    });

    document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.toggle('active', pane.id === `tab-${tabId}`);
    });

    const titles = {
        'live': ['Monitoramento ao Vivo', 'Transmissão em tempo real com InsightFace (ArcFace 512-d)'],
        'youtube': ['Análise de Vídeos do YouTube', 'Detecção e identificação facial automatizada em vídeos'],
        'rtsp': ['Câmeras RTSP & CFTV', 'Gerenciamento de streams de câmeras IP'],
        'register': ['Cadastro de Rostos', 'Registre perfis nomeados com embeddings de 512 dimensões'],
        'people': ['Pessoas Registradas', 'Diretório de perfis e histórico de presenças'],
        'analytics': ['Analytics & IA', 'Métricas de permanência, fluxo de visitantes e relatórios inteligentes'],
        'logs': ['Histórico de Detecções', 'Registro unificado de eventos no banco de dados'],
        'settings': ['Configurações', 'Sensibilidade, registro automático, cooldown e dispositivos'],
        'events-tab': ['Eventos & Presença', 'Crie eventos de verificação e acompanhe a lista de presença']
    };
    if (titles[tabId]) {
        document.getElementById('page-title').innerText = titles[tabId][0];
        document.getElementById('page-desc').innerText = titles[tabId][1];
    }

    if (tabId === 'people') loadPeople();
    if (tabId === 'rtsp') loadRTSPStreams();
    if (tabId === 'logs') loadLogsTable();
    if (tabId === 'analytics') loadAnalyticsTimeline();
    if (tabId === 'events-tab') {
        loadActiveEvent();
        loadEventPresence();
        loadPastEvents();
    }
    if (window.lucide) lucide.createIcons();
}

// ─── Live Video Feed & Camera Switcher ────────────────────────

function setVideoSource(source) {
    videoSource = source;
    const btnServer = document.getElementById('btn-source-server');
    const btnBrowser = document.getElementById('btn-source-browser');
    const serverImg = document.getElementById('server-stream');
    const browserVid = document.getElementById('browser-video');
    const browserAnnotated = document.getElementById('browser-annotated');

    if (source === 'server') {
        btnServer.classList.add('active');
        btnBrowser.classList.remove('active');
        serverImg.style.display = 'block';
        browserVid.style.display = 'none';
        browserAnnotated.style.display = 'none';
        stopBrowserCam();
    } else {
        btnBrowser.classList.add('active');
        btnServer.classList.remove('active');
        serverImg.style.display = 'none';
        browserVid.style.display = 'block';
        startBrowserCam();
    }
}

async function startBrowserCam() {
    const video = document.getElementById('browser-video');
    try {
        browserStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
        video.srcObject = browserStream;
        video.play();

        if (browserCamInterval) clearInterval(browserCamInterval);
        browserCamInterval = setInterval(sendBrowserFrameForAnalysis, 800);
        showToast('Webcam do navegador iniciada', 'success');
    } catch (err) {
        showToast('Não foi possível acessar a webcam do navegador: ' + err.message, 'danger');
        setVideoSource('server');
    }
}

function stopBrowserCam() {
    if (browserCamInterval) {
        clearInterval(browserCamInterval);
        browserCamInterval = null;
    }
    if (browserStream) {
        browserStream.getTracks().forEach(track => track.stop());
        browserStream = null;
    }
}

async function sendBrowserFrameForAnalysis() {
    const video = document.getElementById('browser-video');
    const canvas = document.getElementById('browser-canvas');
    if (!video || !canvas || video.readyState !== 4) return;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);

    canvas.toBlob(async (blob) => {
        if (!blob) return;
        const formData = new FormData();
        formData.append('file', blob, 'webcam.jpg');

        try {
            const res = await fetch('/api/v1/local_camera/analyze_frame', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            const hudText = document.getElementById('hud-status-text');
            if (hudText && data && data.faces && data.faces.length > 0) {
                const summary = data.faces.map(f => {
                    const label = f.name || 'Desconhecido';
                    return f.status === 'pending' ? `${label} (?)` : label;
                }).join(', ');
                hudText.innerText = `Detectado: ${summary}`;
            }
        } catch (e) {
            console.error(e);
        }
    }, 'image/jpeg', 0.8);
}

function reloadStream() {
    const img = document.getElementById('server-stream');
    if (img) {
        img.src = '/api/video_feed?t=' + Date.now();
        showToast('Transmissão recarregada', 'info');
    }
}

function toggleFullscreen() {
    const elem = document.getElementById('video-container');
    if (!document.fullscreenElement) {
        elem.requestFullscreen().catch(err => alert(err.message));
    } else {
        document.exitFullscreen();
    }
}

// ─── Stats Polling ────────────────────────────────────────────

async function pollStats() {
    try {
        const res = await fetch('/api/stats');
        const data = await res.json();

        const activeCount = data.active_count || 0;
        document.getElementById('sidebar-active-count').innerText = `${activeCount} Ativos`;
        document.getElementById('header-active-badge').innerText = `${activeCount} presentes agora`;
        document.getElementById('sidebar-fps').innerText = `${data.fps || '0.0'} FPS`;
        document.getElementById('hud-fps-badge').innerText = `FPS: ${data.fps || '0.0'}`;
        document.getElementById('sidebar-camera-status').innerText = data.camera_status || 'Sistema Ativo';
        if (data.database_status) {
            document.getElementById('sidebar-db-text').innerText = data.database_status;
        }

        const chipsContainer = document.getElementById('active-chips-container');
        document.getElementById('active-strip-count').innerText = activeCount;

        if (data.active_people && data.active_people.length > 0) {
            chipsContainer.innerHTML = data.active_people.map(p => `
                <div class="person-chip registered">
                    <i data-lucide="user-check"></i>
                    <a href="#" onclick="openPersonModal(${p.person_id}, '${(p.name || '').replace(/'/g, '')}'); return false;">
                        ${p.display_name}
                    </a>
                    <span class="chip-time">${Math.max(1, Math.round(p.duration_seconds / 60))} min</span>
                </div>
            `).join('');
        } else {
            chipsContainer.innerHTML = '<div class="empty-state-sm">Nenhuma pessoa presente no momento</div>';
        }

        document.getElementById('kpi-total-registered').innerText = data.total_registered || 0;
        document.getElementById('kpi-registered-today').innerText = data.detections_today || 0;
        document.getElementById('kpi-unknown-today').innerText = data.new_registrations_today || 0;
        document.getElementById('kpi-avg-stay').innerText = `${data.avg_stay_minutes || 0} min`;
        document.getElementById('nav-people-count').innerText = data.total_registered || 0;

        if (window.lucide) lucide.createIcons();
    } catch (err) {
        console.warn('Erro ao atualizar estatísticas:', err);
    }
}

// ─── AI Insights ──────────────────────────────────────────────

async function fetchInsights() {
    try {
        const res = await fetch('/api/ai_insights');
        const insights = await res.json();
        const feed = document.getElementById('insights-feed');
        if (!feed || !insights || insights.length === 0) return;

        feed.innerHTML = insights.map(item => `
            <div class="insight-item ${item.type || 'info'}">
                <div class="insight-meta">
                    <span class="insight-time">${item.timestamp}</span>
                    <span class="insight-name">${item.name || ''}</span>
                </div>
                <div class="insight-text">${item.text}</div>
            </div>
        `).join('');
    } catch (e) {
        /* AI agent may be disabled — silently ignore */
    }
}

async function generateAiSummary() {
    const summaryBox = document.getElementById('ai-summary-text');
    summaryBox.innerHTML = '<p class="text-muted"><i data-lucide="loader" class="spin"></i> Gerando análise...</p>';
    if (window.lucide) lucide.createIcons();

    try {
        const res = await fetch('/api/generate_summary', { method: 'POST' });
        const data = await res.json();
        summaryBox.innerHTML = `<div class="ai-generated-report">${(data.summary || 'Sem resposta da IA.').replace(/\n/g, '<br>')}</div>`;
        showToast('Resumo IA gerado com sucesso!', 'success');
    } catch (err) {
        summaryBox.innerHTML = '<p class="text-danger">Erro ao gerar resumo da IA.</p>';
        showToast('Falha na comunicação com Agente IA', 'danger');
    }
}

function generateAiSummaryModal() {
    switchTab('analytics');
    generateAiSummary();
}

// ─── YouTube Processing ───────────────────────────────────────

function startYoutubAnalysis() {
    const url = document.getElementById('yt-url-input').value.trim();
    if (!url) {
        showToast('Por favor, informe a URL do vídeo do YouTube.', 'warning');
        return;
    }

    const interval = parseFloat(document.getElementById('yt-interval').value) || 1.0;
    const minScore = parseFloat(document.getElementById('yt-min-score').value) || 0.40;

    document.getElementById('btn-start-yt').style.display = 'none';
    document.getElementById('btn-stop-yt').style.display = 'block';
    const statusBox = document.getElementById('yt-status-box');
    statusBox.style.display = 'block';
    document.getElementById('yt-status-title').innerText = 'Iniciando download...';
    document.getElementById('yt-progress-fill').style.width = '0%';
    document.getElementById('yt-progress-text').innerText = '0%';

    const facesGrid = document.getElementById('yt-faces-grid');
    facesGrid.innerHTML = '';
    let detectedCount = 0;

    const ytVideoId = extractYoutubeId(url);
    if (ytVideoId) {
        document.getElementById('yt-player-preview').style.display = 'block';
        document.getElementById('yt-iframe').src = `https://www.youtube.com/embed/${ytVideoId}?autoplay=0`;
    }

    fetch('/api/v1/youtube/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, frame_interval: interval, min_det_score: minScore })
    }).then(response => {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        function readStream() {
            reader.read().then(({ done, value }) => {
                if (done) { stopYoutubeAnalysis(); return; }
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            handleYoutubeEvent(JSON.parse(line.substring(6)));
                        } catch (e) { console.error(e); }
                    }
                }
                readStream();
            }).catch(() => stopYoutubeAnalysis());
        }
        readStream();
    }).catch(err => {
        showToast('Erro ao iniciar processamento do vídeo: ' + err.message, 'danger');
        stopYoutubeAnalysis();
    });

    function handleYoutubeEvent(data) {
        if (data.type === 'info') {
            document.getElementById('yt-status-title').innerText = data.message;
        } else if (data.type === 'progress') {
            document.getElementById('yt-status-title').innerText = `Processando frame em ${data.time}s...`;
            document.getElementById('yt-progress-fill').style.width = `${data.progress}%`;
            document.getElementById('yt-progress-text').innerText = `${data.progress}%`;
        } else if (data.type === 'face') {
            detectedCount++;
            document.getElementById('yt-detected-badge').innerText = `${detectedCount} Detectados`;

            const statusBadge = data.status === 'registered'
                ? '<span class="badge badge-new">NOVO CADASTRO</span>'
                : data.status === 'pending'
                    ? '<span class="badge">AGUARDANDO CONFIRMAÇÃO</span>'
                    : '<span class="badge badge-known">IDENTIFICADO</span>';

            const card = document.createElement('div');
            card.className = 'yt-face-card animate-in';
            card.innerHTML = `
                <img src="${data.face_image}" class="yt-face-thumb" alt="Face" />
                <div class="yt-face-info">
                    <div class="yt-face-header">
                        <span class="yt-face-name">${data.name || 'Pessoa #' + data.person_id}</span>
                        ${statusBadge}
                    </div>
                    <div class="yt-face-meta">
                        <span>Tempo: ${data.time}s</span> |
                        <span>Confiança: ${(data.confidence * 100).toFixed(0)}%</span>
                        ${data.status === 'registered' ? `<button class="btn btn-ghost btn-sm" onclick="openNamingPrompt(${data.person_id}, '${(data.name || '').replace(/'/g, '')}')">Nomear</button>` : ''}
                    </div>
                </div>
            `;
            facesGrid.prepend(card);
        } else if (data.type === 'done') {
            document.getElementById('yt-status-title').innerText = data.message;
            document.getElementById('yt-progress-fill').style.width = '100%';
            document.getElementById('yt-progress-text').innerText = '100% Concluído';
            showToast('Processamento do vídeo finalizado!', 'success');
            stopYoutubeAnalysis();
        } else if (data.type === 'error') {
            showToast(data.message, 'danger');
            stopYoutubeAnalysis();
        }
    }
}

function stopYoutubeAnalysis() {
    document.getElementById('btn-start-yt').style.display = 'block';
    document.getElementById('btn-stop-yt').style.display = 'none';
}

function extractYoutubeId(url) {
    const match = url.match(/(?:v=|\/|shorts\/)([0-9A-Za-z_-]{11})/);
    return match ? match[1] : null;
}

// ─── RTSP Streams ─────────────────────────────────────────────

async function loadRTSPStreams() {
    try {
        const res = await fetch('/api/v1/streams');
        const streams = await res.json();
        const list = document.getElementById('rtsp-streams-list');

        if (!streams || streams.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <i data-lucide="cctv"></i>
                    <p>Nenhuma câmera RTSP cadastrada ainda.</p>
                </div>
            `;
        } else {
            list.innerHTML = streams.map(s => `
                <div class="rtsp-card">
                    <div class="rtsp-card-body">
                        <div class="rtsp-header">
                            <span class="rtsp-name">${s.name}</span>
                            <span class="badge ${s.is_active ? 'badge-active' : 'badge-inactive'}">
                                ${s.is_active ? '● Ativa' : '○ Inativa'}
                            </span>
                        </div>
                        <div class="rtsp-url">${s.url}</div>
                    </div>
                    <div class="rtsp-actions">
                        ${s.is_active ? `
                            <button class="btn btn-warning btn-sm" onclick="stopRTSP(${s.id})">
                                <i data-lucide="pause"></i> Parar
                            </button>
                        ` : `
                            <button class="btn btn-primary btn-sm" onclick="startRTSP(${s.id})">
                                <i data-lucide="play"></i> Iniciar
                            </button>
                        `}
                        <button class="btn btn-danger btn-sm" onclick="deleteRTSP(${s.id})">
                            <i data-lucide="trash-2"></i> Excluir
                        </button>
                    </div>
                </div>
            `).join('');
        }
        if (window.lucide) lucide.createIcons();
    } catch (err) {
        console.error('Erro ao carregar streams RTSP:', err);
    }
}

async function handleAddRTSP(e) {
    e.preventDefault();
    const name = document.getElementById('rtsp-name').value.trim();
    const url = document.getElementById('rtsp-url').value.trim();

    try {
        const res = await fetch('/api/v1/streams', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, url })
        });
        if (res.ok) {
            showToast('Câmera RTSP cadastrada com sucesso!', 'success');
            document.getElementById('form-add-rtsp').reset();
            loadRTSPStreams();
        } else {
            const err = await res.json();
            showToast(err.detail || 'Erro ao cadastrar câmera', 'danger');
        }
    } catch (err) {
        showToast('Erro de conexão: ' + err.message, 'danger');
    }
}

async function startRTSP(id) {
    try {
        const res = await fetch(`/api/v1/streams/${id}/start`, { method: 'POST' });
        const data = await res.json();
        showToast(data.detail, 'info');
        loadRTSPStreams();
    } catch (e) {
        showToast('Erro ao iniciar RTSP: ' + e.message, 'danger');
    }
}

async function stopRTSP(id) {
    try {
        const res = await fetch(`/api/v1/streams/${id}/stop`, { method: 'POST' });
        const data = await res.json();
        showToast(data.detail, 'info');
        loadRTSPStreams();
    } catch (e) {
        showToast('Erro ao parar RTSP: ' + e.message, 'danger');
    }
}

async function deleteRTSP(id) {
    if (!confirm('Deseja realmente excluir esta câmera RTSP?')) return;
    try {
        const res = await fetch(`/api/v1/streams/${id}`, { method: 'DELETE' });
        if (res.ok) {
            showToast('Câmera excluída com sucesso', 'success');
            loadRTSPStreams();
        }
    } catch (e) {
        showToast('Erro ao excluir RTSP: ' + e.message, 'danger');
    }
}

// ─── Register Face ────────────────────────────────────────────

let registerCapturedBase64 = null;

function quickSnapshotFromStream() {
    switchTab('register');
    captureSnapshotForRegister();
}

function captureSnapshotForRegister() {
    const video = document.getElementById('browser-video');
    const canvas = document.createElement('canvas');

    if (videoSource === 'browser' && browserStream) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext('2d').drawImage(video, 0, 0);
        registerCapturedBase64 = canvas.toDataURL('image/jpeg', 0.95);
        showRegisterPreview(registerCapturedBase64);
    } else {
        const img = document.getElementById('server-stream');
        if (img && img.naturalWidth) {
            canvas.width = img.naturalWidth;
            canvas.height = img.naturalHeight;
            canvas.getContext('2d').drawImage(img, 0, 0);
            registerCapturedBase64 = canvas.toDataURL('image/jpeg', 0.95);
            showRegisterPreview(registerCapturedBase64);
        } else {
            showToast('Nenhum frame disponível da transmissão ainda.', 'warning');
        }
    }
}

function handleRegisterFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        registerCapturedBase64 = e.target.result;
        showRegisterPreview(registerCapturedBase64);
    };
    reader.readAsDataURL(file);
}

function showRegisterPreview(dataUrl) {
    const preview = document.getElementById('register-preview-img');
    const placeholder = document.getElementById('register-placeholder');
    preview.src = dataUrl;
    preview.style.display = 'block';
    placeholder.style.display = 'none';
    showToast('Foto capturada! Preencha o nome para cadastrar.', 'info');
}

async function submitRegisterFace() {
    const name = document.getElementById('register-name').value.trim();
    if (!name) {
        showToast('Por favor, informe o nome completo da pessoa.', 'warning');
        return;
    }
    if (!registerCapturedBase64) {
        showToast('Capture uma foto ou faça upload de uma imagem primeiro.', 'warning');
        return;
    }

    const btn = document.getElementById('btn-save-register');
    btn.disabled = true;
    btn.innerHTML = '<i data-lucide="loader" class="spin"></i> Cadastrando...';

    try {
        const res = await fetch('/api/v1/persons/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, image_base64: registerCapturedBase64 })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(`${name} cadastrado(a) com sucesso!`, 'success');
            document.getElementById('register-name').value = '';
            registerCapturedBase64 = null;
            document.getElementById('register-preview-img').style.display = 'none';
            document.getElementById('register-placeholder').style.display = 'flex';
            loadPeople();
            switchTab('people');
        } else {
            showToast(data.detail || 'Não foi possível detectar um rosto na foto.', 'danger');
        }
    } catch (err) {
        showToast('Erro ao cadastrar: ' + err.message, 'danger');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i data-lucide="check"></i> <span>Concluir Cadastro</span>';
        if (window.lucide) lucide.createIcons();
    }
}

// ─── Manage People ────────────────────────────────────────────

async function loadPeople() {
    try {
        const res = await fetch('/api/v1/persons?limit=200');
        allPeopleCache = await res.json();
        renderPeopleGrid(allPeopleCache);
    } catch (err) {
        console.error('Erro ao listar pessoas:', err);
    }
}

function renderPeopleGrid(people) {
    const grid = document.getElementById('people-cards-grid');
    if (!people || people.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <i data-lucide="users"></i>
                <p>Nenhuma pessoa registrada ainda.</p>
                <button class="btn btn-primary btn-sm" onclick="switchTab('register')">Cadastrar Agora</button>
            </div>
        `;
        return;
    }

    grid.innerHTML = people.map(p => {
        const photoUrl = p.image_url || `/api/v1/persons/${p.id}/image`;
        const displayName = p.display_name || `Pessoa #${p.id}`;
        const isUnnamed = !p.name;
        const firstSeen = p.first_seen_at ? new Date(p.first_seen_at).toLocaleDateString('pt-BR') : '';
        const lastSeen = p.last_seen_at ? new Date(p.last_seen_at).toLocaleString('pt-BR') : '';
        return `
            <div class="person-card">
                <img src="${photoUrl}" class="person-avatar" alt="${displayName}" onerror="this.src='/static/avatar.svg'" />
                <div class="person-info">
                    <span class="person-name">${displayName}
                        ${isUnnamed ? '<span class="badge badge-new">SEM NOME</span>' : ''}
                    </span>
                    <span class="person-meta">${p.sighting_count || 0} avistamentos · desde ${firstSeen}</span>
                    <span class="person-meta">Visto por último: ${lastSeen}</span>
                </div>
                <div class="person-card-actions">
                    <button class="btn-icon" title="Mesclar com outro perfil" onclick="openMergeModal(${p.id})">
                        <i data-lucide="git-merge"></i>
                    </button>
                    <button class="btn-icon" title="Nomear/Renomear" onclick="openNamingPrompt(${p.id}, '${displayName.replace(/'/g, '')}')">
                        <i data-lucide="pencil"></i>
                    </button>
                    <button class="btn-icon" title="Ver Histórico" onclick="openPersonModal(${p.id}, '${displayName.replace(/'/g, '')}')">
                        <i data-lucide="history"></i>
                    </button>
                    <button class="btn-icon danger" title="Excluir Perfil" onclick="deletePerson(${p.id}, '${displayName.replace(/'/g, '')}')">
                        <i data-lucide="trash-2"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
    if (window.lucide) lucide.createIcons();
}

function filterPeopleList(query) {
    const q = query.toLowerCase().trim();
    if (!q) {
        renderPeopleGrid(allPeopleCache);
        return;
    }
    const filtered = allPeopleCache.filter(p =>
        (p.name || `pessoa #${p.id}`).toLowerCase().includes(q)
    );
    renderPeopleGrid(filtered);
}

async function deletePerson(id, name) {
    if (!confirm(`Deseja realmente excluir '${name}' e todos os seus registros?`)) return;

    try {
        const res = await fetch(`/api/v1/persons/${id}`, { method: 'DELETE' });
        if (res.ok) {
            showToast('Pessoa excluída com sucesso.', 'success');
            loadPeople();
        }
    } catch (e) {
        showToast('Erro ao excluir: ' + e.message, 'danger');
    }
}

async function openPersonModal(id, name) {
    const modal = document.getElementById('person-modal');
    document.getElementById('modal-person-name').innerText = `Histórico de ${name}`;
    const list = document.getElementById('modal-person-logs-list');
    list.innerHTML = 'Carregando histórico...';
    modal.style.display = 'flex';

    try {
        const res = await fetch(`/api/v1/persons/${id}/logs`);
        const logs = await res.json();
        if (!logs || logs.length === 0) {
            list.innerHTML = '<div class="empty-state-sm">Nenhum registro encontrado.</div>';
        } else {
            list.innerHTML = logs.map(lg => `
                <div class="log-item-row">
                    <span class="log-time">${new Date(lg.detected_at).toLocaleString('pt-BR')}</span>
                    <span class="log-source badge">${lg.source || 'câmera'}</span>
                    <span class="log-conf">Confiança: ${(lg.confidence * 100).toFixed(0)}%</span>
                    ${lg.image_url ? `<img src="${lg.image_url}" class="log-thumb" />` : ''}
                </div>
            `).join('');
        }
    } catch (err) {
        list.innerHTML = '<div class="text-danger">Erro ao carregar histórico.</div>';
    }
}

function closePersonModal() {
    document.getElementById('person-modal').style.display = 'none';
}

// ─── Detection Logs Table ─────────────────────────────────────

async function loadLogsTable() {
    try {
        const res = await fetch('/api/logs?limit=150');
        allLogsCache = await res.json();
        renderLogsTable(allLogsCache);
    } catch (err) {
        console.error('Erro ao ler logs:', err);
    }
}

function renderLogsTable(logs) {
    const tbody = document.getElementById('logs-tbody');
    if (!logs || logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">Nenhuma detecção registrada.</td></tr>';
        return;
    }

    tbody.innerHTML = logs.map(lg => {
        const when = lg.detected_at ? new Date(lg.detected_at).toLocaleString('pt-BR') : '';
        const badge = lg.is_new_registration
            ? '<span class="badge badge-new">NOVO REGISTRO</span>'
            : '<span class="badge badge-known">RECONHECIDO</span>';
        return `
            <tr>
                <td>${when}</td>
                <td><img src="${lg.image_url || '/static/avatar.svg'}" class="log-thumb" onerror="this.style.display='none'" /></td>
                <td class="font-medium">${lg.person_name || ''}</td>
                <td>${badge}</td>
                <td>${lg.source || ''} · ${(lg.confidence * 100).toFixed(0)}%</td>
            </tr>
        `;
    }).join('');
}

function filterLogsTable() {
    const eventType = document.getElementById('log-filter-status').value;
    if (eventType === 'ALL') {
        renderLogsTable(allLogsCache);
        return;
    }
    renderLogsTable(allLogsCache.filter(l =>
        eventType === 'registered' ? l.is_new_registration : !l.is_new_registration
    ));
}

// ─── Settings ─────────────────────────────────────────────────

async function loadRuntimeSettings() {
    try {
        const res = await fetch('/api/v1/settings');
        if (!res.ok) return;
        const data = await res.json();

        document.getElementById('setting-threshold').value = data.similarity_threshold;
        document.getElementById('threshold-val').innerText = data.similarity_threshold;
        document.getElementById('setting-cooldown').value = data.cooldown_minutes;
        document.getElementById('setting-retention').value = data.image_retention_hours;
        document.getElementById('setting-min-sightings').value = data.min_sightings;
        document.getElementById('setting-presence-timeout').value = data.presence_timeout_seconds;
        document.getElementById('setting-auto-register').checked = data.auto_register_enabled;

        const webhookEl = document.getElementById('setting-webhook-url');
        if (webhookEl) webhookEl.value = data.webhook_url || '';

        const audioEl = document.getElementById('setting-audio-alerts');
        if (audioEl) {
            audioEl.checked = data.audio_alerts_enabled !== false;
            audioAlertsEnabled = audioEl.checked;
            const icon = document.getElementById('audio-toggle-icon');
            if (icon) {
                icon.setAttribute('data-lucide', audioAlertsEnabled ? 'volume-2' : 'volume-x');
                if (window.lucide) lucide.createIcons();
            }
        }
    } catch (e) {
        console.warn('Erro ao carregar settings:', e);
    }
}

async function saveRuntimeSettings() {
    const webhookVal = document.getElementById('setting-webhook-url') ? document.getElementById('setting-webhook-url').value.trim() : null;
    const audioVal = document.getElementById('setting-audio-alerts') ? document.getElementById('setting-audio-alerts').checked : true;

    const payload = {
        similarity_threshold: parseFloat(document.getElementById('setting-threshold').value),
        cooldown_minutes: parseInt(document.getElementById('setting-cooldown').value),
        image_retention_hours: parseInt(document.getElementById('setting-retention').value),
        min_sightings: parseInt(document.getElementById('setting-min-sightings').value),
        presence_timeout_seconds: parseInt(document.getElementById('setting-presence-timeout').value),
        auto_register_enabled: document.getElementById('setting-auto-register').checked,
        webhook_url: webhookVal || null,
        audio_alerts_enabled: audioVal
    };

    try {
        const res = await fetch('/api/v1/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            audioAlertsEnabled = audioVal;
            showToast('Parâmetros salvos com sucesso!', 'success');
        } else {
            const err = await res.json();
            showToast(err.detail?.[0]?.msg || 'Parâmetros inválidos.', 'danger');
        }
    } catch (e) {
        showToast('Erro ao salvar parâmetros: ' + e.message, 'danger');
    }
}

async function saveCameraSettings() {
    const cameraIdx = parseInt(document.getElementById('setting-camera-index').value);
    const useA9 = document.getElementById('setting-use-a9').checked;

    try {
        const res = await fetch('/api/camera_config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                camera_index: cameraIdx,
                use_a9: useA9
            })
        });
        const data = await res.json();
        showToast(`Câmera configurada: ${data.status}`, 'success');
        reloadStream();
    } catch (err) {
        showToast('Erro ao atualizar câmera: ' + err.message, 'danger');
    }
}

// ─── Events & Presence ────────────────────────────────────────

async function handleCreateEvent(e) {
    e.preventDefault();
    const name = document.getElementById('event-name').value.trim();
    const duration = parseInt(document.getElementById('event-duration').value, 10);

    if (!name) {
        showToast('Informe o nome do evento.', 'warning');
        return;
    }

    try {
        const res = await fetch('/api/v1/events', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, duration_minutes: duration })
        });
        if (res.ok) {
            showToast('Evento iniciado com sucesso!', 'success');
            document.getElementById('form-create-event').reset();
            document.getElementById('event-duration-val').innerText = '60 min';
            loadActiveEvent();
            loadEventPresence();
            loadPastEvents();
        } else {
            const err = await res.json();
            showToast(err.detail || 'Erro ao criar evento.', 'danger');
        }
    } catch (err) {
        showToast('Erro ao criar evento: ' + err.message, 'danger');
    }
}

async function loadActiveEvent() {
    try {
        const res = await fetch('/api/v1/events/active');
        const event = await res.json();
        const nameEl = document.getElementById('active-event-name');
        const metaEl = document.getElementById('active-event-meta');
        const btnEnd = document.getElementById('btn-end-event');

        if (!event) {
            nameEl.innerText = 'Nenhum evento ativo';
            metaEl.innerText = '';
            btnEnd.style.display = 'none';
            return;
        }

        nameEl.innerText = event.name;
        const started = new Date(event.started_at).toLocaleString('pt-BR');
        metaEl.innerText = `Iniciado em: ${started}`;
        btnEnd.style.display = 'block';
        btnEnd.onclick = () => endActiveEvent(event.id);
    } catch (err) {
        console.error('Erro ao carregar evento ativo:', err);
    }
}

async function endActiveEvent(eventId) {
    try {
        const id = eventId || document.getElementById('btn-end-event').getAttribute('data-event-id');
        if (!id) {
            showToast('Nenhum evento ativo para encerrar.', 'warning');
            return;
        }
        const res = await fetch(`/api/v1/events/${id}/end`, { method: 'POST' });
        if (res.ok) {
            showToast('Evento encerrado.', 'success');
            loadActiveEvent();
            loadPastEvents();
        } else {
            const err = await res.json();
            showToast(err.detail || 'Erro ao encerrar evento.', 'danger');
        }
    } catch (err) {
        showToast('Erro ao encerrar evento: ' + err.message, 'danger');
    }
}

async function loadEventPresence() {
    try {
        const res = await fetch('/api/v1/events/active');
        const event = await res.json();
        const tbody = document.getElementById('presence-tbody');
        const subtitle = document.getElementById('presence-subtitle');

        if (!event) {
            if (subtitle) subtitle.innerText = '';
            tbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">Nenhum evento ativo.</td></tr>';
            return;
        }

        if (subtitle) subtitle.innerText = `Evento: ${event.name}`;

        const presRes = await fetch(`/api/v1/events/${event.id}/presence`);
        const presences = await presRes.json();
        if (!presences || presences.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">Nenhuma presença registrada ainda.</td></tr>';
            return;
        }

        tbody.innerHTML = presences.map(p => `
            <tr>
                <td class="presence-photo-cell">
                    <img src="${p.face_image_url || '/static/avatar.svg'}" class="presence-avatar" onerror="this.onerror=null;this.src='/static/avatar.svg'" />
                </td>
                <td class="font-medium">${p.display_name}</td>
                <td class="text-muted">${new Date(p.first_seen_at).toLocaleString('pt-BR')}</td>
            </tr>
        `).join('');
    } catch (err) {
        console.error('Erro ao carregar presença:', err);
    }
}

async function loadPastEvents() {
    try {
        const res = await fetch('/api/v1/events?limit=20');
        const events = await res.json();
        const container = document.getElementById('past-events-list');

        if (!events || events.length === 0) {
            container.innerHTML = '<div class="empty-state-sm">Nenhum evento anterior.</div>';
            return;
        }

        container.innerHTML = events.map(e => {
            const started = new Date(e.started_at).toLocaleString('pt-BR');
            const ended = e.ended_at ? new Date(e.ended_at).toLocaleString('pt-BR') : 'Em andamento';
            const statusBadge = e.is_active
                ? '<span class="badge badge-active">● Ativo</span>'
                : '<span class="badge badge-inactive">○ Encerrado</span>';
            return `
                <div class="event-card">
                    <div class="event-card-body">
                        <div class="event-card-title-row">
                            <span class="event-name">${e.name}</span>
                            ${statusBadge}
                        </div>
                        <span class="event-meta">Início: ${started}</span>
                        <span class="event-meta">Fim: ${ended}</span>
                    </div>
                    <div class="event-actions">
                        <button class="btn btn-ghost btn-sm" onclick="viewEventPresence(${e.id}, '${(e.name || '').replace(/'/g, '')}')">
                            <i data-lucide="eye"></i> Ver Presença
                        </button>
                    </div>
                </div>
            `;
        }).join('');
        if (window.lucide) lucide.createIcons();
    } catch (err) {
        console.error('Erro ao carregar eventos:', err);
    }
}

async function viewEventPresence(eventId, eventName) {
    try {
        const res = await fetch(`/api/v1/events/${eventId}/presence`);
        const presences = await res.json();
        const tbody = document.getElementById('presence-tbody');
        const subtitle = document.getElementById('presence-subtitle');

        if (subtitle && eventName) subtitle.innerText = `Evento: ${eventName}`;

        if (!presences || presences.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">Nenhuma presença neste evento.</td></tr>';
            return;
        }
        tbody.innerHTML = presences.map(p => `
            <tr>
                <td class="presence-photo-cell">
                    <img src="${p.face_image_url || '/static/avatar.svg'}" class="presence-avatar" onerror="this.onerror=null;this.src='/static/avatar.svg'" />
                </td>
                <td class="font-medium">${p.display_name}</td>
                <td class="text-muted">${new Date(p.first_seen_at).toLocaleString('pt-BR')}</td>
            </tr>
        `).join('');
        switchTab('events-tab');
    } catch (err) {
        showToast('Erro ao carregar presença do evento.', 'danger');
    }
}

// ─── CSV Export Actions ──────────────────────────────────────

function exportLogsCSV() {
    window.open('/api/logs/export.csv', '_blank');
}

function exportPresenceCSV() {
    window.open('/api/presence/export.csv', '_blank');
}

async function exportCurrentEventCSV() {
    try {
        const res = await fetch('/api/v1/events/active');
        const active = await res.json();
        if (active && active.id) {
            window.open(`/api/v1/events/${active.id}/export.csv`, '_blank');
        } else {
            showToast('Nenhum evento ativo no momento para exportar.', 'warning');
        }
    } catch (e) {
        showToast('Erro ao exportar evento: ' + e.message, 'danger');
    }
}

// ─── Merge Persons Modal & Execution ─────────────────────────

function openMergeModal(defaultSourceId = null) {
    const modal = document.getElementById('merge-modal');
    const selectSrc = document.getElementById('merge-source-select');
    const selectTgt = document.getElementById('merge-target-select');
    if (!modal || !selectSrc || !selectTgt) return;

    if (!allPeopleCache || allPeopleCache.length < 2) {
        showToast('É necessário ter ao menos 2 pessoas cadastradas para realizar a mesclagem.', 'warning');
        return;
    }

    const options = allPeopleCache.map(p => `
        <option value="${p.id}">${p.display_name} (ID #${p.id} · ${p.sighting_count || 1} avistamentos)</option>
    `).join('');

    selectSrc.innerHTML = options;
    selectTgt.innerHTML = options;

    if (defaultSourceId) {
        selectSrc.value = defaultSourceId;
        const other = allPeopleCache.find(p => p.id !== defaultSourceId);
        if (other) selectTgt.value = other.id;
    } else {
        if (allPeopleCache.length > 1) {
            selectTgt.selectedIndex = 1;
        }
    }

    modal.style.display = 'flex';
}

function closeMergeModal() {
    const modal = document.getElementById('merge-modal');
    if (modal) modal.style.display = 'none';
}

async function executeMergePersons() {
    const srcId = parseInt(document.getElementById('merge-source-select').value);
    const tgtId = parseInt(document.getElementById('merge-target-select').value);

    if (srcId === tgtId) {
        showToast('Selecione perfis de origem e destino diferentes.', 'warning');
        return;
    }

    if (!confirm(`Tem certeza que deseja mesclar o perfil #${srcId} no perfil #${tgtId}? Esta ação unificará o histórico e removerá o perfil #${srcId}.`)) {
        return;
    }

    try {
        const res = await fetch(`/api/v1/persons/${srcId}/merge/${tgtId}`, {
            method: 'POST',
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message || 'Perfis mesclados com sucesso!', 'success');
            closeMergeModal();
            loadPeople();
            loadLogsTable();
        } else {
            showToast(data.detail || 'Erro ao mesclar perfis.', 'danger');
        }
    } catch (e) {
        showToast('Erro de conexão ao mesclar: ' + e.message, 'danger');
    }
}

// ─── Analytics Timeline Chart (Canvas 2D) ────────────────────

async function loadAnalyticsTimeline() {
    const canvas = document.getElementById('hourly-traffic-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    try {
        const res = await fetch('/api/analytics/timeline');
        if (!res.ok) return;
        const data = await res.json();
        const timeline = data.timeline || [];

        const rect = canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        const width = rect.width || 600;
        const height = 160;
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        ctx.scale(dpr, dpr);

        ctx.clearRect(0, 0, width, height);

        if (timeline.length === 0) {
            ctx.fillStyle = '#94a3b8';
            ctx.font = '13px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('Nenhum dado registrado nas últimas 24 horas.', width / 2, height / 2);
            return;
        }

        const maxVal = Math.max(5, ...timeline.map(t => t.detections));
        const padding = { top: 20, bottom: 28, left: 36, right: 16 };
        const chartW = width - padding.left - padding.right;
        const chartH = height - padding.top - padding.bottom;

        // Grid lines
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
        ctx.lineWidth = 1;
        ctx.fillStyle = '#64748b';
        ctx.font = '10px JetBrains Mono, monospace';
        ctx.textAlign = 'right';

        for (let i = 0; i <= 3; i++) {
            const yVal = Math.round((maxVal / 3) * i);
            const yPos = padding.top + chartH - (i / 3) * chartH;
            ctx.beginPath();
            ctx.moveTo(padding.left, yPos);
            ctx.lineTo(width - padding.right, yPos);
            ctx.stroke();
            ctx.fillText(yVal.toString(), padding.left - 8, yPos + 3);
        }

        // Draw bars
        const step = chartW / timeline.length;
        const barWidth = Math.max(4, step * 0.65);

        timeline.forEach((item, i) => {
            const x = padding.left + i * step + (step - barWidth) / 2;
            const barH = (item.detections / maxVal) * chartH;
            const y = padding.top + chartH - barH;

            // Gradient fill
            const grad = ctx.createLinearGradient(0, y, 0, y + barH);
            grad.addColorStop(0, '#38bdf8');
            grad.addColorStop(1, 'rgba(56, 189, 248, 0.15)');

            ctx.fillStyle = grad;
            ctx.beginPath();
            if (ctx.roundRect) {
                ctx.roundRect(x, y, barWidth, barH, [3, 3, 0, 0]);
            } else {
                ctx.rect(x, y, barWidth, barH);
            }
            ctx.fill();

            // Highlight new registrations in green
            if (item.new_registrations > 0) {
                const newBarH = (item.new_registrations / maxVal) * chartH;
                const newY = padding.top + chartH - newBarH;
                ctx.fillStyle = '#10b981';
                ctx.beginPath();
                if (ctx.roundRect) {
                    ctx.roundRect(x, newY, barWidth, newBarH, [3, 3, 0, 0]);
                } else {
                    ctx.rect(x, newY, barWidth, newBarH);
                }
                ctx.fill();
            }

            // Labels
            if (i % 3 === 0) {
                ctx.fillStyle = '#94a3b8';
                ctx.font = '10px JetBrains Mono, monospace';
                ctx.textAlign = 'center';
                ctx.fillText(item.hour, x + barWidth / 2, height - 8);
            }
        });
    } catch (e) {
        console.error('Erro ao renderizar gráfico timeline:', e);
    }
}

