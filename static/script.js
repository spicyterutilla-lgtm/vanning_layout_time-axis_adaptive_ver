/* ============================================
   ISUZU Vanning Optimizer — Frontend Logic
   Dashboard-first, visual-first rewrite
   ============================================ */

// --- DOM refs ---
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const btnRun = document.getElementById('btn-run');
const btnRolling = document.getElementById('btn-rolling');
const btnScenario = document.getElementById('btn-scenario');

// --- State ---
let currentContainersData = [];

// =====================
// Utilities
// =====================
function esc(v) {
    return String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function num(id, fallback, min, max) {
    const v = parseInt(document.getElementById(id)?.value, 10);
    return Math.min(max, Math.max(min, Number.isFinite(v) ? v : fallback));
}

// =====================
// Navigation
// =====================
function showStep(n) {
    document.querySelectorAll('.step-panel').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.step-dot').forEach(el => { el.classList.remove('active'); el.classList.remove('done'); });
    document.getElementById(`step-${n}`).classList.add('active');
    document.getElementById(`step-${n}-nav`).classList.add('active');
    for (let i = 1; i < n; i++) document.getElementById(`step-${i}-nav`).classList.add('done');
}

// =====================
// Init
// =====================
document.addEventListener('DOMContentLoaded', async () => {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        if (data.has_data) {
            document.getElementById('total-items').textContent = data.total_items;
            document.getElementById('base-date').valueAsDate = new Date();
            renderValidation(data);
            showStep(2);
        }
    } catch(e) { console.error("Status error", e); }
});

// =====================
// File Upload
// =====================
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', e => {
    if (e.target.files.length) uploadFile(e.target.files[0]);
});

async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    dropZone.innerHTML = '<div class="upload-spinner"></div><p>データを読み込み中...</p>';

    try {
        const res = await fetch('/api/upload', { method: 'POST', body: formData });
        const data = await res.json();
        if (res.ok) {
            document.getElementById('total-items').textContent = data.total_items;
            document.getElementById('base-date').valueAsDate = new Date();
            renderValidation(data);
            showStep(2);
        } else {
            alert('エラー: ' + data.error);
            resetUpload();
        }
    } catch(e) { alert('通信エラー'); resetUpload(); }
}

function resetUpload() {
    dropZone.innerHTML = '<div class="upload-icon">📦</div><p>ここにファイルをドラッグ＆ドロップ</p><p class="hint">または、クリックして選択</p>';
}

function renderValidation(data) {
    const bar = document.getElementById('validation-bar');
    if (!bar) return;
    const s = data.validation_summary;
    if (!s || s.total === 0) { bar.style.display = 'none'; return; }
    bar.style.display = 'flex';
    bar.className = 'validation-bar';
    bar.textContent = `⚠ エラー除外 ${s.errors}件 / 注意 ${s.warnings}件`;
}

// =====================
// Optimize (Single Day)
// =====================
btnRun.addEventListener('click', async () => {
    showStep(3);
    const loadingText = document.getElementById('loading-text');
    const phases = ["データ構造を解析中...", "納期と期限を評価中...", "空き埋め候補を探索中...", "3D配置を計算中...", "結果を生成中..."];
    let pi = 0;
    const interval = setInterval(() => { pi = (pi + 1) % phases.length; if (loadingText) loadingText.textContent = phases[pi]; }, 700);

    const baseDate = document.getElementById('base-date').value;
    const mustWindow = num('must-window', 7, 0, 30);

    try {
        const res = await fetch('/api/optimize', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ base_date: baseDate, must_ship_window_days: mustWindow })
        });
        const data = await res.json();
        clearInterval(interval);
        if (res.ok) { renderDashboard(data); showStep(4); }
        else { alert('エラー: ' + data.error); showStep(2); }
    } catch(e) { clearInterval(interval); alert('通信エラー'); showStep(2); }
});

