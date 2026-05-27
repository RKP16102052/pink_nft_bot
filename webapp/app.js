const telegramApp = window.Telegram?.WebApp || null;

if (telegramApp) {
    telegramApp.ready();
    telegramApp.expand();
    telegramApp.setHeaderColor?.('#fff0f6');
    telegramApp.setBackgroundColor?.('#fff7fb');
}

const API_BASE = '/api';

const state = {
    user: null,
    activeTab: 'market',
    market: [],
    myNfts: [],
    collections: [],
    topupRate: null,
    tonWallet: null,
    selectedHistory: null,
    chart: null,
};

let tonConnectUI = null;
const PENDING_TOPUP_KEY = 'pinkPendingTopup';

function initTonConnect() {
    if (!window.TON_CONNECT_UI) {
        return;
    }

    tonConnectUI = new TON_CONNECT_UI.TonConnectUI({
        manifestUrl: `${window.location.origin}/webapp/tonconnect-manifest.json`,
        buttonRootId: 'ton-connect-button',
    });

    tonConnectUI.connectionRestored.then((restored) => {
        state.tonWallet = restored ? tonConnectUI.wallet : null;
    });

    tonConnectUI.onStatusChange((wallet) => {
        state.tonWallet = wallet || null;
    });
}

function getInitData() {
    return telegramApp?.initData || '';
}

function authHeaders(hasJsonBody = true) {
    const headers = { 'X-Telegram-InitData': getInitData() };
    if (hasJsonBody) {
        headers['Content-Type'] = 'application/json';
    }
    return headers;
}

async function apiFetch(url, options = {}) {
    const hasBody = Boolean(options.body);
    const response = await fetch(API_BASE + url, {
        ...options,
        headers: {
            ...authHeaders(hasBody),
            ...options.headers,
        },
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Ошибка запроса' }));
        throw new Error(error.detail || 'Ошибка запроса');
    }

    if (response.status === 204) {
        return null;
    }

    return response.json();
}

function contentEl() {
    return document.getElementById('content');
}

function escapeHtml(value = '') {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function formatMoney(value) {
    if (value === null || value === undefined) {
        return '0 PINK';
    }
    return `${Number(value).toLocaleString('ru-RU', {
        maximumFractionDigits: 2,
        minimumFractionDigits: Number(value) % 1 === 0 ? 0 : 2,
    })} PINK`;
}

function shortDate(value) {
    return new Date(value).toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
    });
}

function showToast(message) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.add('is-visible');
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => toast.classList.remove('is-visible'), 2600);
}

function setActiveTab(tab) {
    state.activeTab = tab;
    document.querySelectorAll('.tab').forEach((button) => {
        button.classList.toggle('is-active', button.id === `tab-${tab}`);
    });
}

function renderUser() {
    const target = document.getElementById('user-info');
    if (!state.user) {
        target.textContent = '';
        return;
    }

    target.innerHTML = `
        <span>${escapeHtml(state.user.first_name)}</span>
        <strong>${formatMoney(state.user.balance)}</strong>
    `;
    document.getElementById('tab-admin').hidden = state.user.role !== 'admin';
}

function renderLoading(title = 'Загрузка') {
    contentEl().innerHTML = `
        <section class="panel center-panel">
            <div class="loader"></div>
            <h2>${escapeHtml(title)}</h2>
        </section>
    `;
}

function renderError(error) {
    contentEl().innerHTML = `
        <section class="panel center-panel">
            <h2>Не удалось загрузить данные</h2>
            <p>${escapeHtml(error.message)}</p>
        </section>
    `;
}

function nftMedia(nft) {
    const imageUrl = (nft.image_url || '').trim();
    if (!imageUrl) {
        return `<div class="nft-placeholder">${escapeHtml(nft.name.slice(0, 1).toUpperCase())}</div>`;
    }

    return `
        <img
            src="${escapeHtml(imageUrl)}"
            alt="${escapeHtml(nft.name)}"
            loading="lazy"
            onerror="this.outerHTML='<div class=&quot;nft-placeholder&quot;>?</div>'"
        >
    `;
}

