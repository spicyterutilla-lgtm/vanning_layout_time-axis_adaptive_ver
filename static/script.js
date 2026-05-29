/* ============================================
   ISUZU Vanning Optimizer — Frontend Logic
   ui_test.html と同一の構造・アニメーションに対応
   ============================================ */

'use strict';

// =====================
// グローバル状態
// =====================
let currentContainersData = [];
let currentUnusedItems = [];
let removedItemIds = new Set(); // 手動編集時にコンテナから外した荷物のIDを管理

function esc(v) {
    return String(v ?? '').replace(/[&<>"']/g, c =>
        ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// =====================
// 初期化
// =====================
document.addEventListener('DOMContentLoaded', async () => {
    const bd = document.getElementById('base-date');
    const setToday = () => {
        if (!bd) return;
        const today = new Date();
        const yyyy = today.getFullYear();
        const mm = String(today.getMonth() + 1).padStart(2, '0');
        const dd = String(today.getDate()).padStart(2, '0');
        bd.value = `${yyyy}-${mm}-${dd}`;
    };
    
    setToday();
    document.getElementById('btn-today')?.addEventListener('click', setToday);

    try {
        const res = await fetch('/api/status');
        const d   = await res.json();
        if (d.has_data) applyUploadSuccess(d.total_items, d.simulation_context);
    } catch(e) { console.error('status error', e); }
});

// =====================
// ファイルアップロード
// =====================
const dropZone  = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => {
    e.preventDefault();
    dropZone.style.borderColor = '#3b82f6';
    dropZone.style.background  = 'rgba(59,130,246,0.05)';
});
dropZone.addEventListener('dragleave', () => {
    dropZone.style.borderColor = '';
    dropZone.style.background  = '';
});
dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.style.borderColor = '';
    dropZone.style.background  = '';
    if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', e => {
    if (e.target.files[0]) uploadFile(e.target.files[0]);
});

async function uploadFile(file) {
    document.getElementById('drop-icon').textContent   = '⏳';
    document.getElementById('upload-status').textContent = '読み込み中...';
    const fd = new FormData();
    fd.append('file', file);
    try {
        const res = await fetch('/api/upload', { method: 'POST', body: fd });
        const d   = await res.json();
        if (res.ok) {
            applyUploadSuccess(d.total_items, d.simulation_context, d.baseline_stats);
        } else {
            alert('エラー: ' + d.error);
            document.getElementById('drop-icon').textContent     = '🗂️';
            document.getElementById('upload-status').textContent = '読込完了: 待機中';
        }
    } catch(e) {
        alert('通信エラー');
        document.getElementById('drop-icon').textContent     = '🗂️';
        document.getElementById('upload-status').textContent = '読込完了: 待機中';
    }
}

function applyUploadSuccess(totalItems, ctx, baselineStats = null) {
    window.uploadedTotalItems = Number(totalItems);
    window.baselineStats = baselineStats || { total_volume_m3: 0, theoretical_min: 40, greedy_estimate: 55 };
    document.getElementById('drop-icon').textContent = '✅';
    document.getElementById('upload-status').innerHTML =
        `<strong style="color:var(--success);">読込完了: ${Number(totalItems).toLocaleString()}件</strong>`;
    if (ctx?.recommended_base_date) {
        const bd = document.getElementById('base-date');
        if (bd) bd.value = ctx.recommended_base_date;
    }
}

// =====================
// フィルター（ui_test.html と同一）
// =====================
function filterCards(type, btnElem) {
    document.querySelectorAll('.filter-btn').forEach(b => {
        b.classList.remove('active');
        b.style.background  = 'transparent';
        b.style.borderColor = '#cbd5e1';
        b.style.color       = '#64748b';
    });
    btnElem.classList.add('active');
    if (type === 'all')   { btnElem.style.background = 'var(--bg-primary)'; btnElem.style.borderColor = '#3b82f6';        btnElem.style.color = '#3b82f6'; }
    if (type === 'must-ship') { btnElem.style.background = '#fef2f2';           btnElem.style.borderColor = '#ef4444';        btnElem.style.color = '#dc2626'; }
    if (type === 'ok')    { btnElem.style.background = '#f0fdf4';           btnElem.style.borderColor = 'var(--success)'; btnElem.style.color = '#16a34a'; }
    if (type === 'delay') { btnElem.style.background = '#f8fafc';           btnElem.style.borderColor = '#94a3b8';        btnElem.style.color = '#64748b'; }

    document.querySelectorAll('.container-grid .c-card').forEach(card => {
        if      (type === 'all')   card.style.display = '';
        else if (type === 'must-ship') card.style.display = card.dataset.status === 'must-ship' ? '' : 'none';
        else if (type === 'ok')    card.style.display = card.dataset.status === 'ok'    ? '' : 'none';
        else if (type === 'delay') card.style.display = card.dataset.status === 'delay' ? '' : 'none';
    });
}

// =====================
// 折りたたみ（ui_test.html と同一）
// =====================
function toggleStoryCollapse() {
    document.getElementById('story-dashboard').classList.toggle('collapsed');
}