// =====================
// Dashboard Rendering
// =====================
function renderDashboard(data) {
    currentContainersData = data.containers;
    const cmp = data.comparison || {};
    const before = cmp.baseline || {};
    const after = cmp.optimized || {};
    const delta = cmp.delta || {};

    // --- KPI Cards ---
    document.getElementById('kpi-containers').textContent = data.containers.length;
    const cDelta = document.getElementById('kpi-containers-delta');
    if (delta.container_count > 0) {
        cDelta.textContent = `前倒しなし比 −${delta.container_count}本`;
        cDelta.className = 'kpi-delta good';
    } else if (delta.container_count < 0) {
        cDelta.textContent = `前倒しなし比 +${Math.abs(delta.container_count)}本`;
        cDelta.className = 'kpi-delta bad';
    } else {
        cDelta.textContent = '';
        cDelta.className = 'kpi-delta';
    }

    const alertCount = data.alert_containers || 0;
    document.getElementById('kpi-alerts').textContent = alertCount;
    const alertCard = document.getElementById('kpi-card-alerts');
    alertCard.classList.toggle('has-alert', alertCount > 0);

    const avgVol = after.avg_volume_rate ?? (data.containers.length ? Math.round(data.containers.reduce((s,c) => s + c.volume_rate, 0) / data.containers.length * 10) / 10 : 0);
    document.getElementById('kpi-fillrate').textContent = avgVol;
    const fDelta = document.getElementById('kpi-fillrate-delta');
    if (delta.avg_volume_rate > 0) {
        fDelta.textContent = `+${delta.avg_volume_rate}pt 改善`;
        fDelta.className = 'kpi-delta good';
    } else if (delta.avg_volume_rate < 0) {
        fDelta.textContent = `${delta.avg_volume_rate}pt`;
        fDelta.className = 'kpi-delta bad';
    } else {
        fDelta.textContent = '';
    }

    // --- Summary Line ---
    const sl = document.getElementById('summary-line');
    const pullText = (data.total_pulls > 0) ? ` / 空き埋め <strong>${data.total_pulls}</strong>件` : '';
    const alertHtml = alertCount > 0
        ? ` / <span class="accent">要確認 ${alertCount}本</span>`
        : ' / <span class="ok">全て80%クリア</span>';
    sl.innerHTML = `<strong>${data.containers.length}本</strong>で確定${pullText}${alertHtml}`;

    // --- Container Grid ---
    const grid = document.getElementById('container-grid');
    grid.innerHTML = '';

    data.containers.forEach(c => {
        const isAlert = c.is_alert;
        const pullCount = c.items.filter(i => i.status_msg && i.status_msg.includes('前倒し')).length;
        const isPulled = pullCount > 0 && !isAlert;

        let statusClass, signalClass, badgeClass, badgeText;
        if (isAlert) {
            statusClass = 'alert'; signalClass = 'red'; badgeClass = 'alert'; badgeText = '要確認';
        } else if (isPulled) {
            statusClass = 'warn'; signalClass = 'yellow'; badgeClass = 'warn'; badgeText = '補填済み';
        } else {
            statusClass = 'ok'; signalClass = 'green'; badgeClass = 'ok'; badgeText = 'OK';
        }

        // Fill bar
        const volRate = c.volume_rate;
        const fillClass = volRate >= 80 ? 'ok' : volRate >= 60 ? 'warn' : 'alert';

        // Short reason
        let reasonHtml = '';
        if (isAlert && c.alert_reason_title) {
            reasonHtml = `<div class="c-reason force">${esc(c.alert_reason_title)}</div>`;
        } else if (isPulled) {
            reasonHtml = `<div class="c-reason pull">空き埋め ${pullCount}件で80%達成</div>`;
        }

        // Item details (collapsed)
        let itemsHtml = '';
        c.items.forEach(i => {
            let tagHtml = '';
            if (i.status_msg && i.status_msg.includes('前倒し')) tagHtml = '<span class="item-tag pull">空き埋め</span>';
            else if (i.is_force_ship) tagHtml = '<span class="item-tag force">強制出荷</span>';
            const idsJson = JSON.stringify([i.id]).replace(/"/g, '&quot;');
            const isManual = i.is_manual_force_ship;
            itemsHtml += `<div class="c-item-row" onclick="toggleOverride(${idsJson}, ${!isManual})">
                <span class="item-name">${esc(i.name)}</span>
                ${tagHtml}
            </div>`;
        });

        const card = document.createElement('div');
        card.className = `c-card ${statusClass}`;
        card.innerHTML = `
            <div class="c-head">
                <div class="c-num"><span class="signal ${signalClass}"></span>${c.display_order ?? ''}本目</div>
                <span class="c-badge ${badgeClass}">${badgeText}</span>
            </div>
            <div class="fill-bar">
                <div class="bar-head">
                    <span class="bar-label">積載率</span>
                    <span class="bar-val">${volRate}%</span>
                </div>
                <div class="fill-track"><div class="fill-bar-inner ${fillClass}" style="width:${Math.min(100, volRate)}%"></div></div>
            </div>
            <div class="c-stats">
                <span>荷物 <strong>${c.items.length}</strong>件</span>
                <span>重量 <strong>${Math.round(c.weight_val).toLocaleString()}</strong>kg</span>
            </div>
            ${reasonHtml}
            <div class="c-footer" onclick="open3D('${c.id}')">📦 3Dで中身を見る</div>
            <details class="c-details">
                <summary>荷物一覧 (${c.items.length}件)</summary>
                <div style="margin-top:0.5rem;">${itemsHtml}</div>
            </details>
        `;
        // Card click opens 3D (except details area)
        card.addEventListener('click', (e) => {
            if (e.target.closest('.c-details') || e.target.closest('.c-footer') || e.target.closest('.c-item-row')) return;
            open3D(c.id);
        });
        grid.appendChild(card);
    });
}

// =====================
// Override (Manual Force Ship)
// =====================
async function toggleOverride(itemIds, forceShip) {
    const action = forceShip ? "強制出荷" : "強制出荷の解除";
    if (!confirm(`この荷物を「${action}」に変更して再計算しますか？`)) return;

    try {
        const res = await fetch('/api/override', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ item_ids: itemIds, force_ship: forceShip })
        });
        if (res.ok) { btnRun.click(); }
        else { alert("エラーが発生しました"); }
    } catch(e) { alert('通信エラー'); }
}

