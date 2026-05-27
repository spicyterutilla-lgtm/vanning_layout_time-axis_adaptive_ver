/* ============================================
   ISUZU Vanning Optimizer — Frontend Logic
   Dashboard-first, visual-first rewrite
   ============================================ */

// --- DOM refs ---
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const btnRun = document.getElementById('btn-run');

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

function applyPlanningContext(context) {
    const baseDateInput = document.getElementById('base-date');
    if (baseDateInput) {
        if (context?.recommended_base_date) baseDateInput.value = context.recommended_base_date;
        else baseDateInput.valueAsDate = new Date();
    }

    const box = document.getElementById('planning-context');
    if (!box) return;
    if (!context?.vessel_loading_date) {
        box.style.display = 'none';
        box.innerHTML = '';
        return;
    }
    box.style.display = 'grid';
    box.innerHTML = `
        <div class="planning-title">今回の船積計画</div>
        <div class="planning-stat"><span>情報受領</span><strong>${esc(context.cargo_information_date)}</strong></div>
        <div class="planning-stat"><span>レイアウト確定</span><strong>${esc(context.layout_confirmation_date)}</strong></div>
        <div class="planning-stat emphasis"><span>バンニング期間</span><strong>${esc(context.vanning_start_date)} - ${esc(context.vanning_end_date)}</strong></div>
        <div class="planning-stat"><span>船積日</span><strong>${esc(context.vessel_loading_date)}</strong></div>
    `;
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
            applyPlanningContext(data.simulation_context);
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
            applyPlanningContext(data.simulation_context);
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
    const messages = [];
    if (s.errors > 0) messages.push(`入力エラー除外 ${s.errors}件`);
    if (s.warnings > 0) messages.push(`確認対象 ${s.warnings}件`);
    bar.textContent = messages.join(' / ');
}