// =====================
// 最適化実行ボタン
// =====================
document.getElementById('btn-run').addEventListener('click', async () => {
    document.getElementById('welcome-screen').style.display    = 'none';
    document.getElementById('reset-btn').style.display         = 'flex';
    document.getElementById('story-dashboard').style.display   = 'flex';
    document.getElementById('schedule-timeline').style.display = 'grid';
    document.getElementById('workspace-layout').style.display  = 'grid';
    await sleep(100);
    await runStory();
});

// =====================
// ストーリーアニメーション＋API（ui_test.html の startStorySimulation と同構造）
// =====================
async function runStory() {
    const grid = document.getElementById('container-grid');
    grid.style.pointerEvents = 'none';

    // --- リセット ---
    [1,2,3].forEach(i => {
        document.getElementById('story-'+i).className        = 'story-panel';
        document.getElementById('content-'+i).style.display  = 'none';
        document.getElementById('placeholder-'+i).style.display = 'block';
        document.getElementById('status-'+i).innerText       = '待機中';
    });
    document.querySelectorAll('.decision-point').forEach(el => el.classList.remove('show'));
    document.getElementById('step1-data1').style.opacity = '0';
    document.getElementById('step1-data2').style.opacity = '0';
    grid.innerHTML = '';
    removedItemIds.clear();

    // ===== STEP 1 =====
    const p1 = document.getElementById('story-1');
    p1.classList.add('active');
    document.getElementById('status-1').innerText              = '解析中...';
    document.getElementById('placeholder-1').style.display     = 'none';
    document.getElementById('content-1').style.display         = 'block';

    const baseDate = document.getElementById('base-date').value;
    
    // 事前計算通信（0.1秒）
    let baselineData = null;
    try {
        const blRes = await fetch('/api/baseline', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ base_date: baseDate })
        });
        baselineData = await blRes.json();
    } catch(e) {
        console.error("Baseline API error", e);
    }

    const targetItems = baselineData ? baselineData.target_items_count : (window.uploadedTotalItems || 880);
    const stats = baselineData ? baselineData : (window.baselineStats || { total_volume_m3: 0, theoretical_min: 40, greedy_estimate: 55 });
    
    const step = targetItems / 10;
    for (let i = 0; i <= 10; i++) {
        document.getElementById('val-items').innerText = Math.round(i * step).toLocaleString();
        await sleep(40);
    }
    document.getElementById('val-volume').innerText = stats.total_volume_m3;
    await sleep(300);

    const theoryStep = stats.theoretical_min / 10;
    for (let i = 0; i <= 10; i++) {
        document.getElementById('val-theoretical').innerText = Math.round(i * theoryStep) + ' 台';
        await sleep(40);
    }
    document.getElementById('val-theoretical-note').style.display = 'none';
    document.getElementById('step1-data1').style.opacity = '1';
    await sleep(500);

    const greedyStep = stats.greedy_estimate / 10;
    for (let i = 0; i <= 10; i++) {
        document.getElementById('val-greedy').innerText = Math.round(i * greedyStep) + ' 台';
        await sleep(40);
    }
    document.getElementById('step1-data2').style.opacity = '1';
    await sleep(200);
    
    p1.classList.remove('active');
    p1.classList.add('completed');
    document.getElementById('status-1').innerText = '完了';

    // ===== STEP 2（API 呼び出し）=====
    await sleep(400);
    const p2 = document.getElementById('story-2');
    p2.classList.add('active');
    document.getElementById('status-2').innerText = '思考中...';

    // ui_test.html と同一のスピナー + テキスト
    document.getElementById('placeholder-2').innerHTML = `
        <div class="ai-loading-container">
            <div class="ai-spinner"></div>
            <div class="ai-loading-text" id="ai-loading-text">空間データを解析中...</div>
            <div id="ai-timer" style="margin-top:0.75rem; font-family:monospace; font-size:1.1rem; color:var(--text-secondary); font-weight:bold;">0.0s</div>
        </div>`;

    const aiTexts = [
        '空間データを解析中...',
        'デッドスペースの境界を計算中...',
        '3Dパズル配置シミュレーションを実行中...',
        '数万通りのパターンから最適解を探索中...',
        '局所最適を脱出し、さらなる高密度配置を計算中...',
        '最終的な積載プランを生成中...'
    ];
    let ti = 0;
    const textInterval = setInterval(() => {
        ti = (ti + 1) % aiTexts.length;
        const el = document.getElementById('ai-loading-text');
        if (el) { el.style.opacity = 0; setTimeout(() => { if(el) { el.innerText = aiTexts[ti]; el.style.opacity = 1; } }, 300); }
    }, 1600);

    // GA進捗ポーリング
    const gaInterval = setInterval(async () => {
        try {
            const r = await fetch('/api/ga_status');
            const st = await r.json();
            if (st?.generation > 0) {
                const el = document.getElementById('ai-loading-text');
                if (el) el.innerText = `第${st.generation}世代を探索中（スコア: ${st.best_score.toFixed(1)}）...`;
            }
        } catch(e) {}
    }, 800);

    const startMs = Date.now();
    const timeInterval = setInterval(() => {
        const el = document.getElementById('ai-timer');
        if (el) el.innerText = ((Date.now() - startMs) / 1000).toFixed(1) + 's';
    }, 100);

    // 実API呼び出し
    let apiData = null;
    try {
        const res = await fetch('/api/optimize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ base_date: baseDate, optimization_mode: 'deep' })
        });
        if (!res.ok) {
            let errText = await res.text();
            try {
                const parsed = JSON.parse(errText);
                if (parsed.error) errText = parsed.error;
            } catch (e) {}
            throw new Error(errText);
        }
        apiData = await res.json();
    } catch(e) {
        clearInterval(textInterval); clearInterval(gaInterval); clearInterval(timeInterval);
        alert('エラー: ' + e.message);
        return;
    }
    clearInterval(textInterval); clearInterval(gaInterval); clearInterval(timeInterval);
    if (apiData?.error) { alert('エラー: ' + apiData.error); return; }

    // ===== Step 1 の数値を実データで上書き（削除） =====
    // ※事前の /api/baseline で正確な対象件数と体積を取得しているため、ここでは上書きせず維持します
    const optSum     = apiData.optimization_summary || {};
    const finalCount = apiData.containers.length;
    const lowerBound = optSum.capacity_lower_bound || Math.ceil(finalCount * 0.75);
    // パネル1（読込と現状の課題）で表示したグリーディ予測値を基準にする
    const greedyEst  = (window.baselineStats && window.baselineStats.greedy_estimate) ? window.baselineStats.greedy_estimate : (optSum.greedy_container_count || Math.round(lowerBound * 1.35));
    const avgFill    = optSum.avg_volume_rate  ? Number(optSum.avg_volume_rate).toFixed(1)  : '-';
    
    // タイムラインの構築
    const bd2  = apiData.planning_conditions?.base_date || new Date().toISOString().slice(0,10);
    const baseD = new Date(bd2);
    document.getElementById('tl-date1').textContent = bd2;
    document.getElementById('tl-date2').textContent = new Date(baseD.getTime() +  7*86400000).toISOString().slice(0,10);
    document.getElementById('tl-date3').textContent =
        new Date(baseD.getTime() + 14*86400000).toISOString().slice(0,10) + ' ～ ' +
        new Date(baseD.getTime() + 19*86400000).toISOString().slice(0,10);
    document.getElementById('tl-date4').textContent = new Date(baseD.getTime() + 21*86400000).toISOString().slice(0,10);

    // スピナー → パイプライン（ui_test.html と同一タイミング）
    document.getElementById('placeholder-2').style.display = 'none';
    document.getElementById('content-2').style.display     = 'flex';
    document.getElementById('content-2').style.flexDirection = 'column';

    await sleep(300);
    document.getElementById('dp-1').classList.add('show');
    await sleep(600);
    document.getElementById('dp-2').classList.add('show');
    await sleep(800);
    document.getElementById('dp3-result').textContent =
        `隙間を極限まで減らし、全量を【${finalCount}台】に収めるプランが完成しました！`;
    document.getElementById('dp-3').classList.add('show');

    await sleep(500);
    p2.classList.remove('active');
    p2.classList.add('completed');
    document.getElementById('status-2').innerText = '完了';

    // ===== STEP 3 =====
    await sleep(400);
    const p3 = document.getElementById('story-3');
    p3.classList.add('active');
    document.getElementById('status-3').innerText              = '確定！';
    document.getElementById('placeholder-3').style.display    = 'none';
    document.getElementById('content-3').style.display        = 'block';

    const reduction = greedyEst - finalCount;
    document.getElementById('r3-greedy-count').textContent   = greedyEst + '台';
    document.getElementById('r3-final-count').innerHTML      = `${finalCount}<span style="font-size:0.9rem; margin-left:2px;">台</span>`;
    document.getElementById('r3-reduction').textContent      = reduction > 0 ? `${reduction}台削減` : '最適済';
    document.getElementById('r3-final-rate').innerHTML       = `${avgFill}<span style="font-size:0.9rem; margin-left:2px;">%</span>`;
    document.getElementById('r3-final-rate').style.color     = parseFloat(avgFill) >= 80 ? 'var(--success)' : '#ef4444';
    document.getElementById('r3-rate-label').textContent     = parseFloat(avgFill) >= 80 ? '高密度積載' : '要改善';
    document.getElementById('r3-rate-label').style.color     = parseFloat(avgFill) >= 80 ? 'var(--success)' : '#ef4444';

    await sleep(800);
    p3.classList.remove('active');
    p3.classList.add('completed');
    document.getElementById('status-3').innerText = '完了';

    // ===== 折りたたみ → シャッター展開（ui_test.html と同一）=====
    await sleep(500);
    document.getElementById('story-dashboard').classList.add('collapsed');

    await sleep(300);
    await renderCards(apiData);
    grid.style.pointerEvents = 'auto';
}