// =====================
// Export
// =====================
function downloadExcel() { window.location.href = '/api/export'; }
function downloadRollingExcel() { window.location.href = '/api/export_rolling'; }

// =====================
// Admin Panel (Rolling / Scenarios)
// =====================
function toggleAdmin(e) {
    e.preventDefault();
    const panel = document.getElementById('admin-panel');
    const toggle = document.getElementById('admin-toggle');
    const isVisible = panel.classList.contains('visible');
    panel.classList.toggle('visible');
    toggle.textContent = isVisible ? '管理者向け分析 ▸' : '管理者向け分析 ▾';
}

if (btnRolling) btnRolling.addEventListener('click', async () => {
    showStep(3);
    const loadingText = document.getElementById('loading-text');
    if (loadingText) loadingText.textContent = 'ローリングシミュレーション計算中...';

    const baseDate = document.getElementById('base-date').value;
    const days = num('rolling-days', 30, 1, 90);

    try {
        const res = await fetch('/api/rolling', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ base_date: baseDate, days: days })
        });
        const data = await res.json();
        if (res.ok) { renderAdminRolling(data); showStep(4); }
        else { alert('エラー: ' + data.error); showStep(4); }
    } catch(e) { alert('通信エラー'); showStep(4); }
});

if (btnScenario) btnScenario.addEventListener('click', async () => {
    showStep(3);
    const loadingText = document.getElementById('loading-text');
    if (loadingText) loadingText.textContent = 'シナリオ比較中...';

    const baseDate = document.getElementById('base-date').value;
    const mustWindow = num('must-window', 7, 0, 30);

    try {
        const res = await fetch('/api/scenarios', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ base_date: baseDate, must_ship_window_days: mustWindow })
        });
        const data = await res.json();
        if (res.ok) { renderAdminScenarios(data); showStep(4); }
        else { alert('エラー: ' + data.error); showStep(4); }
    } catch(e) { alert('通信エラー'); showStep(4); }
});