function marketStats(nfts) {
    const prices = nfts.map((nft) => nft.price).filter((price) => Number.isFinite(price));
    const total = prices.reduce((sum, price) => sum + price, 0);
    const avg = prices.length ? total / prices.length : 0;
    const max = prices.length ? Math.max(...prices) : 0;

    return `
        <section class="stats-grid">
            <div class="stat">
                <span>Лоты</span>
                <strong>${nfts.length}</strong>
            </div>
            <div class="stat">
                <span>Средняя цена</span>
                <strong>${formatMoney(avg)}</strong>
            </div>
            <div class="stat">
                <span>Максимум</span>
                <strong>${formatMoney(max)}</strong>
            </div>
        </section>
    `;
}

function renderTopupPanel() {
    const rate = state.topupRate?.pink_per_ton || 0;
    const isConfigured = Boolean(state.topupRate?.treasury_address_configured);

    return `
        <section class="topup-panel">
            <div>
                <span class="section-label">PINK</span>
                <h2>Купить за TON</h2>
            </div>
            <div class="topup-form">
                <input id="topup-ton" type="number" min="0" step="0.01" inputmode="decimal" placeholder="TON">
                <output id="topup-preview">${formatMoney(0)}</output>
                <button class="primary-btn" type="button" data-action="topup" ${isConfigured ? '' : 'disabled'}>
                    Купить PINK
                </button>
            </div>
            <div class="rate-line">
                <span>1 TON</span>
                <strong>${formatMoney(rate)}</strong>
            </div>
            ${isConfigured ? '' : '<p class="form-note">Казначейский TON-адрес не задан</p>'}
        </section>
    `;
}

function renderNftCard(nft, source) {
    const isMine = source === 'my';
    const saleBadge = nft.is_for_sale
        ? `<span class="badge sale">В продаже</span>`
        : `<span class="badge">В кошельке</span>`;
    const description = nft.description || 'Без описания';

    return `
        <article class="nft-card">
            <div class="nft-visual">${nftMedia(nft)}</div>
            <div class="nft-info">
                <div class="nft-title-row">
                    <h3>${escapeHtml(nft.name)}</h3>
                    ${saleBadge}
                </div>
                <p>${escapeHtml(description)}</p>
                <div class="price-row">
                    <span>Цена</span>
                    <strong>${nft.price ? formatMoney(nft.price) : 'Не выставлен'}</strong>
                </div>
                <div class="sparkline-shell">
                    <canvas id="sparkline-${source}-${nft.id}" height="48"></canvas>
                </div>
            </div>
            <div class="card-actions">
                <button class="ghost-btn" type="button" data-action="history" data-source="${source}" data-id="${nft.id}">График</button>
                ${isMine ? myNftControls(nft) : buyButton(nft)}
            </div>
        </article>
    `;
}

function buyButton(nft) {
    return `<button class="primary-btn" type="button" data-action="buy" data-id="${nft.id}">Купить</button>`;
}

function myNftControls(nft) {
    const cancelButton = nft.is_for_sale
        ? `<button class="ghost-btn" type="button" data-action="cancel" data-id="${nft.id}">Снять</button>`
        : '';

    return `
        <div class="sell-form">
            <input id="sell-price-${nft.id}" type="number" min="0" step="0.01" inputmode="decimal" placeholder="Цена" value="${nft.price || ''}">
            <input id="seller-address-${nft.id}" type="text" placeholder="TON-адрес" value="${escapeHtml(nft.seller_address || '')}">
            <button class="primary-btn" type="button" data-action="sell" data-id="${nft.id}">
                ${nft.is_for_sale ? 'Обновить' : 'Выставить'}
            </button>
            ${cancelButton}
        </div>
    `;
}

async function loadMarket() {
    setActiveTab('market');
    renderLoading('Маркет');
    try {
        const [market, rate] = await Promise.all([
            apiFetch('/nfts?for_sale=true'),
            apiFetch('/wallet/topup/rate'),
        ]);
        state.market = market;
        state.topupRate = rate;
        contentEl().innerHTML = `
            ${renderTopupPanel()}
            ${marketStats(state.market)}
            <section class="list-panel">
                ${state.market.length
                    ? state.market.map((nft) => renderNftCard(nft, 'market')).join('')
                    : '<div class="empty-state">На рынке пока нет активных лотов</div>'}
            </section>
        `;
        document.getElementById('topup-ton')?.addEventListener('input', updateTopupPreview);
        updateTopupPreview();
        hydrateSparklines(state.market, 'market');
    } catch (error) {
        renderError(error);
    }
}