// =====================
// コンテナカード生成（シャッター展開）
// =====================
async function renderCards(data) {
    currentContainersData = data.containers;
    currentUnusedItems = data.unused_items || [];
    const grid = document.getElementById('container-grid');
    grid.innerHTML = '';

    const mustShipCount = data.containers.filter(c => c.items.some(i => i.is_force_ship)).length;
    document.getElementById('filter-count-all').textContent   = data.containers.length;
    document.getElementById('filter-count-must-ship').textContent = mustShipCount;
    document.getElementById('filter-count-ok').textContent    = data.containers.length - mustShipCount;

    for (let index = 0; index < data.containers.length; index++) {
        const c = data.containers[index];
        const isAlert   = c.is_alert;
        const pullCount = c.items.filter(i => i.status_msg?.includes('前倒し')).length;
        const isUrgent  = c.items.some(i => i.is_force_ship);
        const isPulled  = pullCount > 0 && !isUrgent;

        const statusClass = isUrgent ? 'must-ship' : isPulled ? 'warn' : 'ok';
        const volRate     = Number(c.volume_rate).toFixed(1);
        const fillClass   = c.volume_rate >= 80 ? 'ok' : c.volume_rate >= 60 ? 'warn' : 'alert';
        const fillColor   = c.volume_rate < 80 && c.volume_rate < 60 ? 'color:#ef4444;' : '';

        const badgeStyle = isUrgent
            ? 'background:#ef4444; color:white; border:none; white-space:nowrap; padding:4px 10px;'
            : 'white-space:nowrap;';
        const badgeClass = isUrgent ? '' : 'ok';
        const badgeText  = isUrgent ? '出荷必須（納期直近あり）'
                         : isPulled ? '✨ 出荷OK（前倒し適用）' : '出荷OK';

        // 最短納期
        const dues = c.items.map(i => i.due_date).filter(Boolean).sort();
        const dueInfo = dues.length
            ? `<span style="font-size:0.7rem; background:#f8fafc; color:#64748b; padding:2px 6px; border-radius:4px; margin-top:4px; white-space:nowrap;">納期: ${dues[0]}</span>`
            : '';


        // 荷物行
        let itemsHtml = '';
        c.items.forEach(i => {
            let tag = '';
            if (i.status_msg?.includes('前倒し')) tag = '<span class="item-tag pull" style="margin-left:auto;">空き埋め</span>';
            else if (i.is_force_ship)              tag = '<span class="item-tag force" style="margin-left:auto;">強制出荷</span>';
            const liClass = i.is_force_ship ? 'urgent' : i.status_msg?.includes('前倒し') ? 'pull' : '';
            itemsHtml += `
            <div class="drag-item ${liClass}">
                <div class="item-info">
                    <div class="item-title">${esc(i.name)}</div>
                    <div class="item-meta">
                        <span class="item-weight">${Math.round(i.weight)}kg</span>
                        <span>L${i.l} × W${i.w} × H${i.h} mm</span>
                    </div>
                </div>
                ${tag}
            </div>`;
        });

        const card = document.createElement('div');
        card.className  = `c-card ${statusClass}${isUrgent ? ' urgent' : ''}`;
        card.dataset.status = isUrgent ? 'must-ship' : 'ok';
        card.onclick = () => open3D(c.id);

        let reasonHtml = '';
        if (isAlert && c.alert_reason_title) {
            reasonHtml = `<div style="font-size:0.75rem; color:#ef4444; margin-top:6px; line-height:1.2; word-break:break-all;">${esc(c.alert_reason_title)}</div>`;
        } else if (isPulled) {
            reasonHtml = `<div style="font-size:0.75rem; color:var(--primary); margin-top:6px; line-height:1.2;">前倒し${pullCount}個追加</div>`;
        }

        card.innerHTML = `
            <div class="c-head">
                <div class="c-num">
                    <span style="font-weight:bold; white-space:nowrap; font-size:1.1rem; color:var(--text-primary);">${esc(c.id)}</span>
                    ${dueInfo}
                </div>
                <div style="display:flex; flex-direction:column; gap:6px; align-items:flex-end;">
                    <span class="c-badge ${badgeClass}" style="${badgeStyle}">${badgeText}</span>
                    ${reasonHtml}
                </div>
            </div>
            <div class="fill-bar-wrap">
                <div class="fill-bar-labels"><span>積載効率</span><span class="fill-pct" style="${fillColor}">${volRate}%</span></div>
                <div class="fill-bar-track">
                    <div class="fill-bar-fill ${fillClass}" style="width:${Math.min(100, volRate)}%"></div>
                    <div class="fill-bar-target"></div>
                </div>
            </div>
            <div class="c-stats-grid">
                <div class="stat-box"><div class="stat-lbl">積載効率</div><div class="stat-val ${fillClass}">${volRate}<small>%</small></div></div>
                <div class="stat-box"><div class="stat-lbl">総重量</div><div class="stat-val">${Math.round(c.weight_val || 0).toLocaleString()}<small>kg</small></div></div>
                <div class="stat-box"><div class="stat-lbl">荷物数</div><div class="stat-val">${c.items.length}<small>個</small></div></div>
            </div>
            <div style="margin-top:1rem; text-align:center; color:#64748b; font-size:0.85rem; font-weight:600;">
                👆 クリックして個別作業を開く
            </div>
        `;

        grid.appendChild(card);

        // シャッター（ui_test.html と同一 150ms 間隔）
        await sleep(150);
        card.classList.add('deployed');
    }
}