function renderAdminRolling(data) {
    // Minimal dashboard for rolling
    currentContainersData = [];
    document.getElementById('kpi-containers').textContent = data.total_containers;
    document.getElementById('kpi-containers-delta').textContent = `${data.days}日間`;
    document.getElementById('kpi-containers-delta').className = 'kpi-delta neutral';
    document.getElementById('kpi-alerts').textContent = data.total_alert_containers;
    document.getElementById('kpi-card-alerts').classList.toggle('has-alert', data.total_alert_containers > 0);
    document.getElementById('kpi-fillrate').textContent = data.avg_volume_rate;
    document.getElementById('kpi-fillrate-delta').textContent = `空き埋め ${data.total_pulls}件`;
    document.getElementById('kpi-fillrate-delta').className = 'kpi-delta good';

    const sl = document.getElementById('summary-line');
    sl.innerHTML = `<strong>${esc(data.start_date)} 〜 ${esc(data.end_date)}</strong> / 出荷 <strong>${data.total_shipped}</strong>件 / 週平均 <strong>${data.weekly_container_rate}</strong>本`;

    const grid = document.getElementById('container-grid');
    grid.innerHTML = '';
    const active = data.daily_results.filter(d => d.containers > 0 || d.must_ship > 0);
    (active.length ? active : data.daily_results.slice(0, 7)).forEach(d => {
        const isAlert = d.alerts > 0;
        const card = document.createElement('div');
        card.className = `c-card ${isAlert ? 'alert' : d.pulls > 0 ? 'warn' : 'ok'}`;
        card.innerHTML = `
            <div class="c-head">
                <div class="c-num">${esc(d.date)}</div>
                <span class="c-badge ${isAlert ? 'alert' : 'ok'}">${d.containers}本</span>
            </div>
            <div class="fill-bar">
                <div class="bar-head"><span class="bar-label">平均積載率</span><span class="bar-val">${d.avg_volume_rate}%</span></div>
                <div class="fill-track"><div class="fill-bar-inner ${d.avg_volume_rate >= 80 ? 'ok' : 'alert'}" style="width:${Math.min(100, d.avg_volume_rate)}%"></div></div>
            </div>
            <div class="c-stats">
                <span>出荷 <strong>${d.shipped}</strong></span>
                <span>空き埋め <strong>${d.pulls}</strong></span>
                <span>赤字 <strong>${d.alerts}</strong></span>
            </div>`;
        grid.appendChild(card);
    });

    // Show rolling export
    const rollingExport = document.getElementById('btn-export-rolling');
    if (rollingExport) rollingExport.style.display = '';
    const mainExport = document.getElementById('btn-export');
    if (mainExport) mainExport.style.display = 'none';
}

function renderAdminScenarios(data) {
    currentContainersData = [];
    const scenarios = data.scenarios || [];
    const rec = data.recommended || {};

    document.getElementById('kpi-containers').textContent = scenarios.length;
    document.getElementById('kpi-containers-delta').textContent = 'シナリオ数';
    document.getElementById('kpi-containers-delta').className = 'kpi-delta neutral';
    document.getElementById('kpi-alerts').textContent = rec.alert_containers ?? 0;
    document.getElementById('kpi-card-alerts').classList.toggle('has-alert', (rec.alert_containers ?? 0) > 0);
    document.getElementById('kpi-fillrate').textContent = rec.avg_volume_rate ?? 0;
    document.getElementById('kpi-fillrate-delta').textContent = `推奨: ${rec.must_ship_window_days ?? '-'}日`;
    document.getElementById('kpi-fillrate-delta').className = 'kpi-delta good';

    const sl = document.getElementById('summary-line');
    sl.innerHTML = `<strong>${esc(data.base_date)}</strong> 基準 / 推奨は <strong>${rec.must_ship_window_days ?? '-'}日</strong>先読み`;

    const grid = document.getElementById('container-grid');
    grid.innerHTML = '';
    scenarios.forEach(s => {
        const isRec = s.recommended;
        const card = document.createElement('div');
        card.className = `c-card ${isRec ? 'ok' : s.alert_containers > 0 ? 'alert' : 'warn'}`;
        card.innerHTML = `
            <div class="c-head">
                <div class="c-num">${s.must_ship_window_days}日先読み</div>
                <span class="c-badge ${isRec ? 'ok' : 'warn'}">${isRec ? '推奨' : '比較'}</span>
            </div>
            <div class="fill-bar">
                <div class="bar-head"><span class="bar-label">平均積載率</span><span class="bar-val">${s.avg_volume_rate}%</span></div>
                <div class="fill-track"><div class="fill-bar-inner ${s.avg_volume_rate >= 80 ? 'ok' : 'alert'}" style="width:${Math.min(100, s.avg_volume_rate)}%"></div></div>
            </div>
            <div class="c-stats">
                <span>コンテナ <strong>${s.container_count}</strong></span>
                <span>要確認 <strong>${s.alert_containers}</strong></span>
                <span>空き埋め <strong>${s.total_pulls}</strong></span>
            </div>`;
        grid.appendChild(card);
    });

    const mainExport = document.getElementById('btn-export');
    if (mainExport) { mainExport.style.display = ''; mainExport.textContent = '📋 シナリオ比較を出力'; mainExport.onclick = () => { window.location.href = '/api/export_scenarios'; }; }
    const rollingExport = document.getElementById('btn-export-rolling');
    if (rollingExport) rollingExport.style.display = 'none';
}