function updateTopupPreview() {
    const input = document.getElementById('topup-ton');
    const output = document.getElementById('topup-preview');
    if (!input || !output) {
        return;
    }

    const tonAmount = Number(input.value);
    const rate = state.topupRate?.pink_per_ton || 0;
    const pinkAmount = Number.isFinite(tonAmount) && tonAmount > 0 ? tonAmount * rate : 0;
    output.textContent = formatMoney(pinkAmount);
}

async function buyPink(button) {
    if (!tonConnectUI) {
        showToast('TonConnect не загружен');
        return;
    }
    if (!state.tonWallet) {
        await tonConnectUI.openModal();
        showToast('Подключите TON-кошелек');
        return;
    }

    const input = document.getElementById('topup-ton');
    const tonAmount = Number(input?.value);
    if (!Number.isFinite(tonAmount) || tonAmount <= 0) {
        showToast('Укажите сумму TON');
        return;
    }

    setButtonBusy(button, true);
    let topup = null;
    let txBoc = null;
    try {
        topup = await apiFetch('/wallet/topup/request', {
            method: 'POST',
            body: JSON.stringify({ ton_amount: tonAmount }),
        });
        const transaction = {
            validUntil: Math.floor(Date.now() / 1000) + 600,
            network: state.topupRate?.ton_network || '-3',
            messages: [{
                address: topup.treasury_address,
                amount: String(Math.round(topup.ton_amount * 1e9)),
                payload: topup.payload,
            }],
        };

        const result = await tonConnectUI.sendTransaction(transaction);
        txBoc = result.boc;
        localStorage.setItem(PENDING_TOPUP_KEY, JSON.stringify({
            topup_id: topup.id,
            tx_boc: txBoc,
            pink_amount: topup.pink_amount,
        }));
        state.user = await apiFetch('/wallet/topup/confirm', {
            method: 'POST',
            body: JSON.stringify({
                topup_id: topup.id,
                tx_boc: txBoc,
            }),
        });
        localStorage.removeItem(PENDING_TOPUP_KEY);
        renderUser();
        showToast(`Начислено ${formatMoney(topup.pink_amount)}`);
        input.value = '';
        updateTopupPreview();
    } catch (error) {
        if (topup && txBoc) {
            showToast(`${error.message}. Подтверждение повторится позже`);
            schedulePendingTopupRetry();
        } else {
            showToast(error.message);
        }
    } finally {
        setButtonBusy(button, false);
    }
}

async function confirmPendingTopup() {
    const raw = localStorage.getItem(PENDING_TOPUP_KEY);
    if (!raw) {
        return true;
    }

    try {
        const pending = JSON.parse(raw);
        state.user = await apiFetch('/wallet/topup/confirm', {
            method: 'POST',
            body: JSON.stringify({
                topup_id: pending.topup_id,
                tx_boc: pending.tx_boc,
            }),
        });
        localStorage.removeItem(PENDING_TOPUP_KEY);
        renderUser();
        showToast(`Начислено ${formatMoney(pending.pink_amount)}`);
        return true;
    } catch {
        // TonCenter can lag behind wallet confirmation; keep the request for the next app open.
        return false;
    }
}

function schedulePendingTopupRetry() {
    [7000, 20000, 45000].forEach((delay) => {
        window.setTimeout(syncPendingTopups, delay);
    });
}

async function syncPendingTopups() {
    await confirmPendingTopup();

    try {
        state.user = await apiFetch('/wallet/topup/retry_pending', { method: 'POST' });
        renderUser();
    } catch {
        // Keep UI quiet: this is a background reconciliation pass.
    }
}

async function loadMyNfts() {
    setActiveTab('my');
    renderLoading('Мои NFT');
    try {
        state.myNfts = await apiFetch('/nfts?my=true');
        contentEl().innerHTML = `
            <section class="list-panel">
                ${state.myNfts.length
                    ? state.myNfts.map((nft) => renderNftCard(nft, 'my')).join('')
                    : '<div class="empty-state">В коллекции пока нет NFT</div>'}
            </section>
        `;
        hydrateSparklines(state.myNfts, 'my');
    } catch (error) {
        renderError(error);
    }
}