// =====================
// エクスポート
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
        if (modal.style.display === 'flex') {
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

        document.querySelectorAll('.drag-item').forEach(el => el.style.background = '');

        if (intersects.length > 0) {
            const item = intersects[0].object.userData.item;
            tooltip.style.display = 'block';
            tooltip.style.left = (event.clientX - rect.left + 15) + 'px';
            tooltip.style.top  = (event.clientY - rect.top  + 15) + 'px';

            let extra = '';
            if (item.status_msg?.includes('前倒し')) extra = `<br><span style="color:#10b981;">空き埋め補填</span>`;
            else if (item.is_force_ship)              extra = `<br><span style="color:#ef4444;">強制出荷</span>`;
            const dest = item.destination ? `<br><span style="color:#cbd5e1;">仕向け地: ${esc(item.destination)}</span>` : '';

            tooltip.innerHTML = `<strong>${esc(item.name)}</strong><br>
                <span style="color:#94a3b8;">L${item.l} × W${item.w} × H${item.h} mm</span>${dest}${extra}`;
                
            const listItem = document.getElementById('drag-item-' + item.id);
            if (listItem) {
                listItem.style.background = 'rgba(59,130,246,0.1)';
                if (listItem.scrollIntoViewIfNeeded) listItem.scrollIntoViewIfNeeded();
            }
        } else {
            tooltip.style.display = 'none';
        }
    });

    animate();
}

