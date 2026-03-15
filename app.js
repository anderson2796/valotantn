const API_KEY = 'f100b7fc-52cf-4347-b8c2-87a4a6078baf';
const BASE_URL = '/api';

// App State
let authToken = localStorage.getItem('val_auth_token') || null;
let currentUser = null;
let accounts = [];
let activeAccountPuuid = null;
let currentTab = 'dashboard';
let cachedMMR = null;
let manualMatches = [];
let aggregateCache = null;

// DOM Elements
const searchInput = document.getElementById('account-search');
const addAccountBtn = document.getElementById('add-account-btn');
const navLinks = document.querySelectorAll('.nav-links li');
const tabContents = document.querySelectorAll('.tab-content');
const seasonFilter = document.getElementById('season-filter');
const loader = document.getElementById('loader');

// Auth DOM Elements
const authModal = document.getElementById('auth-modal');
const authForm = document.getElementById('auth-form');
const authEmail = document.getElementById('auth-email');
const authPassword = document.getElementById('auth-password');
const authTitle = document.getElementById('auth-title');
const authToggleBtn = document.getElementById('auth-toggle-btn');
const authToggleText = document.getElementById('auth-toggle-text');
const authError = document.getElementById('auth-error');
const logoutBtn = document.getElementById('logout-btn');

let isLoginMode = true;

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    initApp();
});

async function initApp() {
    if (!authToken) {
        showAuthModal(true);
        return;
    }

    showAuthModal(false);
    logoutBtn.classList.remove('hidden');

    try {
        await fetchUserData();

        renderManagedAccounts();

        if (accounts.length > 0) {
            await loadAllAccountsData();
            await selectAccount(accounts[0].puuid);
        } else {
            showTab('accounts');
        }
        setupAutoRefresh();
    } catch (err) {
        console.error('Initialization Error:', err);
        showAuthModal(true);
        handleLogout();
    }
}

async function fetchUserData() {
    showLoader(true, 'Cargando tus datos...');
    try {
        const data = await apiFetch('/user/data');
        accounts = data.accounts || [];
        manualMatches = data.manual_matches || [];
    } catch (err) {
        throw err;
    } finally {
        showLoader(false);
    }
}

async function loadAllAccountsData() {
    // Pre-load aggregate stats for all accounts
    if (accounts.length > 0) {
        await renderAggregateStats();
    }
}

function setupAutoRefresh() {
    // Refresh data every 30 minutes (1800000 ms)
    autoRefreshInterval = setInterval(async () => {
        console.log('Auto-refreshing stats...');
        if (accounts.length > 0) {
            await loadAllAccountsData();
            if (activeAccountPuuid) {
                await selectAccount(activeAccountPuuid);
            }
        }
    }, 1800000); // 30 minutes
}