async function sellNft(id, button) {
    const priceInput = document.getElementById(`sell-price-${id}`);
    const addressInput = document.getElementById(`seller-address-${id}`);
    const price = Number(priceInput.value);

    if (!Number.isFinite(price) || price <= 0) {
        showToast('Укажите цену больше нуля');
        return;
    }

    setButtonBusy(button, true);
    try {
        await apiFetch('/nfts/sell', {
            method: 'POST',
            body: JSON.stringify({
                nft_id: id,
                price,
                seller_address: addressInput.value.trim() || null,
            }),
        });
        showToast('NFT выставлен на продажу');
        await loadMyNfts();
    } catch (error) {
        showToast(error.message);
    } finally {
        setButtonBusy(button, false);
    }
}

async function cancelSell(id, button) {
    setButtonBusy(button, true);
    try {
        await apiFetch(`/nfts/cancel_sell?nft_id=${id}`, { method: 'POST' });
        showToast('Лот снят с продажи');
        await loadMyNfts();
    } catch (error) {
        showToast(error.message);
    } finally {
        setButtonBusy(button, false);
    }
}

async function buyNft(id, button) {
    const nft = state.market.find((item) => item.id === id);
    if (!nft) {
        return;
    }

    const confirmed = window.confirm(`Купить ${nft.name} за ${formatMoney(nft.price)}?`);
    if (!confirmed) {
        return;
    }

    setButtonBusy(button, true);
    try {
        await apiFetch('/nfts/buy/internal', {
            method: 'POST',
            body: JSON.stringify({ nft_id: id }),
        });
        showToast('Покупка завершена');
        state.user = await apiFetch('/me');
        renderUser();
        await loadMarket();
    } catch (error) {
        showToast(error.message);
    } finally {
        setButtonBusy(button, false);
    }
}

function setButtonBusy(button, isBusy) {
    if (!button) {
        return;
    }
    button.disabled = isBusy;
    button.classList.toggle('is-busy', isBusy);
}

async function hydrateSparklines(nfts, source) {
    await Promise.all(nfts.map(async (nft) => {
        const canvas = document.getElementById(`sparkline-${source}-${nft.id}`);
        if (!canvas) {
            return;
        }

        try {
            const history = await apiFetch(`/nfts/${nft.id}/history`);
            drawSparkline(canvas, history, nft.price);
        } catch {
            drawSparkline(canvas, [], nft.price);
        }
    }));
}

function drawSparkline(canvas, history, currentPrice) {
    const context = canvas.getContext('2d');
    if (!context) {
        return;
    }

    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth || 220;
    const height = canvas.clientHeight || 48;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);

    let values = history.map((point) => Number(point.price)).filter(Number.isFinite);
    if (!values.length && currentPrice) {
        values = [Number(currentPrice)];
    }
    if (!values.length) {
        context.strokeStyle = '#ffd3e5';
        context.beginPath();
        context.moveTo(0, height / 2);
        context.lineTo(width, height / 2);
        context.stroke();
        return;
    }
    if (values.length === 1) {
        values = [values[0], values[0]];
    }

    let min = Math.min(...values);
    let max = Math.max(...values);
    if (min === max) {
        min -= 1;
        max += 1;
    }

    const points = values.map((value, index) => ({
        x: (index / (values.length - 1)) * width,
        y: height - ((value - min) / (max - min)) * (height - 10) - 5,
    }));

    const gradient = context.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, 'rgba(236, 64, 122, 0.28)');
    gradient.addColorStop(1, 'rgba(236, 64, 122, 0)');

    context.beginPath();
    points.forEach((point, index) => {
        if (index === 0) {
            context.moveTo(point.x, point.y);
        } else {
            context.lineTo(point.x, point.y);
        }
    });
    context.lineTo(width, height);
    context.lineTo(0, height);
    context.closePath();
    context.fillStyle = gradient;
    context.fill();

    context.beginPath();
    points.forEach((point, index) => {
        if (index === 0) {
            context.moveTo(point.x, point.y);
        } else {
            context.lineTo(point.x, point.y);
        }
    });
    context.strokeStyle = '#ec407a';
    context.lineWidth = 2;
    context.stroke();
}

async function openHistory(id, source) {
    renderLoading('График');
    const pool = [...state.market, ...state.myNfts];
    const nft = pool.find((item) => item.id === id) || { id, name: `NFT #${id}` };

    try {
        const history = await apiFetch(`/nfts/${id}/history`);
        state.selectedHistory = { nft, history, source, range: 'week' };
        renderHistory();
    } catch (error) {
        renderError(error);
    }
}