function highlightMesh(itemId) {
    const mesh = interactableMeshes.find(m => m.userData.item.id === itemId);
    if (mesh) mesh.material.emissive.setHex(0x3b82f6);
}
function unhighlightMesh(itemId) {
    const mesh = interactableMeshes.find(m => m.userData.item.id === itemId);
    if (mesh) mesh.material.emissive.setHex(0x000000);
}

function animate() {
    animId = requestAnimationFrame(animate);
    if (controls) controls.update();
    if (renderer && scene && camera) renderer.render(scene, camera);
}


window.useDestinationColor = false;

function close3D() {
    document.getElementById('modal-3d').style.display = 'none';
}

function resetCamera() {
    if (camera && controls) {
        const cW = 2.300, cH = 2.400, cL = 12.0;
        camera.position.set(cW / 2, cH + 3, cL + 6);
        controls.target.set(cW / 2, cH / 2, cL / 2);
        controls.update();
    }
}

let isTransparentMode = false;
function toggleTransparentMode() {
    isTransparentMode = !isTransparentMode;
    interactableMeshes.forEach(mesh => {
        mesh.material.transparent = true;
        mesh.material.opacity = isTransparentMode ? 0.3 : 1.0;
    });
    const btn = document.getElementById('btn-toggle-transparent');
    if (btn) btn.textContent = isTransparentMode ? '👁️ 透過解除' : '👁️ 透過モード';
}

document.getElementById('toggle-color-mode')?.addEventListener('click', (e) => {
    window.useDestinationColor = !window.useDestinationColor;
    e.target.textContent = window.useDestinationColor ? '🟦 通常の色分けに戻す' : '🎨 仕向け地で色分け';
    document.getElementById('color-legend-normal').style.display = window.useDestinationColor ? 'none' : 'flex';
    const containerId = document.getElementById('modal-title').getAttribute('data-c-id');
    if (containerId) open3D(containerId, true);
});