function setupEventListeners() {
    // Auth Events
    authToggleBtn.addEventListener('click', (e) => {
        e.preventDefault();
        isLoginMode = !isLoginMode;
        authTitle.innerText = isLoginMode ? 'Iniciar Sesión' : 'Registrarse';
        authSubmitBtn.innerText = isLoginMode ? 'Entrar' : 'Registrarse';
        authToggleText.innerHTML = isLoginMode
            ? '¿No tienes cuenta? <a href="#" id="auth-toggle-btn">Regístrate</a>'
            : '¿Ya tienes cuenta? <a href="#" id="auth-toggle-btn">Inicia Sesión</a>';

        authError.classList.add('hidden');

        // Re-attach toggle listener since we replaced innerHTML
        document.getElementById('auth-toggle-btn').addEventListener('click', arguments.callee);
    });

    authForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = authEmail.value;
        const password = authPassword.value;

        authError.classList.add('hidden');
        showLoader(true, isLoginMode ? 'Iniciando sesión...' : 'Registrando...');

        try {
            const endpoint = isLoginMode ? '/login' : '/register';
            const res = await fetch(`${BASE_URL}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            const data = await res.json();

            if (!res.ok) throw new Error(data.error || 'Error de autenticación');

            if (isLoginMode) {
                authToken = data.token;
                localStorage.setItem('val_auth_token', authToken);
                initApp();
            } else {
                // Si se registró, pasar a login
                isLoginMode = true;
                authToggleBtn.click();
                authError.innerText = 'Registro exitoso. Inicia sesión.';
                authError.classList.remove('hidden');
                authError.style.color = '#4ade80';
                authError.style.backgroundColor = 'rgba(74, 222, 128, 0.1)';
            }
        } catch (err) {
            authError.innerText = err.message;
            authError.classList.remove('hidden');
            authError.style.color = '#ff4e4e';
            authError.style.backgroundColor = 'rgba(255, 78, 78, 0.1)';
        } finally {
            showLoader(false);
        }
    });

    logoutBtn.addEventListener('click', handleLogout);

    addAccountBtn.addEventListener('click', () => {
        const query = searchInput.value.trim();
        if (query.includes('#')) {
            const [name, tag] = query.split('#');
            addAccount(name, tag);
        } else {
            alert('Por favor usa el formato Nombre#TAG');
        }
    });

    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') addAccountBtn.click();
    });

    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            const tabId = link.getAttribute('data-tab');
            showTab(tabId);
        });
    });

    seasonFilter.addEventListener('change', () => {
        if (cachedMMR && activeAccountPuuid) {
            const acc = accounts.find(a => a.puuid === activeAccountPuuid);
            updateDashboard(acc, cachedMMR, null, true); // Partial update
        }
    });

    // Manual match form submission
    const manualForm = document.getElementById('manual-match-form');
    if (manualForm) {
        manualForm.addEventListener('submit', (e) => {
            e.preventDefault();
            addManualMatch();
        });
    }
}

function handleLogout() {
    authToken = null;
    localStorage.removeItem('val_auth_token');
    accounts = [];
    manualMatches = [];
    aggregateCache = null;
    showAuthModal(true);
    logoutBtn.classList.add('hidden');
}

function showAuthModal(show) {
    if (show) {
        authModal.classList.remove('hidden');
    } else {
        authModal.classList.add('hidden');
    }
}

function showTab(tabId) {
    currentTab = tabId;
    navLinks.forEach(l => l.classList.remove('active'));
    document.querySelector(`[data-tab="${tabId}"]`).classList.add('active');

    tabContents.forEach(content => {
        content.classList.remove('active');
        if (content.id === `${tabId}-tab`) {
            content.classList.add('active');
        }
    });

    if (tabId === 'aggregate') {
        // Only render if needed or if data is missing
        if (!aggregateCache) {
            renderAggregateStats();
        } else {
            updateAggregateUI(aggregateCache);
        }
    }
    if (tabId === 'provisional') renderManualMatches();
}

// API Calls
async function apiFetch(endpoint, options = {}) {
    try {
        const url = `${BASE_URL}${endpoint}`;
        console.log(`Fetching: ${url}`);

        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };

        if (authToken) {
            headers['Authorization'] = `Bearer ${authToken}`;
        }

        const response = await fetch(url, { ...options, headers });

        if (!response.ok) {
            if (response.status === 401) {
                handleLogout(); // Auth expired
                throw new Error("Sesión expirada");
            }
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.error || `HTTP Error ${response.status}`);
        }

        const data = await response.json();
        return data;
    } catch (err) {
        console.error('Fetch Error:', err);
        throw err;
    }
}


async function addAccount(name, tag) {
    showLoader(true, `Buscando a ${name}#${tag}...`);
    try {
        const accountData = await apiFetch(`/v1/account/${encodeURIComponent(name)}/${encodeURIComponent(tag)}`);

        // Check if already exists
        if (accounts.find(a => a.puuid === accountData.puuid)) {
            alert('Esta cuenta ya ha sido agregada.');
            showLoader(false);
            return;
        }

        // Save to backend
        await apiFetch('/user/accounts', {
            method: 'POST',
            body: JSON.stringify({
                name: accountData.name,
                tag: accountData.tag,
                puuid: accountData.puuid,
                account_level: accountData.account_level,
                region: accountData.region || 'latam',
                card: accountData.card
            })
        });

        accounts.push(accountData);
        aggregateCache = null; // Invalidate cache to force refresh in aggregate tab
        renderManagedAccounts();
        await selectAccount(accountData.puuid);
        searchInput.value = '';
    } catch (err) {
        alert(err.message || 'No se pudo encontrar o guardar la cuenta.');
    } finally {
        showLoader(false);
    }
}

async function selectAccount(puuid) {
    const account = accounts.find(a => a.puuid === puuid);
    if (!account) return;

    activeAccountPuuid = puuid;
    renderManagedAccounts(); // Highlight active
    showLoader(true, `Cargando estadísticas de carrera de ${account.name}...`);

    try {
        // Call Flask backend for complete career stats
        const profileData = await apiFetch(`/profile/${encodeURIComponent(account.name)}/${encodeURIComponent(account.tag)}`);

        // Store profile data in account
        account.careerStats = profileData.stats;
        account.rank = profileData.rank;
        account.agents = profileData.agents;

        updateDashboard(account, profileData);
        showTab('dashboard');
    } catch (err) {
        console.error(err);
        alert('Error al cargar las estadísticas. Asegúrate de que el backend esté corriendo.');
    } finally {
        showLoader(false);
    }
}

function updateDashboard(account, profileData) {
    console.log(">>> DASHBOARD UPDATE:", { account, profileData });
    const stats = profileData.stats;

    // Rank display
    const rankDisplay = profileData.rank || 'Unrated';
    const tierId = profileData.tier_id || 0;
    let rankImg = `https://media.valorant-api.com/competitivetiers/03621f52-342b-cf4e-4f86-9350a49c6d04/${tierId}/largeicon.png`;
    if (tierId === 0) rankImg = "https://media.valorant-api.com/playercards/9fb34440-4f0b-49dc-3cb7-578f797d1000/displayicon.png";

    document.getElementById('main-rank-img').src = rankImg;
    document.getElementById('rank-name').innerText = rankDisplay;
    document.getElementById('main-username').innerText = `${account.name}#${account.tag}`;
    document.getElementById('main-level').innerText = `Nivel ${account.account_level || 0}`;

    // Update Sidebar Profile Section Sync
    const sidebarAvatar = document.getElementById('sidebar-avatar');
    const sidebarUser = document.getElementById('sidebar-username');
    const sidebarLevel = document.getElementById('sidebar-level');
    
    if (sidebarAvatar) sidebarAvatar.src = account.card || "https://wallpapers.com/images/hd/valorant-jett-profile-picture-t8z4x3x3x3x3x3x3.jpg";
    if (sidebarUser) sidebarUser.innerText = `${account.name}#${account.tag}`;
    if (sidebarLevel) sidebarLevel.innerText = `Level ${account.account_level || 0}`;

    // Display career stats from Tracker.gg
    document.getElementById('stat-kd').innerText = typeof stats.kd === 'number' ? stats.kd.toFixed(2) : (stats.kd || '0.00');
    document.getElementById('stat-winrate').innerText = stats.winPercent;
    document.getElementById('winrate-fill').style.width = stats.winPercent;
    document.getElementById('stat-kpr').innerText = typeof stats.kpr === 'number' ? stats.kpr.toFixed(2) : (stats.kpr || '0.00');

    // Detailed Individual Stats
    const trySet = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.innerText = val;
    };
    trySet('stat-acs', typeof stats.acs === 'number' ? stats.acs.toFixed(1) : (stats.acs || '0.0'));
    trySet('stat-hs', stats.headshotPercent || '0%');
    trySet('stat-kast', stats.kast || 'N/A');
    trySet('stat-clutches', stats.clutches || '0');
    trySet('stat-flawless', stats.flawless || '0');
    trySet('stat-kills', stats.kills?.toLocaleString() || '0');
    trySet('stat-deaths', stats.deaths?.toLocaleString() || '0');
    trySet('stat-assists', stats.assists?.toLocaleString() || '0');

    // Clear matches section (we show career stats, not individual matches)
    const list = document.getElementById('recent-matches');
    list.innerHTML = `<div style="padding: 30px; text-align: center; color: var(--v-text-muted); background: rgba(255,255,255,0.02); border-radius: 20px; border: 1px solid rgba(255,255,255,0.05);">
        <h4 style="color: #fff, margin-bottom: 20px; text-transform: uppercase; letter-spacing: 2px;">Resumen de Carrera</h4>
        <div style="display: flex; justify-content: space-around; align-items: center; margin-top: 20px;">
            <div style="text-align: center;">
                <div style="font-size: 0.8rem; text-transform: uppercase; color: var(--v-text-muted); margin-bottom: 5px;">Partidas</div>
                <div style="font-size: 1.5rem; font-weight: 800; color: #fff;">${stats.games}</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 0.8rem; text-transform: uppercase; color: #4ade80; margin-bottom: 5px;">Victorias</div>
                <div style="font-size: 1.5rem; font-weight: 800; color: #4ade80;">${stats.wins}</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 0.8rem; text-transform: uppercase; color: #ff4e4e; margin-bottom: 5px;">Derrotas</div>
                <div style="font-size: 1.5rem; font-weight: 800; color: #ff4e4e;">${stats.losses}</div>
            </div>
        </div>
    </div>`;

    // Render Agents Table
    renderTopAgents(profileData.agents || [], 'top-agents-mini');
}

function populateSeasonFilter(mmr) {
    const current = seasonFilter.value;
    seasonFilter.innerHTML = '<option value="lifetime">Todas las Temporadas</option>';
    if (mmr.by_season) {
        Object.keys(mmr.by_season).sort().reverse().forEach(key => {
            const opt = document.createElement('option');
            opt.value = key;
            opt.innerText = key.toUpperCase();
            seasonFilter.appendChild(opt);
        });
    }
    seasonFilter.value = current || 'lifetime';
}

function renderMatches(matches, puuid) {
    const list = document.getElementById('recent-matches');
    list.innerHTML = '';

    matches.slice(0, 5).forEach(m => {
        const me = m.players.all_players.find(p => p.puuid === puuid);
        const myTeam = me.team.toLowerCase();
        const winningTeam = m.teams.red.has_won ? 'red' : 'blue';
        const isWin = myTeam === winningTeam;

        const item = document.createElement('div');
        item.className = 'match-item';
        item.style.setProperty('--status-color', isWin ? '#4ade80' : '#f87171');

        item.innerHTML = `
            <img src="${m.metadata.map_image || ''}" class="map-img">
            <div class="match-meta">
                <div class="match-mode">${m.metadata.mode} • ${m.metadata.map}</div>
                <div class="match-score">${m.teams.blue.rounds_won} - ${m.teams.red.rounds_won}</div>
            </div>
            <div class="match-stats">
                <span>KDA: ${me.stats.kills}/${me.stats.deaths}/${me.stats.assists}</span>
                <span>Score: ${me.stats.score}</span>
            </div>
        `;
        list.appendChild(item);
    });
}

function renderTopAgents(agents, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';

    if (!agents || agents.length === 0) {
        container.innerHTML = '<tr><td colspan="7" style="text-align:center; padding: 20px; color: var(--v-text-muted);">No hay datos de agentes disponibles.</td></tr>';
        return;
    }

    // Sort by matches if not already
    const sorted = [...agents].sort((a, b) => b.matches - a.matches);

    // If it's the mini version (dashboard), show only top 5
    const displayAgents = (containerId === 'top-agents-mini') ? sorted.slice(0, 5) : sorted;

    displayAgents.forEach(a => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>
                <div class="agent-info-cell">
                    <img src="${a.icon}" class="agent-img">
                    <span class="agent-name">${a.name}</span>
                </div>
            </td>
            <td>${a.matches}</td>
            <td>${a.win_percent}</td>
            <td>${typeof a.kd === 'number' ? a.kd.toFixed(2) : a.kd}</td>
            <td>${typeof a.adr === 'number' ? a.adr.toFixed(1) : a.adr}</td>
            <td>${typeof a.acs === 'number' ? a.acs.toFixed(1) : a.acs}</td>
            <td>${a.playtime}</td>
        `;
        container.appendChild(row);
    });
}

function renderManagedAccounts() {
    const grid = document.getElementById('managed-accounts');
    grid.innerHTML = '';

    accounts.forEach(acc => {
        const card = document.createElement('div');
        card.className = 'acc-card';
        if (acc.puuid === activeAccountPuuid) card.style.borderColor = 'var(--v-red)';

        card.innerHTML = `
            <img src="${acc.card?.small || 'https://media.valorant-api.com/playercards/9fb34440-4f0b-49dc-3cb7-578f797d1000/smallart.png'}" class="acc-avatar">
            <div>
                <strong>${acc.name}#${acc.tag}</strong>
                <p>Nivel ${acc.account_level}</p>
            </div>
            <i class="fas fa-times acc-remove" data-puuid="${acc.puuid}"></i>
        `;

        card.addEventListener('click', (e) => {
            if (e.target.classList.contains('acc-remove')) {
                removeAccount(acc.puuid);
            } else {
                selectAccount(acc.puuid);
            }
        });

        grid.appendChild(card);
    });
}

async function removeAccount(puuid) {
    try {
        await apiFetch(`/user/accounts/${puuid}`, { method: 'DELETE' });
        accounts = accounts.filter(a => a.puuid !== puuid);
        aggregateCache = null; // Invalidate cache
        renderManagedAccounts();
        if (activeAccountPuuid === puuid) {
            activeAccountPuuid = null;
            if (accounts.length > 0) selectAccount(accounts[0].puuid);
            else showTab('accounts');
        }
    } catch (err) {
        alert('Error al eliminar cuenta');
    }
}

async function renderAggregateStats() {
    if (accounts.length === 0) {
        showTab('accounts');
        return;
    }

    showLoader(true, `Agregando ${accounts.length} cuenta(s)...`);

    try {
        // Call Flask backend aggregate endpoint
        const response = await fetch(`${BASE_URL}/aggregate?t=${Date.now()}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                accounts: [
                    ...accounts.map(acc => ({
                        name: acc.name,
                        tag: acc.tag,
                        account_level: acc.account_level || 0,
                        region: acc.region || 'latam'
                    })),
                    ...manualMatches.map(m => ({
                        type: 'manual',
                        name: `Partida_${m.id}`,
                        stats: {
                            kills: m.kills,
                            deaths: m.deaths,
                            assists: m.assists,
                            damage: m.damage,
                            rounds: m.rounds,
                            acs: m.acs || 0,
                            kast: m.kast || 0,
                            hs: m.hs || 0,
                            wins: m.result === 'win' ? 1 : 0,
                            losses: m.result === 'loss' ? 1 : 0
                        }
                    }))
                ]
            })
        });

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        // Build aggregate cache from backend response
        aggregateCache = {
            global: data.total,
            kd: data.derived.kd,
            winRate: data.derived.winRate,
            adr: data.derived.adr,
            acs: data.derived.acs,
            hs: data.derived.hs,
            kast: data.derived.kast,
            kad: data.derived.kad,
            kpr: data.derived.kpr,
            losses: data.total.losses,
            clutches: data.total.clutches,
            flawless: data.total.flawless,
            highestRankName: data.highest_rank,
            highestRankImage: data.highest_rank_image,
            agents: data.agents || []
        };
        console.log(">>> AGGREGATE CACHE UPDATED:", aggregateCache);

        updateAggregateUI(aggregateCache);
        // REMOVED: showTab('aggregate'); // This was causing the infinite loop
    } catch (err) {
        console.error('Error fetching aggregate stats:', err);
        alert('Detalle del Error: ' + err.message);
    } finally {
        showLoader(false);
    }
}

