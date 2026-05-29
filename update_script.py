import re

with open('static/script.js', 'r', encoding='utf-8') as f:
    js_content = f.read()

# We will define a completely new JS based on the existing one, merging logic from ui_test.html.
new_js = """/* ============================================
   ISUZU Vanning Optimizer — Frontend Logic
   ============================================ */

// --- DOM refs ---
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const btnRun = document.getElementById('btn-run');
const inputPanel = document.getElementById('input-panel');
const storyDashboard = document.getElementById('story-dashboard');
const scheduleTimeline = document.getElementById('schedule-timeline');
const stepPanel = document.getElementById('step-panel');
const containerGrid = document.getElementById('container-grid');

// --- State ---
let currentContainersData = [];
let isStoryCollapsed = false;

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
    
    if (context?.vessel_loading_date) {
        document.getElementById('tl-date1').textContent = esc(context.cargo_information_date);
        document.getElementById('tl-date2').textContent = esc(context.layout_confirmation_date);
        document.getElementById('tl-date3').textContent = `${esc(context.vanning_start_date)} 〜 ${esc(context.vanning_end_date)}`;
        document.getElementById('tl-date4').textContent = esc(context.vessel_loading_date);
    }
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
            updateUploadStatus(data);
        }
    } catch(e) { console.error("Status error", e); }
});

// =====================
// File Upload
// =====================
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.style.borderColor = '#3b82f6'; dropZone.style.background = 'rgba(59, 130, 246, 0.05)'; });
dropZone.addEventListener('dragleave', () => { dropZone.style.borderColor = ''; dropZone.style.background = ''; });
dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.style.borderColor = ''; dropZone.style.background = '';
    if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', e => {
    if (e.target.files.length) uploadFile(e.target.files[0]);
});

async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    document.getElementById('upload-status').innerHTML = '<div class="upload-spinner" style="display:inline-block; margin-right:8px;"></div>データを読み込み中...';

    try {
        const res = await fetch('/api/upload', { method: 'POST', body: formData });
        const data = await res.json();
        if (res.ok) {
            updateUploadStatus(data);
            document.getElementById('btn-run').classList.add('pulse-glow');
            setTimeout(() => document.getElementById('btn-run').classList.remove('pulse-glow'), 2000);
        } else {
            alert('エラー: ' + data.error);
            resetUpload();
        }
    } catch(e) {
        alert('通信エラー');
        resetUpload();
    }
}

function updateUploadStatus(data) {
    document.getElementById('drop-icon').textContent = '✅';
    document.getElementById('upload-status').innerHTML = `<strong style="color:var(--success);">読込完了: ${data.total_items}件</strong>`;
    document.getElementById('step1-total').textContent = data.total_items;
    applyPlanningContext(data.simulation_context);
}

function resetUpload() {
    document.getElementById('drop-icon').textContent = '🗂️';
    document.getElementById('upload-status').innerHTML = 'または、クリックして選択（.xlsx / .xls）';
}

// =====================
// Story Dashboard Controls
// =====================
function toggleStoryCollapse() {
    isStoryCollapsed = !isStoryCollapsed;
    if (isStoryCollapsed) {
        storyDashboard.classList.add('collapsed');
    } else {
        storyDashboard.classList.remove('collapsed');
    }
}

function updateStoryPanel(stepId, status, statusText) {
    const panel = document.getElementById(`story-${stepId}`);
    const statusEl = document.getElementById(`status-${stepId}`);
    
    panel.className = 'story-panel'; // reset
    if (status) panel.classList.add(status); // 'active' or 'completed'
    
    if (statusText) statusEl.textContent = statusText;
}

// =====================
// Optimize & Progressive Disclosure
// =====================
btnRun.addEventListener('click', async () => {
    // Hide input panel and show dashboard
    inputPanel.style.display = 'none';
    document.getElementById('welcome-screen').style.display = 'none';
    document.getElementById('reset-btn').style.display = 'flex';
    
    storyDashboard.style.display = 'flex';
    scheduleTimeline.style.display = 'flex';
    
    // START STEP 1: 現状
    updateStoryPanel('step1', 'active', '分析中...');
    document.getElementById('placeholder-step1').style.display = 'none';
    document.getElementById('content-step1').style.display = 'flex';
    
    setTimeout(() => document.getElementById('step1-data1').classList.add('show'), 300);
    setTimeout(() => document.getElementById('step1-data2').classList.add('show'), 1200);

    const baseDate = document.getElementById('base-date').value;
    
    let gaPollingInterval;
    let animLogs = [];
    
    // Move to Step 2 after a short delay
    setTimeout(() => {
        updateStoryPanel('step1', 'completed', '完了');
        updateStoryPanel('step2', 'active', '計算中');
        document.getElementById('placeholder-step2').style.display = 'none';
        document.getElementById('content-step2').style.display = 'flex';
        
        let logIndex = 0;
        const addLog = (msg) => {
            animLogs.push(msg);
            const logsContainer = document.getElementById('ai-logs');
            const logEl = document.createElement('div');
            logEl.className = 'log-line';
            logEl.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
            logsContainer.appendChild(logEl);
            setTimeout(() => logEl.classList.add('show'), 50);
            logsContainer.scrollTop = logsContainer.scrollHeight;
        };
        addLog('荷物の納入日と積込期限を評価中...');
        
        const phases = [
            '積込対象を分類中...',
            '空き埋め候補を探索中...',
            '3D配置を計算中...'
        ];
        
        let pi = 0;
        const phaseInterval = setInterval(() => {
            if (pi < phases.length) {
                addLog(phases[pi]);
                pi++;
            }
        }, 1000);
        
        const startTime = Date.now();
        const timerInterval = setInterval(() => {
            document.getElementById('loading-timer').textContent = `経過時間: ${Math.floor((Date.now() - startTime) / 1000)}秒`;
        }, 1000);

        // Polling GA status
        gaPollingInterval = setInterval(async () => {
            try {
                const res = await fetch('/api/ga_status');
                const st = await res.json();
                if (st && st.generation > 0 && !st.finished) {
                    addLog(`第${st.generation}世代を探索中（ベストスコア: ${st.best_score.toFixed(1)}点）...`);
                }
            } catch (e) {}
        }, 800);

        // Fetch Optimize
        fetch('/api/optimize', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ base_date: baseDate, optimization_mode: 'deep' })
        })
        .then(res => res.json())
        .then(data => {
            clearInterval(phaseInterval);
            clearInterval(timerInterval);
            clearInterval(gaPollingInterval);
            
            if (data.error) {
                alert('エラー: ' + data.error);
                return;
            }
            
            addLog('結果を検証中...');
            document.getElementById('ai-loading-text').textContent = '最適化完了！';
            document.querySelector('.ai-spinner').style.borderColor = 'var(--success)';
            document.querySelector('.ai-spinner').style.borderTopColor = 'var(--success)';
            document.querySelector('.ai-spinner').style.animation = 'none';

            // Fill Step 1 theoretical data if available from summary
            const optSum = data.optimization_summary || {};
            const minContainers = optSum.capacity_lower_bound || Math.ceil(data.containers.length * 0.8);
            const greedyContainers = optSum.greedy_containers || Math.ceil(minContainers * 1.3);
            
            document.getElementById('step1-theoretical').textContent = minContainers + '台';
            document.getElementById('step1-greedy').textContent = greedyContainers + '台';
            const diff = greedyContainers - minContainers;
            document.getElementById('step1-warning').textContent = `警告: 理論値より${diff}台オーバー`;
            
            // Move to Step 3
            setTimeout(() => {
                updateStoryPanel('step2', 'completed', '完了');
                updateStoryPanel('step3', 'active', '結果');
                
                document.getElementById('placeholder-step3').style.display = 'none';
                document.getElementById('content-step3').style.display = 'block';
                
                const finalCount = data.containers.length;
                const reduction = greedyContainers - finalCount;
                
                document.getElementById('step3-reduction').textContent = `${reduction > 0 ? reduction : 0}台 削減！`;
                document.getElementById('step3-final-containers').innerHTML = `${finalCount}<small>台</small>`;
                
                const avgVol = finalCount ? Math.round(data.containers.reduce((s, c) => s + c.volume_rate, 0) / finalCount * 10) / 10 : 0;
                document.getElementById('step3-final-efficiency').innerHTML = `${avgVol}<small>%</small>`;
                if (avgVol < 80) document.getElementById('step3-final-efficiency').className = 'stat-val alert';
                
                setTimeout(() => document.getElementById('step3-data1').classList.add('show'), 300);
                setTimeout(() => document.getElementById('step3-data2').classList.add('show'), 600);
                setTimeout(() => document.getElementById('step3-data3').classList.add('show'), 900);
                
                // Show container grid
                setTimeout(() => {
                    updateStoryPanel('step3', 'completed', '完了');
                    if (!isStoryCollapsed) toggleStoryCollapse(); // Auto collapse
                    
                    stepPanel.style.display = 'block';
                    renderDashboard(data);
                }, 2000);
                
            }, 1000);
            
        })
        .catch(e => {
            clearInterval(phaseInterval);
            clearInterval(timerInterval);
            clearInterval(gaPollingInterval);
            alert('通信エラー');
        });
        
    }, 1500);
});

// =====================
// Dashboard Rendering (Shutter effect)
// =====================
function renderDashboard(data) {
    currentContainersData = data.containers;
    containerGrid.innerHTML = '';

    data.containers.forEach((c, index) => {
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
        const urgentClass = c.items.some(i => i.is_force_ship) ? 'urgent' : '';

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
            if (i.status_msg && i.status_msg.includes('前倒し')) tagHtml = '<span class="item-tag pull" style="margin-left:auto;">空き埋め</span>';
            else if (i.is_force_ship) tagHtml = '<span class="item-tag force" style="margin-left:auto;">強制出荷</span>';
            
            itemsHtml += `
            <div class="drag-item ${tagHtml.includes('force') ? 'urgent' : ''} ${tagHtml.includes('pull') ? 'pull' : ''}">
                <div class="item-info">
                    <div class="item-title">${esc(i.name)}</div>
                    <div class="item-meta">
                        <span class="item-weight">${Math.round(i.weight)}kg</span>
                        <span>L${i.l} × W${i.w} × H${i.h} mm</span>
                    </div>
                </div>
                ${tagHtml}
            </div>`;
        });

        const card = document.createElement('div');
        // Initial state is opacity 0 for animation
        card.className = `c-card ${statusClass} ${urgentClass}`;
        card.style.opacity = '0';
        card.style.transform = 'translateY(-20px)';
        card.style.transition = 'all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275)';
        
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

            <details class="c-details" style="margin-top: 1rem; border-top: 1px solid #e2e8f0; padding-top: 0.5rem;">
                <summary style="font-weight: bold; color: var(--text-secondary); cursor: pointer; font-size: 0.9rem;">
                    荷物一覧を見る (${c.items.length}個)
                </summary>
                <div class="drag-list" style="margin-top:0.5rem; max-height:200px;">
                    ${itemsHtml}
                </div>
            </details>
        `;

        containerGrid.appendChild(card);
        
        // Shutter animation
        setTimeout(() => {
            card.classList.add('deployed');
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
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
// 3D Visualization (Three.js) - Unchanged
// =====================
"""

with open('static/script.js', 'r', encoding='utf-8') as f:
    js_content = f.read()

# We extract the 3D part from the original script and append it
marker = "// =====================\n// 3D Visualization (Three.js)\n// ====================="
parts = js_content.split(marker)
if len(parts) > 1:
    new_js += parts[1]

with open('static/script.js', 'w', encoding='utf-8') as f:
    f.write(new_js)

print("Updated script.js successfully")