function open3D(containerId, preserveCamera = false) {
    if (!preserveCamera) {
        // 新規で開く場合はバックアップAPIを呼ぶ
        fetch('/api/manual_edit_start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ container_id: containerId })
        }).catch(e => console.error(e));
        isTransparentMode = false;
        const btn = document.getElementById('btn-toggle-transparent');
        if (btn) btn.textContent = '👁️ 透過モード';
    }

    document.getElementById('modal-3d').style.display = 'flex';
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
            while (scene.children.length > 0) scene.remove(scene.children[0]);
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

        const statsOverlay = document.getElementById('3d-stats-overlay');
        const volumeRateColor = cData.volume_rate >= 80 ? '#10b981' : '#ef4444';
        statsOverlay.innerHTML = `
            <table>
                <tr><td class="lbl">内寸</td><td class="val">12.0 × 2.30 × 2.40 m</td></tr>
                <tr><td class="lbl">重量</td><td class="val">${Math.round(cData.weight_val).toLocaleString()} / ${cData.weight_max.toLocaleString()} kg</td></tr>
                <tr><td class="lbl">充填率</td><td class="val" style="color:${volumeRateColor};">${Number(cData.volume_rate).toFixed(1)}%</td></tr>
            </table>`;

        const colorModeButton = document.getElementById('toggle-color-mode');
        const hasDestination  = cData.items.some(item => item.destination);
        if (colorModeButton) {
            colorModeButton.disabled = !hasDestination;
            colorModeButton.title    = hasDestination ? '仕向け地ごとに色を切り替えます' : 'このデータには仕向け地がありません';
        }

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
            
            let x = item.y / 1000, y = item.z / 1000, z = item.x / 1000;
            // 3D配置エラー（キャパオーバー）の場合、コンテナ外側に浮遊させる
            if (item.x == null) {
                x = (Math.random() * cW) * 0.8;
                y = cH + 0.5 + Math.random();
                z = (Math.random() * cL) * 0.8;
            }

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
                else if (item.status_msg?.includes('前倒し')) color = 0x10b981;
            }

            const material = new THREE.MeshStandardMaterial({ color, roughness: 0.5, metalness: 0.1, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
            if (item.x == null) material.transparent = true, material.opacity = 0.6;
            
            const mesh = new THREE.Mesh(boxGeo, material);
            mesh.userData = { item };
            interactableMeshes.push(mesh);

            const boxEdges = new THREE.EdgesGeometry(boxGeo);
            mesh.add(new THREE.LineSegments(boxEdges, new THREE.LineBasicMaterial({ color: (item.x == null) ? 0xef4444 : 0x1e293b, linewidth: 2 })));
            mesh.position.set(x + sX / 2, y + sY / 2, z + sZ / 2);
            scene.add(mesh);
        });

        const cgGeo    = new THREE.SphereGeometry(0.15, 16, 16);
        const cgMat    = new THREE.MeshBasicMaterial({ color: 0xff0000, depthTest: false, transparent: true });
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

        if (!preserveCamera) {
            camera.position.set(cW / 2, cH + 3, cL + 6);
            controls.target.set(cW / 2, cH / 2, cL / 2);
            controls.update();
        }

        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
        
        renderDragList(cData);
    }, 50);
}

// =====================
// サイドバーUI・手動調整
// =====================
function switchModalTab(tab) {
    document.getElementById('tab-packed').classList.remove('active');
    document.getElementById('tab-unpacked').classList.remove('active');
    document.getElementById('tab-removed').classList.remove('active');
    
    document.getElementById('tab-' + tab).classList.add('active');
    
    document.getElementById('packed-view').style.display = tab === 'packed' ? 'flex' : 'none';
    document.getElementById('unpacked-view').style.display = tab === 'unpacked' ? 'flex' : 'none';
    document.getElementById('removed-view').style.display = tab === 'removed' ? 'flex' : 'none';
}

function renderDragList(cData) {
    const listDiv = document.getElementById('modal-drag-list');
    listDiv.innerHTML = '';
    // 奥から手前（X座標が大きい順、あるいは0に近い順？コンテナの奥は x=0 付近。ThreeJS上は z=item.x/1000）
    // 通常の座標系は奥が0なので、xが小さいほど奥。
    const sortedItems = [...cData.items].sort((a,b) => (a.x || 0) - (b.x || 0)); 
    
    sortedItems.forEach(i => {
        const isPull = i.status_msg?.includes('前倒し');
        const isUrgent = i.is_force_ship;
        const liClass = isUrgent ? 'urgent' : isPull ? 'pull' : '';
        const errorStyle = (i.x == null) ? 'border-color:#ef4444; background:#fef2f2;' : '';
        
        let metaHtml = '';
        if (isUrgent && i.due_date) {
            metaHtml = `<span style="color:#ef4444; font-weight:bold;">納期: ${i.due_date}</span>`;
        } else if (isPull) {
            metaHtml = `<span style="color:#10b981;">空き埋め追加</span>`;
        } else if (i.due_date) {
            metaHtml = `<span>納期: ${i.due_date}</span>`;
        }
        
        const itemHtml = `
        <div class="drag-item ${liClass}" id="drag-item-${i.id}" style="${errorStyle}" draggable="true"
             ondragstart="handleReorderDragStart(event, '${i.id}')"
             ondragover="handleReorderDragOver(event)"
             ondrop="handleReorderDrop(event, '${cData.id}', '${i.id}')"
             onmouseenter="highlightMesh('${i.id}')" onmouseleave="unhighlightMesh('${i.id}')">
            <div class="item-info">
                <div class="item-title">${esc(i.name)}</div>
                <div class="item-meta">
                    <span class="item-weight">${Math.round(i.weight).toLocaleString()}kg</span>
                    ${metaHtml}
                </div>
            </div>
            <button class="btn-ghost" style="padding:4px 8px; font-size:0.75rem;" onclick="removeContainerItem('${cData.id}', '${i.id}')">外す</button>
        </div>`;
        listDiv.insertAdjacentHTML('beforeend', itemHtml);
    });

    const unpDiv = document.getElementById('modal-unpacked-list');
    const remDiv = document.getElementById('modal-removed-list');
    unpDiv.innerHTML = '';
    remDiv.innerHTML = '';
    
    let unpackedCount = 0;
    let removedCount = 0;
    
    currentUnusedItems.forEach(i => {
        let metaHtml = i.due_date ? `<span>納期: ${i.due_date}</span>` : '';
        if (i.is_force_ship && i.due_date) {
            metaHtml = `<span style="color:#ef4444; font-weight:bold;">納期: ${i.due_date}</span>`;
        }

        const itemHtml = `
        <div class="drag-item" style="cursor:pointer;" draggable="true" ondragstart="handleDragStart(event, '${cData.id}', '${i.id}')" onclick="addUnusedItem('${cData.id}', '${i.id}')">
            <div class="item-info">
                <div class="item-title">${esc(i.name)}</div>
                <div class="item-meta">
                    <span class="item-weight">${Math.round(i.weight).toLocaleString()}kg</span>
                    ${metaHtml}
                </div>
            </div>
            <button class="btn-ghost" style="padding:4px 8px; font-size:0.75rem; color:#3b82f6; border:1px solid #3b82f6;">追加</button>
        </div>`;
        
        if (removedItemIds.has(i.id)) {
            remDiv.insertAdjacentHTML('beforeend', itemHtml);
            removedCount++;
        } else {
            unpDiv.insertAdjacentHTML('beforeend', itemHtml);
            unpackedCount++;
        }
    });

    document.getElementById('tab-packed').textContent = `搭載済み (${cData.items.length})`;
    document.getElementById('tab-unpacked').textContent = `未積載 / 候補 (${unpackedCount})`;
    document.getElementById('tab-removed').textContent = `外した荷物 (${removedCount})`;
    
    const alertBanner = document.getElementById('modal-alert-banner');
    if (cData.is_overloaded) {
        alertBanner.style.display = 'block';
        document.getElementById('confirm-btn-mock').disabled = true;
        document.getElementById('confirm-btn-mock').style.opacity = '0.5';
    } else {
        alertBanner.style.display = 'none';
        document.getElementById('confirm-btn-mock').disabled = false;
        document.getElementById('confirm-btn-mock').style.opacity = '1';
    }
}

