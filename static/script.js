/* ============================================
   ISUZU Vanning Optimizer — Frontend Logic
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

function applyPlanningContext(context) {
    const baseDateInput = document.getElementById('base-date');
    if (baseDateInput) {
        if (context?.recommended_base_date) baseDateInput.value = context.recommended_base_date;
        else if (!baseDateInput.value) baseDateInput.valueAsDate = new Date();
    }

    const tl = document.getElementById('planning-timeline');
    if (!tl) return;
    if (!context?.vessel_loading_date) {
        tl.style.display = 'none';
        return;
    }
    tl.style.display = 'flex';
    tl.innerHTML = `
        <div class="timeline-phase today">
            <div class="phase-label">📌 情報受領（今日）</div>
            <div class="phase-date">${esc(context.cargo_information_date)}</div>
        </div>
        <div class="timeline-phase">
            <div class="phase-label">📐 レイアウト確定</div>
            <div class="phase-date">${esc(context.layout_confirmation_date)}</div>
        </div>
        <div class="timeline-phase vanning">
            <div class="phase-label">🏭 バンニング期間</div>
            <div class="phase-date">${esc(context.vanning_start_date)} 〜 ${esc(context.vanning_end_date)}</div>
        </div>
        <div class="timeline-phase">
            <div class="phase-label">🚢 船積日</div>
            <div class="phase-date">${esc(context.vessel_loading_date)}</div>
        </div>
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
    // Set today as default
    const baseDateInput = document.getElementById('base-date');
    if (baseDateInput) {
        const today = new Date();
        baseDateInput.valueAsDate = today;
    }

    // Today button
    document.getElementById('btn-today')?.addEventListener('click', () => {
        if (baseDateInput) baseDateInput.valueAsDate = new Date();
    });

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
    } catch(e) {
        alert('通信エラー');
        resetUpload();
    }
}

function resetUpload() {
    dropZone.innerHTML = '<div class="upload-icon">🗂️</div><p>ここにファイルをドラッグ＆ドロップ</p><p class="hint">または、クリックして選択（.xlsx / .xls）</p>';
}

function renderValidation(data) {
    const bar = document.getElementById('validation-bar');
    if (!bar) return;
    const s = data.validation_summary;
    if (!s || s.total === 0) { bar.style.display = 'none'; return; }
    bar.style.display = 'flex';
    bar.className = 'validation-bar';
    const messages = [];
    if (s.errors > 0) messages.push(`⚠ 入力エラー除外 ${s.errors}件`);
    if (s.warnings > 0) messages.push(`確認対象 ${s.warnings}件`);
    bar.textContent = messages.join(' / ');
}

// =====================
// Optimize
// =====================
btnRun.addEventListener('click', async () => {
    showStep(3);
    const loadingText = document.getElementById('loading-text');
    const loadingBar = document.getElementById('loading-bar');
    const timerElement = document.getElementById('loading-timer');
    if (timerElement) timerElement.textContent = '経過時間: 0秒';

    const phases = [
        '荷物の納入日と積込期限を評価中...',
        '積込対象を分類中...',
        '空き埋め候補を探索中...',
        '3D配置を計算中...',
        '遺伝的アルゴリズムで最適化中...',
        '結果を検証中...'
    ];
    let pi = 0;
    const interval = setInterval(() => {
        pi = (pi + 1) % phases.length;
        if (loadingText) loadingText.textContent = phases[pi];
    }, 700);

    // Progress bar animation (indeterminate)
    let progress = 0;
    const progressInterval = setInterval(() => {
        if (progress < 90) {
            progress += Math.random() * 3;
            if (loadingBar) loadingBar.style.width = Math.min(90, progress) + '%';
        }
    }, 400);

    const startTimeMs = Date.now();
    const timerInterval = setInterval(() => {
        if (timerElement) {
            timerElement.textContent = `経過時間: ${Math.floor((Date.now() - startTimeMs) / 1000)}秒`;
        }
    }, 1000);

    // GA status polling
    const gaPollingInterval = setInterval(async () => {
        try {
            const res = await fetch('/api/ga_status');
            const st = await res.json();
            if (st && st.generation > 0 && !st.finished) {
                if (loadingText) loadingText.textContent = `第${st.generation}世代を探索中（ベストスコア: ${st.best_score.toFixed(1)}点）...`;
            }
        } catch (e) {}
    }, 1000);

    const baseDate = document.getElementById('base-date').value;

    try {
        const res = await fetch('/api/optimize', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ base_date: baseDate, optimization_mode: 'deep' })
        });
        const data = await res.json();
        clearInterval(interval);
        clearInterval(progressInterval);
        clearInterval(timerInterval);
        clearInterval(gaPollingInterval);
        if (loadingBar) loadingBar.style.width = '100%';

        if (res.ok) { renderDashboard(data); showStep(4); }
        else { alert('エラー: ' + data.error); showStep(2); }
    } catch(e) {
        clearInterval(interval);
        clearInterval(progressInterval);
        clearInterval(timerInterval);
        clearInterval(gaPollingInterval);
        alert('通信エラー');
        showStep(2);
    }
});

// =====================
// Dashboard Rendering
// =====================
function renderDashboard(data) {
    currentContainersData = data.containers;

    const alertCount = data.alert_containers || 0;
    const containerCount = data.containers.length;
    const allOk = alertCount === 0;

    // --- Decision Banner ---
    const banner = document.getElementById('decision-banner');
    document.getElementById('decision-number').textContent = containerCount;
    banner.className = `decision-banner ${allOk ? 'all-ok' : ''}`;

    const verdict = document.getElementById('decision-verdict');
    if (allOk) {
        verdict.className = 'decision-verdict ok';
        verdict.innerHTML = '✅ 全コンテナ 目標積載効率（80%）クリア';
    } else {
        verdict.className = 'decision-verdict alert';
        verdict.innerHTML = `⚠ 目標未達 ${alertCount}台（要確認）`;
    }

    const optimization = data.optimization_summary || {};
    const metaLines = [];
    if (data.planning_conditions?.base_date) {
        metaLines.push(`情報受領日 <strong>${data.planning_conditions.base_date}</strong>`);
    }
    if (data.execution_time_seconds) {
        metaLines.push(`処理時間 <strong>${data.execution_time_seconds}秒</strong>`);
    }
    document.getElementById('decision-meta').innerHTML = metaLines.join('<br>');

    // --- KPI Cards ---
    document.getElementById('kpi-containers').textContent = containerCount;
    const cDelta = document.getElementById('kpi-containers-delta');
    if (Number.isFinite(optimization.capacity_lower_bound)) {
        const gap = optimization.container_gap_to_lower_bound || 0;
        cDelta.textContent = `理論上の最少台数 ${optimization.capacity_lower_bound}台 との差 +${gap}台`;
        cDelta.className = `kpi-delta ${gap === 0 ? 'good' : 'neutral'}`;
    } else {
        cDelta.textContent = '';
    }

    document.getElementById('kpi-alerts').textContent = alertCount;
    document.getElementById('kpi-card-alerts').classList.toggle('has-alert', alertCount > 0);
    const alertDelta = document.getElementById('kpi-alerts-delta');
    const minimumAlerts = optimization.volume_only_minimum_alerts || 0;
    alertDelta.textContent = minimumAlerts > 0 ? `荷物総量の都合上、最低 ${minimumAlerts}台は未達になります` : '';
    alertDelta.className = 'kpi-delta neutral';

    const avgVol = containerCount
        ? Math.round(data.containers.reduce((s, c) => s + c.volume_rate, 0) / containerCount * 10) / 10
        : 0;
    document.getElementById('kpi-fillrate').textContent = avgVol;
    const fDelta = document.getElementById('kpi-fillrate-delta');
    fDelta.textContent = avgVol >= 80 ? '目標 80% 達成 ✓' : '目標 80% 未達';
    fDelta.className = `kpi-delta ${avgVol >= 80 ? 'good' : 'bad'}`;

    // --- Compact Summary Bar ---
    const sb = document.getElementById('summary-bar');
    const stats = data.inventory_stats || {};
    const pullCount = data.total_pulls || 0;
    const parts = [];
    if (stats.must_ship_count) parts.push(`<span class="badge danger">必須の荷物（納期直近） <strong>${stats.must_ship_count}</strong>個</span>`);
    if (stats.forwardable_count) parts.push(`<span class="badge success">前倒し候補の荷物 <strong>${stats.forwardable_count}</strong>個</span>`);
    if (pullCount > 0) parts.push(`<span class="badge warning">✨ 前倒しで追加積載 <strong>${pullCount}</strong>個</span>`);
    if (stats.future_count > 0) parts.push(`<span class="badge alert">納入前のため次回回し <strong>${stats.future_count}</strong>個</span>`);
    if (optimization.geometry_valid) parts.push(`<span class="badge ok">3D配置 検証済み</span>`);
    sb.innerHTML = `<span class="summary-bar-label">内訳</span>${parts.join('')}`;

    // --- Container Grid ---
    const grid = document.getElementById('container-grid');
    grid.innerHTML = '';

    data.containers.forEach(c => {
        const isAlert = c.is_alert;
        const pullCount = c.items.filter(i => i.status_msg && i.status_msg.includes('前倒し')).length;
        const isPulled = pullCount > 0 && !isAlert;

        let statusClass, badgeClass, badgeText;
        if (isAlert) {
            statusClass = 'alert'; badgeClass = 'alert'; badgeText = '目標未達・要確認';
        } else if (isPulled) {
            statusClass = 'warn'; badgeClass = 'warn'; badgeText = '前倒しで空き埋め済';
        } else {
            statusClass = 'ok'; badgeClass = 'ok'; badgeText = '出荷可';
        }

        const volRate = Number(c.volume_rate).toFixed(1);
        const fillClass = c.volume_rate >= 80 ? 'ok' : c.volume_rate >= 60 ? 'warn' : 'alert';

        let reasonHtml = '';
        if (isAlert && c.alert_reason_title) {
            reasonHtml = `<div class="c-reason force">${esc(c.alert_reason_title)}</div>`;
        } else if (isPulled) {
            reasonHtml = `<div class="c-reason pull">空きスペース埋め ${pullCount}個で積載効率アップ</div>`;
        }

        let itemsHtml = '';
        c.items.forEach(i => {
            let tagHtml = '';
            if (i.status_msg && i.status_msg.includes('前倒し')) tagHtml = '<span class="item-tag pull">空き埋め</span>';
            else if (i.is_force_ship) tagHtml = '<span class="item-tag force">強制出荷</span>';
            const idsJson = JSON.stringify([i.id]).replace(/"/g, '&quot;');
            const isManual = i.is_manual_force_ship;
            const hintText = isManual ? '↩ クリックで強制解除' : '⚙ クリックで強制出荷設定';
            itemsHtml += `<div class="c-item-row" onclick="toggleOverride(${idsJson}, ${!isManual})">
                <span class="item-name">${esc(i.name)}</span>
                ${tagHtml}
                <span class="item-override-hint">${hintText}</span>
            </div>`;
        });

        const card = document.createElement('div');
        const filterStatus = isAlert ? 'alert' : 'ok';
        card.className = `c-card ${statusClass}`;
        card.setAttribute('data-filter-status', filterStatus);
        card.innerHTML = `
            <div class="c-head">
                <div class="c-num">${esc(c.id)}</div>
                <span class="c-badge ${badgeClass}">${badgeText}</span>
            </div>

            <div class="fill-bar-wrap">
                <div class="fill-bar-labels">
                    <span>積載効率</span>
                    <span class="fill-pct">${volRate}%</span>
                </div>
                <div class="fill-bar-track">
                    <div class="fill-bar-fill ${fillClass}" style="width:${Math.min(100, volRate)}%"></div>
                    <div class="fill-bar-target"></div>
                </div>
            </div>

            <div class="c-stats-grid">
                <div class="stat-box">
                    <div class="stat-lbl">積載効率</div>
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
                <button class="btn-3d" onclick="open3D('${c.id}')">📦 3Dレイアウトを確認 →</button>
            </div>

            <details class="c-details">
                <summary>荷物一覧を見る (${c.items.length}個)</summary>
                <div style="margin-top:0.5rem;">${itemsHtml}</div>
            </details>
        `;

        grid.appendChild(card);
    });

    // Update Filter counts
    const okCount = data.containers.length - alertCount;
    document.getElementById('filter-count-all').textContent = data.containers.length;
    document.getElementById('filter-count-alert').textContent = alertCount;
    document.getElementById('filter-count-ok').textContent = okCount;
    
    // Ensure filter bar is visible if there are containers
    const filterBar = document.getElementById('filter-bar');
    if (filterBar && data.containers.length > 0) {
        filterBar.style.display = 'flex';
        // Initialize filter bindings if not already done
        if (!filterBar.dataset.bound) {
            filterBar.dataset.bound = "true";
            const btns = filterBar.querySelectorAll('.filter-btn');
            btns.forEach(btn => {
                btn.addEventListener('click', () => {
                    // Update active state
                    btns.forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    // Apply filter
                    const filterVal = btn.getAttribute('data-filter');
                    const cards = document.querySelectorAll('.c-card');
                    cards.forEach(c => {
                        if (filterVal === 'all') {
                            c.style.display = '';
                        } else {
                            if (c.getAttribute('data-filter-status') === filterVal) {
                                c.style.display = '';
                            } else {
                                c.style.display = 'none';
                            }
                        }
                    });
                });
            });
        }
        // Force 'all' filter on initial render
        filterBar.querySelector('[data-filter="all"]').click();
    }
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
            const destination = item.destination ? `<br><span style="color:#cbd5e1;">仕向け地: ${esc(item.destination)}</span>` : '';

            tooltip.innerHTML = `<strong>${esc(item.name)}</strong><br>
                <span style="color:#94a3b8;">L${item.l} × W${item.w} × H${item.h} mm</span>${destination}${extra}`;
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

window.useDestinationColor = false;

function close3D() {
    document.getElementById('modal-3d').classList.remove('visible');
}

document.getElementById('toggle-color-mode')?.addEventListener('click', (e) => {
    window.useDestinationColor = !window.useDestinationColor;
    e.target.textContent = window.useDestinationColor ? '🟦 通常の色分けに戻す' : '🎨 仕向け地で色分け';
    document.getElementById('color-legend-normal').style.display = window.useDestinationColor ? 'none' : 'flex';
    const containerId = document.getElementById('modal-title').getAttribute('data-c-id');
    if (containerId) open3D(containerId, true);
});

function open3D(containerId, preserveCamera = false) {
    document.getElementById('modal-3d').classList.add('visible');
    const container = document.getElementById('3d-container');
    const cData = currentContainersData.find(c => c.id === containerId);

    const titleEl = document.getElementById('modal-title');
    titleEl.textContent = cData ? `${esc(containerId)} の3Dレイアウト` : containerId;
    titleEl.setAttribute('data-c-id', containerId);

    setTimeout(() => {
        if (!preserveCamera) init3D();

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

        scene.add(new THREE.AmbientLight(0xffffff, 0.6));
        const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
        dirLight.position.set(10, 20, 10);
        scene.add(dirLight);

        const cW = 2.300, cH = 2.400, cL = 12.0;
        const geo = new THREE.BoxGeometry(cW + 0.004, cH + 0.004, cL + 0.004);
        const edges = new THREE.EdgesGeometry(geo);
        const line = new THREE.LineSegments(edges, new THREE.LineBasicMaterial({ color: 0x475569, linewidth: 2 }));
        line.position.set(cW / 2, cH / 2, cL / 2);
        scene.add(line);

        const gridHelper = new THREE.GridHelper(16, 16, 0x334155, 0x1e293b);
        gridHelper.position.set(cW / 2, 0, cL / 2);
        scene.add(gridHelper);

        if (!cData) return;
        const colorModeButton = document.getElementById('toggle-color-mode');
        const hasDestination = cData.items.some(item => item.destination);
        if (colorModeButton) {
            colorModeButton.disabled = !hasDestination;
            colorModeButton.title = hasDestination ? '仕向け地ごとに色を切り替えます' : 'このデータには仕向け地がありません';
        }

        const statsOverlay = document.getElementById('3d-stats-overlay');
        const volumeRateColor = cData.volume_rate >= 80 ? '#10b981' : '#ef4444';
        statsOverlay.innerHTML = `
            <table>
                <tr><td class="lbl">内寸</td><td class="val">12.0 × 2.30 × 2.40 m</td></tr>
                <tr><td class="lbl">重量</td><td class="val">${Math.round(cData.weight_val).toLocaleString()} / ${cData.weight_max.toLocaleString()} kg</td></tr>
                <tr><td class="lbl">充填率</td><td class="val" style="color:${volumeRateColor};">${Number(cData.volume_rate).toFixed(1)}%</td></tr>
            </table>`;

        const getDestColor = (dest) => {
            if (!dest) return 0x94a3b8;
            let hash = 0;
            for (let i = 0; i < dest.length; i++) hash = dest.charCodeAt(i) + ((hash << 5) - hash);
            const color = new THREE.Color();
            color.setHSL((Math.abs(hash) % 360) / 360, 0.7, 0.5);
            return color.getHex();
        };

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

            if (window.useDestinationColor) {
                color = getDestColor(item.destination);
            } else {
                if (item.is_force_ship) color = 0xef4444;
                else if (item.status_msg && item.status_msg.includes('前倒し')) color = 0x10b981;
            }

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

        const cgGeo = new THREE.SphereGeometry(0.15, 16, 16);
        const cgMat = new THREE.MeshBasicMaterial({ color: 0xff0000, depthTest: false, transparent: true });
        const cgSphere = new THREE.Mesh(cgGeo, cgMat);
        const cgX = cData.cg_y / 1000, cgY = cData.cg_z / 1000, cgZ = cData.cg_x / 1000;
        cgSphere.position.set(cgX, cgY, cgZ);
        scene.add(cgSphere);

        const dropGeo = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(cgX, cgY, cgZ), new THREE.Vector3(cgX, 0, cgZ)
        ]);
        const dropLine = new THREE.Line(dropGeo, new THREE.LineDashedMaterial({ color: 0xff0000, dashSize: 0.1, gapSize: 0.1, depthTest: false, transparent: true }));
        dropLine.computeLineDistances();
        scene.add(dropLine);

        const clGeo = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(cW / 2, 0.01, 0), new THREE.Vector3(cW / 2, 0.01, cL)
        ]);
        const cl = new THREE.Line(clGeo, new THREE.LineDashedMaterial({ color: 0xff0000, dashSize: 0.4, gapSize: 0.2 }));
        cl.computeLineDistances();
        scene.add(cl);

        camera.position.set(cW / 2, cH + 3, cL + 6);
        controls.target.set(cW / 2, cH / 2, cL / 2);
        controls.update();

        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    }, 50);
}