// =====================
// 3D Visualization (Three.js)
// =====================
let scene, camera, renderer, controls;
let animId;
let interactableMeshes = [];
let raycaster = new THREE.Raycaster();
let mouse = new THREE.Vector2();

function init3D() {
    if (renderer) return;
    const container = document.getElementById('3d-container');
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0f172a);

    camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 1000);
    camera.position.set(15, 10, 15);

    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;

    window.addEventListener('resize', () => {
        const modal = document.getElementById('modal-3d');
        if (modal.classList.contains('visible')) {
            camera.aspect = container.clientWidth / container.clientHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(container.clientWidth, container.clientHeight);
        }
    });

    container.addEventListener('mousemove', (event) => {
        const rect = container.getBoundingClientRect();
        mouse.x = ((event.clientX - rect.left) / container.clientWidth) * 2 - 1;
        mouse.y = -((event.clientY - rect.top) / container.clientHeight) * 2 + 1;

        raycaster.setFromCamera(mouse, camera);
        const intersects = raycaster.intersectObjects(interactableMeshes);
        const tooltip = document.getElementById('3d-tooltip');

        if (intersects.length > 0) {
            const item = intersects[0].object.userData.item;
            tooltip.style.display = 'block';
            tooltip.style.left = (event.clientX - rect.left + 15) + 'px';
            tooltip.style.top = (event.clientY - rect.top + 15) + 'px';

            let extra = '';
            if (item.status_msg && item.status_msg.includes('前倒し')) extra = `<br><span style="color:#10b981;">空き埋め補填</span>`;
            else if (item.is_force_ship) extra = `<br><span style="color:#ef4444;">強制出荷</span>`;

            tooltip.innerHTML = `<strong>${esc(item.name)}</strong><br>
                <span style="color:#94a3b8;">L${item.l} × W${item.w} × H${item.h} mm</span>${extra}`;
        } else {
            tooltip.style.display = 'none';
        }
    });

    animate();
}

function animate() {
    animId = requestAnimationFrame(animate);
    if (controls) controls.update();
    if (renderer && scene && camera) renderer.render(scene, camera);
}

function close3D() {
    document.getElementById('modal-3d').classList.remove('visible');
}