function updateUndoRedoButtons(data) {
    const undoBtn = document.getElementById('undo-btn');
    const redoBtn = document.getElementById('redo-btn');
    if (undoBtn) undoBtn.disabled = !data.can_undo;
    if (redoBtn) redoBtn.disabled = !data.can_redo;
}

function showErrorBanner(msg) {
    const banner = document.getElementById('modal-alert-banner');
    if (banner) {
        banner.style.display = 'block';
        banner.innerHTML = `⚠️ ${msg}`;
        setTimeout(() => {
            // オーバーロード状態なら元のメッセージに戻す
            const cData = currentContainersData.find(c => c.id === document.getElementById('modal-title').getAttribute('data-c-id'));
            if (cData && cData.is_overloaded) {
                banner.innerHTML = `⚠️ 容積オーバー - エラーを解消するまで確定できません`;
            } else {
                banner.style.display = 'none';
            }
        }, 4000);
    }
}

function showToastNotification(msg) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.style.background = 'rgba(15, 23, 42, 0.85)';
    toast.style.color = '#fff';
    toast.style.padding = '0.75rem 1rem';
    toast.style.borderRadius = '6px';
    toast.style.fontSize = '0.85rem';
    toast.style.fontWeight = 'bold';
    toast.style.boxShadow = '0 4px 6px -1px rgba(0,0,0,0.1)';
    toast.style.backdropFilter = 'blur(4px)';
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s, transform 0.3s';
    toast.style.transform = 'translateY(-10px)';
    toast.textContent = msg;
    container.appendChild(toast);
    
    // Animation in
    requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateY(0)';
    });
    
    // Animation out
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-10px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

async function removeContainerItem(containerId, itemId) {
    try {
        const itemObj = interactableMeshes.find(m => m.userData.item.id === itemId)?.userData.item;
        const itemName = itemObj ? itemObj.name : '荷物';

        const res = await fetch('/api/manual_edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ container_id: containerId, action: 'remove', item_id: itemId })
        });
        const data = await res.json();
        if (data.error) { showErrorBanner(data.error); return; }
        
        const cIndex = currentContainersData.findIndex(c => c.id === containerId);
        if (cIndex >= 0) currentContainersData[cIndex] = data.container;
        
        removedItemIds.add(itemId);
        
        if (itemObj && !currentUnusedItems.find(i => i.id === itemId)) {
            currentUnusedItems.push(itemObj);
        }
        
        updateUndoRedoButtons(data);
        open3D(containerId, true);
        showToastNotification(`${itemName} を外しました`);
    } catch(e) { console.error(e); }
}