function updateAggregateUI(data) {
    console.log(">>> UPDATING AGGREGATE UI WITH:", data);
    const trySet = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.innerText = val;
    };

    const trySetImg = (id, src) => {
        const el = document.getElementById(id);
        if (el && el.tagName === 'IMG') el.src = src;
    };

    // Top section
    if (data.highestRankImage) {
        // Replace old UUID if present in backend response (backup)
        const updatedImg = data.highestRankImage.replace('03621f13-43b2-ad59-395d-209214732c7a', '03621f52-342b-cf4e-4f86-9350a49c6d04');
        trySetImg('global-rank-icon-img', updatedImg);
    } else {
        const tierId = data.global.tier_id || 0;
        let rankImg = `https://media.valorant-api.com/competitivetiers/03621f52-342b-cf4e-4f86-9350a49c6d04/${tierId}/largeicon.png`;
        if (tierId === 0) rankImg = "https://media.valorant-api.com/playercards/9fb34440-4f0b-49dc-3cb7-578f797d1000/displayicon.png";
        trySetImg('global-rank-icon-img', rankImg);
    }
    trySet('global-rank-text', data.highestRankName);
    trySet('global-total-level', data.global.level);
    trySet('global-wins', data.global.wins);
    trySet('global-losses', data.losses);

    // Main stats cards
    trySet('global-adr', typeof data.adr === 'number' ? data.adr.toFixed(1) : (data.adr || '0.0'));
    trySet('global-kd', typeof data.kd === 'number' ? data.kd.toFixed(2) : (data.kd || '0.00'));
    trySet('global-hs', `${data.hs}%`);
    trySet('global-win-percent', `${data.winRate}%`);

    // Grid stats
    trySet('global-wins-alt', data.global.wins);
    trySet('global-kast', `${data.kast}%`);
    trySet('global-dd', typeof data.dd === 'number' ? data.dd.toFixed(1) : (data.dd || "0"));
    trySet('global-kills', data.global.kills.toLocaleString());
    trySet('global-deaths', data.global.deaths.toLocaleString());
    trySet('global-assists', data.global.assists.toLocaleString());
    trySet('global-acs', typeof data.acs === 'number' ? data.acs.toFixed(1) : (data.acs || '0.0'));
    trySet('global-kad', typeof data.kad === 'number' ? data.kad.toFixed(2) : (data.kad || '0.00'));
    trySet('global-kpr', typeof data.kpr === 'number' ? data.kpr.toFixed(2) : (data.kpr || '0.00'));
    trySet('global-clutches', data.clutches);
    trySet('global-flawless', data.flawless);

    // Render Unified Agents Table
    renderTopAgents(data.agents || [], 'global-agents-list');
}