function filteredHistory(history, range) {
    if (range === 'all') {
        return history;
    }

    const days = range === 'month' ? 30 : 7;
    const border = Date.now() - days * 24 * 60 * 60 * 1000;
    return history.filter((point) => new Date(point.timestamp).getTime() >= border);
}

function renderHistory(range = state.selectedHistory?.range || 'week') {
    if (!state.selectedHistory) {
        return;
    }

    const { nft, history, source } = state.selectedHistory;
    state.selectedHistory.range = range;
    const points = filteredHistory(history, range);
    const values = points.map((point) => Number(point.price));
    const lastPrice = values.length ? values[values.length - 1] : nft.price;
    const minPrice = values.length ? Math.min(...values) : lastPrice || 0;
    const maxPrice = values.length ? Math.max(...values) : lastPrice || 0;

    contentEl().innerHTML = `
        <section class="history-panel">
            <div class="history-head">
                <button class="ghost-btn" type="button" data-action="back" data-source="${source}">Назад</button>
                <div>
                    <span class="section-label">Динамика цены</span>
                    <h2>${escapeHtml(nft.name)}</h2>
                </div>
            </div>
            <div class="range-tabs">
                <button class="${range === 'week' ? 'is-active' : ''}" type="button" data-action="range" data-range="week">7 дней</button>
                <button class="${range === 'month' ? 'is-active' : ''}" type="button" data-action="range" data-range="month">30 дней</button>
                <button class="${range === 'all' ? 'is-active' : ''}" type="button" data-action="range" data-range="all">Все</button>
            </div>
            <div class="chart-card">
                <canvas id="price-chart"></canvas>
            </div>
            <div class="stats-grid compact">
                <div class="stat">
                    <span>Последняя</span>
                    <strong>${formatMoney(lastPrice || 0)}</strong>
                </div>
                <div class="stat">
                    <span>Минимум</span>
                    <strong>${formatMoney(minPrice)}</strong>
                </div>
                <div class="stat">
                    <span>Максимум</span>
                    <strong>${formatMoney(maxPrice)}</strong>
                </div>
            </div>
        </section>
    `;

    renderPriceChart(points, nft.price);
}

function renderPriceChart(points, currentPrice) {
    const canvas = document.getElementById('price-chart');
    if (!canvas || !window.Chart) {
        return;
    }

    if (state.chart) {
        state.chart.destroy();
    }

    const labels = points.length ? points.map((point) => shortDate(point.timestamp)) : ['Сейчас'];
    const values = points.length ? points.map((point) => point.price) : [currentPrice || 0];

    state.chart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Цена PINK',
                data: values,
                borderColor: '#ec407a',
                backgroundColor: 'rgba(236, 64, 122, 0.14)',
                fill: true,
                tension: 0.35,
                pointRadius: 3,
                pointHoverRadius: 5,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (context) => formatMoney(context.parsed.y),
                    },
                },
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: '#7a3652' },
                },
                y: {
                    beginAtZero: false,
                    grid: { color: '#ffe1ed' },
                    ticks: {
                        color: '#7a3652',
                        callback: (value) => Number(value).toLocaleString('ru-RU'),
                    },
                },
            },
        },
    });
}

async function loadAdmin() {
    if (state.user?.role !== 'admin') {
        await loadMarket();
        return;
    }

    setActiveTab('admin');
    renderLoading('Админ');
    try {
        state.collections = await apiFetch('/collections');
        renderAdmin();
    } catch (error) {
        renderError(error);
    }
}