async function addUnusedItem(containerId, itemId) {
    try {
        const res = await fetch('/api/manual_edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ container_id: containerId, action: 'add', item_id: itemId })
        });
        const data = await res.json();
        if (data.error) { 
            // 失敗時は対象アイテムをフラッシュし、ポップアップ警告を出す
            const el = document.getElementById('drag-item-' + itemId);
            if (el) {
                el.style.transition = 'background-color 0.2s';
                el.style.backgroundColor = '#fee2e2';
                setTimeout(() => el.style.backgroundColor = '', 500);
            }
            alert(`【追加失敗】\n${data.error}`);
            showErrorBanner(data.error); 
            return; 
        }
        
        const cIndex = currentContainersData.findIndex(c => c.id === containerId);
        if (cIndex >= 0) currentContainersData[cIndex] = data.container;
        
        currentUnusedItems = currentUnusedItems.filter(i => i.id !== itemId);
        removedItemIds.delete(itemId);
        
        updateUndoRedoButtons(data);
        switchModalTab('packed');
        open3D(containerId, true);

        // どこに追加されたか分かりやすくするため、3D上でハイライトする
        setTimeout(() => {
            highlightMesh(itemId);
            // 3秒後にハイライト解除
            setTimeout(() => {
                unhighlightMesh(itemId);
            }, 3000);
        }, 300); // 描画待ち
    } catch(e) { console.error(e); }
}

// リスト内のD&D並び替え
let draggedReorderItemId = null;
function handleReorderDragStart(e, itemId) {
    draggedReorderItemId = itemId;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', itemId);
}
function handleReorderDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
}
async function handleReorderDrop(e, containerId, targetItemId) {
    e.preventDefault();
    if (!draggedReorderItemId || draggedReorderItemId === targetItemId) return;
    
    // 現在のリスト順序を取得
    const listDiv = document.getElementById('modal-drag-list');
    let currentIds = Array.from(listDiv.children).map(el => el.id.replace('drag-item-', ''));
    
    // 配列の要素を移動
    const fromIndex = currentIds.indexOf(draggedReorderItemId);
    const toIndex = currentIds.indexOf(targetItemId);
    if (fromIndex > -1 && toIndex > -1) {
        currentIds.splice(fromIndex, 1);
        currentIds.splice(toIndex, 0, draggedReorderItemId);
    }
    
    try {
        const res = await fetch('/api/manual_edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ container_id: containerId, action: 'reorder', items_order: currentIds })
        });
        const data = await res.json();
        if (data.error) {
            showErrorBanner(data.error);
            // エラー時は元の順序で再描画（バックエンドでロールバック済み）
        } else {
            const cIndex = currentContainersData.findIndex(c => c.id === containerId);
            if (cIndex >= 0) currentContainersData[cIndex] = data.container;
            updateUndoRedoButtons(data);
        }
        open3D(containerId, true);
    } catch(e) { console.error(e); }
}

async function undoManualEdit() {
    const containerId = document.getElementById('modal-title').getAttribute('data-c-id');
    try {
        const res = await fetch('/api/manual_edit_undo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ container_id: containerId })
        });
        const data = await res.json();
        if (!data.error) {
            const cIndex = currentContainersData.findIndex(c => c.id === containerId);
            if (cIndex >= 0) currentContainersData[cIndex] = data.container;
            if (data.unused_items) currentUnusedItems = data.unused_items;
            updateUndoRedoButtons(data);
            open3D(containerId, true);
        }
    } catch(e) { console.error(e); }
}

async function redoManualEdit() {
    const containerId = document.getElementById('modal-title').getAttribute('data-c-id');
    try {
        const res = await fetch('/api/manual_edit_redo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ container_id: containerId })
        });
        const data = await res.json();
        if (!data.error) {
            const cIndex = currentContainersData.findIndex(c => c.id === containerId);
            if (cIndex >= 0) currentContainersData[cIndex] = data.container;
            if (data.unused_items) currentUnusedItems = data.unused_items;
            updateUndoRedoButtons(data);
            open3D(containerId, true);
        }
    } catch(e) { console.error(e); }
}

async function clearManualEdits() {
    if (!confirm('手動での変更をすべて破棄して、最適化直後の状態に戻しますか？')) return;
    const containerId = document.getElementById('modal-title').getAttribute('data-c-id');
    try {
        const res = await fetch('/api/manual_edit_revert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ container_id: containerId })
        });
        const data = await res.json();
        if (!data.error) {
            const cIndex = currentContainersData.findIndex(c => c.id === containerId);
            if (cIndex >= 0) currentContainersData[cIndex] = data.container;
            if (data.unused_items) currentUnusedItems = data.unused_items;
            removedItemIds.clear(); // 外した荷物リストもリセット
            updateUndoRedoButtons({can_undo: false, can_redo: false});
            open3D(containerId, true);
        }
    } catch(e) { console.error(e); }
}

async function cancelManualEdit() {
    const containerId = document.getElementById('modal-title').getAttribute('data-c-id');
    if (!containerId) {
        close3D();
        return;
    }
    try {
        const res = await fetch('/api/manual_edit_revert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ container_id: containerId })
        });
        const data = await res.json();
        if (!data.error) {
            const cIndex = currentContainersData.findIndex(c => c.id === containerId);
            if (cIndex >= 0) currentContainersData[cIndex] = data.container;
            if (data.unused_items) currentUnusedItems = data.unused_items;
        }
    } catch(e) { console.error(e); }
    close3D();
}

function confirmManualEdit() {
    const containerId = document.getElementById('modal-title').getAttribute('data-c-id');
    if (!containerId) return;
    close3D();
    window.location.href = `/api/export_container?container_id=${encodeURIComponent(containerId)}`;
}