function open3D(containerId) {
    document.getElementById('modal-3d').classList.add('visible');
    const cData = currentContainersData.find(c => c.id === containerId);
    document.getElementById('modal-title').textContent = cData
        ? `${cData.display_order ?? ''}本目の3Dレイアウト`
        : containerId;

    setTimeout(() => {
        init3D();
        while (scene.children.length > 0) scene.remove(scene.children[0]);
        interactableMeshes = [];
        document.getElementById('3d-tooltip').style.display = 'none';

        // Lights
        scene.add(new THREE.AmbientLight(0xffffff, 0.6));
        const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
        dirLight.position.set(10, 20, 10);
        scene.add(dirLight);

        // Container wireframe (mm -> m)
        const cW = 2.300, cH = 2.400, cL = 12.0;
        const geo = new THREE.BoxGeometry(cW + 0.004, cH + 0.004, cL + 0.004);
        const edges = new THREE.EdgesGeometry(geo);
        const line = new THREE.LineSegments(edges, new THREE.LineBasicMaterial({ color: 0x475569, linewidth: 2 }));
        line.position.set(cW / 2, cH / 2, cL / 2);
        scene.add(line);

        // Grid
        const gridHelper = new THREE.GridHelper(16, 16, 0x334155, 0x1e293b);
        gridHelper.position.set(cW / 2, 0, cL / 2);
        scene.add(gridHelper);

        if (!cData) return;

        // Stats overlay
        const statsOverlay = document.getElementById('3d-stats-overlay');
        statsOverlay.innerHTML = `
            <table>
                <tr><td class="lbl">内寸</td><td class="val">12.0 × 2.30 × 2.40 m</td></tr>
                <tr><td class="lbl">重量</td><td class="val">${Math.round(cData.weight_val).toLocaleString()} / ${cData.weight_max.toLocaleString()} kg</td></tr>
                <tr><td class="lbl">積載率</td><td class="val" style="color:#10b981;">${cData.volume_rate}%</td></tr>
            </table>`;

        // Items
        cData.items.forEach(item => {
            let iL = item.l / 1000, iW = item.w / 1000, iH = item.h / 1000;
            let pxL = item.rotated ? iW : iL;
            let pyL = item.rotated ? iL : iW;
            const sX = pyL, sY = iH, sZ = pxL;
            const x = item.y / 1000, y = item.z / 1000, z = item.x / 1000;

            const margin = 0.01;
            const vX = Math.max(0.01, sX - margin);
            const vY = Math.max(0.01, sY - margin);
            const vZ = Math.max(0.01, sZ - margin);

            const boxGeo = new THREE.BoxGeometry(vX, vY, vZ);
            let color = 0x3b82f6;
            if (item.is_force_ship) color = 0xef4444;
            else if (item.status_msg && item.status_msg.includes('前倒し')) color = 0x10b981;

            const material = new THREE.MeshStandardMaterial({
                color, roughness: 0.5, metalness: 0.1,
                polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1
            });
            const mesh = new THREE.Mesh(boxGeo, material);
            mesh.userData = { item };
            interactableMeshes.push(mesh);

            const boxEdges = new THREE.EdgesGeometry(boxGeo);
            mesh.add(new THREE.LineSegments(boxEdges, new THREE.LineBasicMaterial({ color: 0x1e293b, linewidth: 2 })));
            mesh.position.set(x + sX / 2, y + sY / 2, z + sZ / 2);
            scene.add(mesh);
        });

        // CG marker
        const cgGeo = new THREE.SphereGeometry(0.15, 16, 16);
        const cgMat = new THREE.MeshBasicMaterial({ color: 0xff0000, depthTest: false, transparent: true });
        const cgSphere = new THREE.Mesh(cgGeo, cgMat);
        const cgX = cData.cg_y / 1000, cgY = cData.cg_z / 1000, cgZ = cData.cg_x / 1000;
        cgSphere.position.set(cgX, cgY, cgZ);
        scene.add(cgSphere);

        // CG drop line
        const dropGeo = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(cgX, cgY, cgZ), new THREE.Vector3(cgX, 0, cgZ)
        ]);
        const dropLine = new THREE.Line(dropGeo, new THREE.LineDashedMaterial({ color: 0xff0000, dashSize: 0.1, gapSize: 0.1, depthTest: false, transparent: true }));
        dropLine.computeLineDistances();
        scene.add(dropLine);

        // Center line
        const clGeo = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(cW / 2, 0.01, 0), new THREE.Vector3(cW / 2, 0.01, cL)
        ]);
        const cl = new THREE.Line(clGeo, new THREE.LineDashedMaterial({ color: 0xff0000, dashSize: 0.4, gapSize: 0.2 }));
        cl.computeLineDistances();
        scene.add(cl);

        // Camera position
        camera.position.set(cW / 2, cH + 3, cL + 6);
        controls.target.set(cW / 2, cH / 2, cL / 2);
        controls.update();

        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    }, 50);
}