async function addManualMatch() {
    const matchData = {
        result: document.getElementById('m-result').value,
        kills: parseInt(document.getElementById('m-kills').value) || 0,
        deaths: parseInt(document.getElementById('m-deaths').value) || 0,
        assists: parseInt(document.getElementById('m-assists').value) || 0,
        damage: parseInt(document.getElementById('m-damage').value) || 0,
        rounds: parseInt(document.getElementById('m-rounds').value) || 0,
        acs: parseInt(document.getElementById('m-acs').value) || 0,
        kast: parseFloat(document.getElementById('m-kast').value) || 0,
        hs: parseFloat(document.getElementById('m-hs').value) || 0
    };

    try {
        const res = await apiFetch('/user/matches', {
            method: 'POST',
            body: JSON.stringify(matchData)
        });

        manualMatches.push(res.match);

        // Reset form
        document.getElementById('manual-match-form').reset();

        // Invalidate aggregate cache
        aggregateCache = null;

        renderManualMatches();
        alert('Partida guardada correctamente');
    } catch (e) {
        alert('Error al guardar partida: ' + e.message);
    }
}

function renderManualMatches() {
    const list = document.getElementById('manual-matches-list');
    if (!list) return;

    if (manualMatches.length === 0) {
        list.innerHTML = '<p class="empty-msg">No has añadido partidas manuales aún.</p>';
        return;
    }

    list.innerHTML = '';
    manualMatches.forEach(m => {
        const isWin = m.result === 'win';
        const statusColor = isWin ? '#4ade80' : '#f87171';
        const kd = m.deaths > 0 ? (m.kills / m.deaths).toFixed(2) : m.kills.toFixed(2);
        const adr = (m.damage / m.rounds).toFixed(1);

        const div = document.createElement('div');
        div.className = 'manual-item';
        div.style.setProperty('--status-color', statusColor);
        div.innerHTML = `
            <div class="match-result-badge" style="background: ${isWin ? 'rgba(74,222,128,0.1)' : 'rgba(248,113,113,0.1)'}; border: 1px solid ${statusColor}; color: ${statusColor}; padding: 6px 14px; border-radius: 8px; font-weight: 800; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; min-width: 80px; text-align: center;">
                ${isWin ? '🏆 Victoria' : '💀 Derrota'}
            </div>
            <div class="m-info" style="flex: 1; padding: 0 20px;">
                <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                    <span style="color:#fff; font-weight:700;">K/D: <span style="color:${statusColor}">${kd}</span></span>
                    <span style="color:var(--v-text-muted);">ADR: ${adr}</span>
                    <span style="color:var(--v-text-muted);">ACS: ${m.acs}</span>
                    <span style="color:var(--v-text-muted);">KAST: ${m.kast}%</span>
                    <span style="color:var(--v-text-muted);">HS: ${m.hs}%</span>
                    <span style="color:var(--v-text-muted);">Rondas: ${m.rounds}</span>
                </div>
            </div>
            <div class="m-delete" onclick="deleteManualMatch(${m.id})" title="Eliminar">
                <i class="fas fa-trash"></i>
            </div>
        `;
        list.appendChild(div);
    });
}

async function deleteManualMatch(id) {
    if (!confirm('¿Seguro que quieres eliminar esta partida?')) return;
    try {
        await apiFetch(`/user/matches/${id}`, { method: 'DELETE' });
        manualMatches = manualMatches.filter(m => m.id !== id);
        aggregateCache = null;
        renderManualMatches();
    } catch (e) {
        alert('Error al eliminar partida');
    }
}

function showLoader(show, text = 'Cargando...') {
    if (show) {
        loader.querySelector('p').innerText = text;
        loader.classList.remove('hidden');
    } else {
        loader.classList.add('hidden');
    }
}