// =====================
// Optimize (Single Day)
// =====================
btnRun.addEventListener('click', async () => {
    showStep(3);
    const loadingText = document.getElementById('loading-text');
    const phases = ["データ構造を解析中...", "納入予定と積込期限を評価中...", "空き埋め候補を探索中...", "3D配置を計算中...", "結果を生成中..."];
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

    // --- Worker-Friendly KPI Cards ---
    document.getElementById('kpi-containers').textContent = data.containers.length;
    const cDelta = document.getElementById('kpi-containers-delta');
    const optimization = data.optimization_summary || {};
    if (Number.isFinite(optimization.capacity_lower_bound)) {
        const gap = optimization.container_gap_to_lower_bound || 0;
        cDelta.textContent = `容量・重量下限 ${optimization.capacity_lower_bound}本との差 +${gap}本`;
        cDelta.className = `kpi-delta ${gap === 0 ? 'good' : 'neutral'}`;
    } else {
        cDelta.textContent = '';
        cDelta.className = 'kpi-delta';
    }

    const alertCount = data.alert_containers || 0;
    document.getElementById('kpi-alerts').textContent = alertCount;
    const alertCard = document.getElementById('kpi-card-alerts');
    alertCard.classList.toggle('has-alert', alertCount > 0);
    const alertDelta = document.getElementById('kpi-alerts-delta');
    const minimumAlerts = optimization.volume_only_minimum_alerts || 0;
    alertDelta.textContent = minimumAlerts > 0 ? `体積総量上の最低 ${minimumAlerts}本` : '';
    alertDelta.className = 'kpi-delta neutral';

    const avgVol = data.containers.length
        ? Math.round(data.containers.reduce((s, c) => s + c.volume_rate, 0) / data.containers.length * 10) / 10
        : 0;
    document.getElementById('kpi-fillrate').textContent = avgVol;
    const fDelta = document.getElementById('kpi-fillrate-delta');
    fDelta.textContent = '目標 80%以上';
    fDelta.className = 'kpi-delta neutral';

    // --- Summary Line ---
    const sl = document.getElementById('summary-line');

    let inventoryText = '';
    if (data.inventory_stats) {
        const stats = data.inventory_stats;
        const lateArrivalText = stats.future_count > 0
            ? `<span class="badge alert">期限後納入予定 <strong>${stats.future_count}</strong>個</span>`
            : '';
        inventoryText = `
            <div class="summary-row">
                <span class="badge info">📦 全荷物 <strong>${stats.total_valid_items}</strong>個</span>
                <span class="badge danger">🚨 今回積込対象 <strong>${stats.must_ship_count}</strong>個</span>
                <span class="badge success">📅 追加積載候補 <strong>${stats.forwardable_count}</strong>個</span>
                ${lateArrivalText}
            </div>
        `;
    }

    const pullText = (data.total_pulls > 0) ? `<span class="badge warning">✨ 隙間埋め <strong>${data.total_pulls}</strong>個</span>` : '';
    const improvedAlerts = data.layout_improvements?.improved_alert_containers || 0;
    const rearrangeText = improvedAlerts > 0
        ? `<span class="badge success">🔄 再配置で改善 <strong>${improvedAlerts}</strong>本</span>`
        : '';
    const strategyText = optimization.strategy_trial_count > 1
        ? (optimization.deep_strategy_trial_count > 0
            ? `<span class="badge info">候補 <strong>${optimization.strategy_trial_count}</strong>案 / 深掘り <strong>${optimization.deep_strategy_trial_count}</strong>案</span>`
            : `<span class="badge info">配置候補 <strong>${optimization.strategy_trial_count}</strong>案を比較</span>`)
        : '';
    const geometryText = optimization.geometry_valid
        ? `<span class="badge success">3D配置確認済み</span>`
        : `<span class="badge alert">3D配置確認 <strong>${optimization.geometry_warning_count || 0}</strong>件</span>`;
    const alertHtml = alertCount > 0
        ? `<span class="badge alert">⚠️ スカスカ注意 <strong>${alertCount}</strong>本</span>`
        : `<span class="badge ok">✅ 全本80%以上クリア</span>`;

    sl.innerHTML = `
        ${inventoryText}
        <div class="summary-row" style="margin-top: 0.75rem;">
            <span class="badge primary">🚚 <strong>${data.containers.length}</strong>本で確定</span>
            ${pullText}
            ${rearrangeText}
            ${strategyText}
            ${geometryText}
            ${alertHtml}
        </div>
    `;

    // --- Container Grid ---
    const grid = document.getElementById('container-grid');
    grid.innerHTML = '';

    data.containers.forEach(c => {
        const isAlert = c.is_alert;
        const pullCount = c.items.filter(i => i.status_msg && i.status_msg.includes('前倒し')).length;
        const isPulled = pullCount > 0 && !isAlert;

        let statusClass, badgeClass, badgeText;
        if (isAlert) {
            statusClass = 'alert'; badgeClass = 'alert'; badgeText = 'スカスカ注意';
        } else if (isPulled) {
            statusClass = 'warn'; badgeClass = 'warn'; badgeText = '空き埋め済み';
        } else {
            statusClass = 'ok'; badgeClass = 'ok'; badgeText = '出荷OK';
        }

        const volRate = Number(c.volume_rate).toFixed(1);
        const fillClass = c.volume_rate >= 80 ? 'ok' : c.volume_rate >= 60 ? 'warn' : 'alert';

        let reasonHtml = '';
        if (isAlert && c.alert_reason_title) {
            reasonHtml = `<div class="c-reason force">${esc(c.alert_reason_title)}</div>`;
        } else if (isPulled) {
            reasonHtml = `<div class="c-reason pull">空きスペース埋め ${pullCount}個で80%達成</div>`;
        }

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
                <div class="c-num"><span class="container-icon">📦</span> ${c.display_order ?? ''}本目</div>
                <span class="c-badge ${badgeClass}">${badgeText}</span>
            </div>

            <div class="container-graphic">
                <div class="container-body">
                    <div class="container-fill ${fillClass}" style="width:${Math.min(100, volRate)}%"></div>
                    <div class="container-text">${volRate}% 埋まっています</div>
                </div>
            </div>

            <div class="c-stats-grid">
                <div class="stat-box">
                    <div class="stat-lbl">体積充填率</div>
                    <div class="stat-val ${fillClass}">${volRate}<small>%</small></div>
                </div>
                <div class="stat-box">
                    <div class="stat-lbl">総重量</div>
                    <div class="stat-val">${Math.round(c.weight_val).toLocaleString()}<small>kg</small></div>
                </div>
                <div class="stat-box">
                    <div class="stat-lbl">荷物数</div>
                    <div class="stat-val">${c.items.length}<small>個</small></div>
                </div>
            </div>

            ${reasonHtml}

            <div class="c-footer">
                <button class="btn-3d" onclick="open3D('${c.id}')">📦 3Dで中身を見る</button>
            </div>

            <details class="c-details">
                <summary>荷物一覧 (${c.items.length}件)</summary>
                <div style="margin-top:0.5rem;">${itemsHtml}</div>
            </details>
        `;

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
    controls.enableDamping = false;

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

        // メモリリーク（かくつき）防止のため、古いオブジェクトを完全に破棄
        if (scene) {
            scene.traverse(child => {
                if (child.geometry) child.geometry.dispose();
                if (child.material) {
                    if (Array.isArray(child.material)) child.material.forEach(m => m.dispose());
                    else child.material.dispose();
                }
            });
            while (scene.children.length > 0) {
                scene.remove(scene.children[0]);
            }
        }

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
                <tr><td class="lbl">体積充填率</td><td class="val" style="color:#10b981;">${Number(cData.volume_rate).toFixed(1)}%</td></tr>
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