function renderAdmin() {
    const collectionOptions = state.collections.map((collection) => (
        `<option value="${collection.id}">${escapeHtml(collection.name)}</option>`
    )).join('');

    contentEl().innerHTML = `
        <section class="admin-grid">
            <form class="panel form-panel" id="collection-form">
                <div class="form-head">
                    <span class="section-label">Коллекции</span>
                    <h2>Новая коллекция</h2>
                </div>
                <input id="collection-name" type="text" placeholder="Название" required>
                <input id="collection-description" type="text" placeholder="Описание">
                <input id="collection-image" type="url" placeholder="URL обложки">
                <input id="collection-address" type="text" placeholder="Адрес контракта">
                <button class="primary-btn" type="submit">Добавить коллекцию</button>
            </form>

            <form class="panel form-panel" id="nft-form">
                <div class="form-head">
                    <span class="section-label">NFT</span>
                    <h2>Новый подарок</h2>
                </div>
                <select id="nft-collection">
                    <option value="">Без коллекции</option>
                    ${collectionOptions}
                </select>
                <input id="nft-name" type="text" placeholder="Название" required>
                <input id="nft-description" type="text" placeholder="Описание">
                <input id="nft-image" type="url" placeholder="URL изображения">
                <input id="nft-address" type="text" placeholder="Адрес NFT">
                <input id="nft-owner" type="number" inputmode="numeric" placeholder="Telegram ID владельца">
                <button class="primary-btn" type="submit">Добавить NFT</button>
            </form>

            <section class="panel form-panel">
                <div class="form-head">
                    <span class="section-label">Логи</span>
                    <h2>История цен</h2>
                </div>
                <button class="primary-btn" type="button" id="download-logs">Скачать CSV</button>
            </section>
        </section>
    `;

    document.getElementById('collection-form').addEventListener('submit', createCollection);
    document.getElementById('nft-form').addEventListener('submit', createNft);
    document.getElementById('download-logs').addEventListener('click', downloadLogs);
}

async function createCollection(event) {
    event.preventDefault();
    const body = {
        name: document.getElementById('collection-name').value.trim(),
        description: document.getElementById('collection-description').value.trim(),
        image_url: document.getElementById('collection-image').value.trim(),
        contract_address: document.getElementById('collection-address').value.trim() || null,
    };

    if (!body.name) {
        showToast('Название коллекции обязательно');
        return;
    }

    try {
        await apiFetch('/admin/collections', {
            method: 'POST',
            body: JSON.stringify(body),
        });
        showToast('Коллекция добавлена');
        await loadAdmin();
    } catch (error) {
        showToast(error.message);
    }
}

async function createNft(event) {
    event.preventDefault();
    const collectionId = document.getElementById('nft-collection').value;
    const ownerId = document.getElementById('nft-owner').value.trim();
    const body = {
        name: document.getElementById('nft-name').value.trim(),
        description: document.getElementById('nft-description').value.trim(),
        image_url: document.getElementById('nft-image').value.trim(),
        nft_address: document.getElementById('nft-address').value.trim() || null,
        collection_id: collectionId ? Number(collectionId) : null,
        owner_telegram_id: ownerId ? Number(ownerId) : null,
    };

    if (!body.name) {
        showToast('Название NFT обязательно');
        return;
    }

    try {
        await apiFetch('/admin/nfts', {
            method: 'POST',
            body: JSON.stringify(body),
        });
        showToast('NFT добавлен');
        await loadAdmin();
    } catch (error) {
        showToast(error.message);
    }
}

async function downloadLogs() {
    try {
        const response = await fetch(`${API_BASE}/admin/logs`, {
            headers: authHeaders(false),
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Не удалось скачать CSV' }));
            throw new Error(error.detail || 'Не удалось скачать CSV');
        }

        const blob = await response.blob();
        const href = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = href;
        link.download = 'price-history.csv';
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(href);
    } catch (error) {
        showToast(error.message);
    }
}

document.getElementById('tab-market').addEventListener('click', loadMarket);
document.getElementById('tab-my').addEventListener('click', loadMyNfts);
document.getElementById('tab-admin').addEventListener('click', loadAdmin);

document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-action]');
    if (!button) {
        return;
    }

    const action = button.dataset.action;
    const id = Number(button.dataset.id);

    if (action === 'history') {
        openHistory(id, button.dataset.source);
    }
    if (action === 'buy') {
        buyNft(id, button);
    }
    if (action === 'sell') {
        sellNft(id, button);
    }
    if (action === 'cancel') {
        cancelSell(id, button);
    }
    if (action === 'topup') {
        buyPink(button);
    }
    if (action === 'range') {
        renderHistory(button.dataset.range);
    }
    if (action === 'back') {
        button.dataset.source === 'my' ? loadMyNfts() : loadMarket();
    }
});

async function boot() {
    renderLoading();
    try {
        state.user = await apiFetch('/me');
        renderUser();
        await syncPendingTopups();
        const params = new URLSearchParams(window.location.search);
        if (params.get('mode') === 'admin' && state.user.role === 'admin') {
            await loadAdmin();
            return;
        }
        await loadMarket();
    } catch (error) {
        renderError(error);
    }
}

initTonConnect();
boot();
