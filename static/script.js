const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const btnRun = document.getElementById('btn-run');
const btnRolling = document.getElementById('btn-rolling');
const btnScenario = document.getElementById('btn-scenario');
const btnSaveAssumptions = document.getElementById('btn-save-assumptions');

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }[char]));
}

function getBoundedNumber(id, fallback, min, max) {
    const input = document.getElementById(id);
    const parsed = Number.parseInt(input?.value, 10);
    const value = Number.isFinite(parsed) ? parsed : fallback;
    return Math.min(max, Math.max(min, value));
}

function formatPercent(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '-';
    const rounded = Math.round(numeric * 10) / 10;
    return `${Number.isInteger(rounded) ? rounded.toFixed(0) : rounded.toFixed(1)}%`;
}

function formatNumber(value, unit = '') {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '-';
    return `${numeric.toLocaleString()}${unit}`;
}

function setSummaryMetric(slot, label, unit = '件') {
    const labelEl = document.getElementById(`label-${slot}`);
    const unitEl = document.getElementById(`unit-${slot}`);
    if (labelEl) labelEl.innerText = label;
    if (unitEl) unitEl.innerText = unit;
}

function setSingleDayMetricLabels() {
    setSummaryMetric('containers', '確定コンテナ', '本');
    setSummaryMetric('pool', '保留プール送り', '件');
    setSummaryMetric('forwardable', '前倒し候補残', '件');
    setSummaryMetric('hold', '前倒し不可', '件');
    setSummaryMetric('future', '未到着', '件');
    setSummaryMetric('excluded', '入力除外', '件');
}

function setRollingMetricLabels() {
    setSummaryMetric('containers', '期間内コンテナ', '本');
    setSummaryMetric('pool', '期間後残', '件');
    setSummaryMetric('forwardable', '前倒し補填', '件');
    setSummaryMetric('hold', '期限到来/超過残', '件');
    setSummaryMetric('future', '未到着', '件');
    setSummaryMetric('excluded', '入力除外', '件');
}

function setScenarioMetricLabels() {
    setSummaryMetric('containers', '比較シナリオ', '件');
    setSummaryMetric('pool', '推奨先読み', '日');
    setSummaryMetric('forwardable', '最小赤字', '本');
    setSummaryMetric('hold', '最少コンテナ', '本');
    setSummaryMetric('future', '入力対象', '件');
    setSummaryMetric('excluded', '入力除外', '件');
}

function updateSampleDownloadLink() {
    const rows = getBoundedNumber('sample-rows', 200, 50, 3000);
    const seed = getBoundedNumber('sample-seed', 20260516, 1, 99999999);
    const link = document.getElementById('sample-download-link');
    if (link) link.href = `/api/download_template?rows=${rows}&seed=${seed}`;
}

async function loadAssumptions() {
    try {
        const res = await fetch('/api/assumptions');
        const data = await res.json();
        if (!res.ok) return;
        const early = Math.round((data.allow_early_ship_probability ?? 0) * 100);
        const separation = Math.round((data.separation_probability ?? 0) * 100);
        const earlyInput = document.getElementById('early-rate');
        const separationInput = document.getElementById('separation-rate');
        if (earlyInput) earlyInput.value = early;
        if (separationInput) separationInput.value = separation;
        const summary = document.getElementById('assumption-summary');
        if (summary) {
            const classText = Object.entries(data.class_weights || {}).map(([key, value]) => `${escapeHtml(key)}:${value}`).join(' / ');
            summary.innerHTML = `次に作る検証データ: 早めに積める荷物 ${early}% / 一緒に積めない指定 ${separation}% / 箱タイプの出方 ${classText}`;
        }
        updateSampleDownloadLink();
    } catch(e) {
        console.error('前提取得エラー', e);
    }
}

async function saveAssumptions() {
    const earlyRate = getBoundedNumber('early-rate', 86, 0, 100) / 100;
    const separationRate = getBoundedNumber('separation-rate', 7, 0, 100) / 100;
    try {
        const res = await fetch('/api/assumptions', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                allow_early_ship_probability: earlyRate,
                separation_probability: separationRate
            })
        });
        const data = await res.json();
        if (!res.ok) {
            alert('前提保存エラー: ' + data.error);
            return;
        }
        loadAssumptions();
    } catch(e) {
        alert('通信エラー');
    }
}

function renderValidationSummary(data) {
    const box = document.getElementById('validation-summary');
    if (!box || !data || !data.validation_summary) return;

    const summary = data.validation_summary;
    const issues = data.validation_issues || [];
    const readiness = data.readiness;
    if ((summary.total ?? 0) === 0 && !readiness) {
        box.style.display = 'none';
        box.innerHTML = '';
        return;
    }

    const issueList = issues.map(issue => {
        const label = issue.severity === 'error' ? '除外' : '注意';
        return `<div style="font-size:0.85rem; margin-top:0.25rem;">${label}: ${escapeHtml(issue.name)} - ${escapeHtml(issue.message)}</div>`;
    }).join('');
    const readinessRows = readiness?.checks
        ? readiness.checks
            .filter(row => !row.ready)
            .slice(0, 5)
            .map(row => `<div style="font-size:0.82rem; margin-top:0.2rem;">${escapeHtml(row.item)}: ${escapeHtml(row.status)} - ${escapeHtml(row.note)}</div>`)
            .join('')
        : '';
    const readinessHtml = readiness
        ? `
            <div style="font-weight:800; margin-top:${(summary.total ?? 0) > 0 ? '0.75rem' : '0'};">実務準備度 ${readiness.score}% / ${escapeHtml(readiness.risk_level)}</div>
            ${readinessRows}
        `
        : '';

    box.style.display = 'block';
    box.innerHTML = `
        <div style="font-weight:800; margin-bottom:0.25rem;">入力データチェック</div>
        <div>除外対象 ${summary.errors ?? 0}件 / 注意 ${summary.warnings ?? 0}件</div>
        ${issueList}
        ${readinessHtml}
    `;
}

function renderSimulationContext(context) {
    const box = document.getElementById('simulation-context');
    if (!box) return;
    if (!context) {
        box.style.display = 'none';
        box.innerHTML = '';
        return;
    }

    const seedText = context.seed ? ` / 再現用番号 ${escapeHtml(context.seed)}` : '';
    const generatedRowsText = context.generated_rows_setting
        ? `生成時の荷物数 ${formatNumber(context.generated_rows_setting, '件')}`
        : `読み込んだ荷物数 ${formatNumber(context.loaded_count, '件')}`;
    const dataType = context.is_generated
        ? '開示ケースリストをもとに作った検証データです。'
        : '読み込んだExcelから見たデータ状況です。';
    const dueRange = context.due_min && context.due_max
        ? `${escapeHtml(context.due_min)} 〜 ${escapeHtml(context.due_max)}`
        : '-';
    const earlyRateText = Number.isFinite(Number(context.configured_early_ship_rate))
        ? `設定 ${formatPercent(context.configured_early_ship_rate)} / 実データ ${formatPercent(context.early_ship_rate)}`
        : formatPercent(context.early_ship_rate);
    const separationRateText = Number.isFinite(Number(context.configured_separation_rate))
        ? `設定 ${formatPercent(context.configured_separation_rate)} / 実データ ${formatPercent(context.separation_rate)}`
        : formatPercent(context.separation_rate);

    const rows = [
        ['荷物の量', `${formatNumber(context.loaded_count, '件')}（${generatedRowsText}${seedText}）`],
        ['早めに積める荷物', `${earlyRateText}（赤字回避の補填候補になりやすい荷物）`],
        ['一緒に積めない指定', `${separationRateText}（混載注意などで組み合わせが制限される荷物）`],
        ['積み方の制約', `段積み不可 ${formatPercent(context.no_stack_rate)} / 床置き指定 ${formatPercent(context.floor_only_rate)}`],
        ['木箱期限あり', `${formatPercent(context.wood_deadline_rate)}（木箱期限を納期と同じように見る荷物）`],
        ['到着状況', `到着済み ${formatPercent(context.arrived_rate)} / 未到着 ${formatPercent(context.future_rate)}`],
        ['納期の範囲', dueRange],
        ['平均重量', formatNumber(context.avg_weight, 'kg')],
    ];
    const sourceRows = context.source_rows || [];
    const sourceHtml = sourceRows.length
        ? `
            <div style="margin-top:0.9rem; border-top:1px solid #e2e8f0; padding-top:0.75rem;">
                <div style="font-weight:800; color:#1e293b; margin-bottom:0.45rem;">根拠と仮定</div>
                <div style="display:grid; gap:0.35rem;">
                    ${sourceRows.map(row => {
                        const isAssumption = ['仮定', '補完'].some(word => String(row.status || '').includes(word));
                        return `
                            <div style="font-size:0.82rem; background:#fff; border:1px solid #e2e8f0; border-radius:6px; padding:0.55rem 0.65rem;">
                                <div style="display:flex; justify-content:space-between; gap:0.75rem; align-items:flex-start;">
                                    <div style="font-weight:800; color:#334155;">${escapeHtml(row.item)}</div>
                                    <div style="font-weight:800; color:${isAssumption ? '#b45309' : '#047857'}; white-space:nowrap;">${escapeHtml(row.status)}</div>
                                </div>
                                <div style="color:#64748b; margin-top:0.15rem;">${escapeHtml(row.note || row.basis || '')}</div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `
        : '';

    box.style.display = 'block';
    box.innerHTML = `
        <div style="font-weight:800; color:#1e293b; margin-bottom:0.35rem;">今回のデータの状況設定</div>
        <div style="font-size:0.86rem; color:#475569; margin-bottom:0.75rem;">${dataType} ${escapeHtml(context.summary_note || '')}</div>
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(230px, 1fr)); gap:0.6rem 1rem;">
            ${rows.map(([label, value]) => `
                <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:6px; padding:0.65rem 0.75rem;">
                    <div style="font-size:0.75rem; font-weight:800; color:#64748b;">${escapeHtml(label)}</div>
                    <div style="font-size:0.93rem; color:#1e293b; margin-top:0.15rem;">${value}</div>
                </div>
            `).join('')}
        </div>
        ${sourceHtml}
        <div style="font-size:0.8rem; color:#64748b; margin-top:0.75rem;">※ 重量・発生頻度・納期・制約は、先方回答が来たら差し替える仮定部分です。</div>
    `;
}

function formatDayDistance(days) {
    if (!Number.isFinite(days)) return '';
    if (days < 0) return `${Math.abs(days)}日超過`;
    if (days === 0) return '当日';
    return `あと${days}日`;
}

function renderRiskSummary(items, title) {
    const box = document.getElementById('risk-summary');
    if (!box) return;

    if (!items || items.length === 0) {
        box.style.display = 'none';
        box.innerHTML = '';
        return;
    }

    const rows = items.slice(0, 8).map(item => {
        const dueText = `納期 ${escapeHtml(item.due_date)} (${formatDayDistance(item.days_until_due)})`;
        const expText = item.expiration_date
            ? ` / 木箱 ${escapeHtml(item.expiration_date)} (${formatDayDistance(item.days_until_expiration)})`
            : '';
        const constraints = item.constraint_tags?.length
            ? ` / 制約 ${item.constraint_tags.map(escapeHtml).join('・')}`
            : '';
        const decisionText = item.decision_reason
            ? `<div style="font-size:0.82rem; color:#7c2d12; margin-top:0.2rem;">判断根拠: ${escapeHtml(item.decision_reason)}</div>`
            : '';
        return `
            <div style="padding:0.5rem 0; border-top:1px solid #fed7aa;">
                <div style="font-weight:800; color:#7c2d12;">${escapeHtml(item.name)}</div>
                <div style="font-size:0.85rem; color:#9a3412;">${escapeHtml(item.reason)} / ${dueText}${expText} / 優先度 ${escapeHtml(item.priority)}${constraints}</div>
                ${decisionText}
            </div>
        `;
    }).join('');

    box.style.display = 'block';
    box.innerHTML = `
        <div style="font-weight:800; margin-bottom:0.35rem;">${escapeHtml(title)}</div>
        ${rows}
    `;
}

function renderComparisonSummary(comparison) {
    const box = document.getElementById('comparison-summary');
    if (!box) return;
    if (!comparison) {
        box.style.display = 'none';
        box.innerHTML = '';
        return;
    }

    const baseline = comparison.baseline;
    const optimized = comparison.optimized;
    const delta = comparison.delta;
    box.style.display = 'block';
    box.innerHTML = `
        <div style="font-weight:800; margin-bottom:0.5rem; color:#1e293b;">前倒しなし / あり 比較</div>
        <div style="display:flex; flex-wrap:wrap; gap:1rem; font-size:0.9rem; color:#475569;">
            <span>コンテナ本数: ${baseline.container_count} → <strong>${optimized.container_count}</strong> (${delta.container_count >= 0 ? '-' : '+'}${Math.abs(delta.container_count)}本)</span>
            <span>赤字コンテナ: ${baseline.alert_containers} → <strong>${optimized.alert_containers}</strong> (${delta.alert_containers >= 0 ? '-' : '+'}${Math.abs(delta.alert_containers)}本)</span>
            <span>平均体積充填率: ${baseline.avg_volume_rate}% → <strong>${optimized.avg_volume_rate}%</strong> (${delta.avg_volume_rate >= 0 ? '+' : ''}${delta.avg_volume_rate}pt)</span>
            <span>平均重量充填率: ${baseline.avg_weight_rate}% → <strong>${optimized.avg_weight_rate}%</strong> (${delta.avg_weight_rate >= 0 ? '+' : ''}${delta.avg_weight_rate}pt)</span>
        </div>
    `;
}

// 画面遷移関数
function showStep(stepNum) {
    document.querySelectorAll('.step-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.step').forEach(el => el.classList.remove('active'));
    
    document.getElementById(`step-${stepNum}`).classList.remove('hidden');
    document.getElementById(`step-${stepNum}-nav`).classList.add('active');
}

// アプリ起動時（リロード時）にサーバーにデータが残っていればStep2から再開する
document.addEventListener('DOMContentLoaded', async () => {
    loadAssumptions();
    ['sample-rows', 'sample-seed'].forEach(id => {
        const input = document.getElementById(id);
        if (input) input.addEventListener('input', updateSampleDownloadLink);
    });
    if (btnSaveAssumptions) btnSaveAssumptions.addEventListener('click', saveAssumptions);

    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        if (data.has_data) {
            document.getElementById('total-items').textContent = data.total_items + ' 件';
            document.getElementById('base-date').valueAsDate = new Date();
            renderValidationSummary(data);
            renderSimulationContext(data.simulation_context);
            
            // Show Step 2
            document.getElementById('step-1').classList.add('hidden');
            document.getElementById('step-2').classList.remove('hidden');
            
            // Update stepper
            document.querySelectorAll('.step')[0].classList.remove('active');
            document.querySelectorAll('.step')[1].classList.add('active');
        }
    } catch(e) {
        console.error("ステータス取得エラー", e);
    }
});

// ファイルドロップ処理
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.style.borderColor = '#dc2626'; });
dropZone.addEventListener('dragleave', () => dropZone.style.borderColor = '#cbd5e1');
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = '#cbd5e1';
    if(e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', (e) => {
    if(e.target.files.length) uploadFile(e.target.files[0]);
});

async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    dropZone.innerHTML = '<div class="spinner"></div><p>データを解析し、システム共通フォーマットに変換中...</p>';
    
    try {
        const res = await fetch('/api/upload', { method: 'POST', body: formData });
        const data = await res.json();
        
        if(res.ok) {
            // Update Step 2 UI
            document.getElementById('total-items').textContent = data.total_items + ' 件';
            renderValidationSummary(data);
            renderSimulationContext(data.simulation_context);
            
            // 作業基準日の初期値を本日に設定
            document.getElementById('base-date').valueAsDate = new Date();
            
            // Show Step 2
            document.getElementById('step-1').classList.add('hidden');
            document.getElementById('step-2').classList.remove('hidden');
            
            // Update stepper
            document.querySelectorAll('.step')[0].classList.remove('active');
            document.querySelectorAll('.step')[1].classList.add('active');
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
    dropZone.innerHTML = '<div class="upload-icon">📄</div><p>ここにファイルをドラッグ＆ドロップ</p><p class="sub-text">またはクリックしてファイルを選択</p>';
}

// 最適化実行
btnRun.addEventListener('click', async () => {
    showStep(3);
    
    // 段階的なローディング表示（安心感の提供）
    const loadingText = document.getElementById('loading-text');
    const phases = [
        "入力データの構造を解析中...",
        "時間軸（納期・木箱期限）を評価中...",
        "赤字回避のため、現場にある前倒し候補を探索中...",
        "Guillotineアルゴリズムによる3Dパッキングを実行中...",
        "最終的なレイアウト結果を生成中..."
    ];
    let phaseIdx = 0;
    const interval = setInterval(() => {
        phaseIdx = (phaseIdx + 1) % phases.length;
        if(loadingText) loadingText.innerText = phases[phaseIdx];
    }, 800);
    
    const baseDate = document.getElementById('base-date').value;
    const mustShipWindowDays = getBoundedNumber('must-window', 7, 0, 30);
    
    try {
        const res = await fetch('/api/optimize', { 
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ base_date: baseDate, must_ship_window_days: mustShipWindowDays })
        });
        const data = await res.json();
        
        if(res.ok) {
            clearInterval(interval);
            renderResults(data);
            showStep(4);
        } else {
            clearInterval(interval);
            alert('最適化エラー: ' + data.error);
            showStep(2);
        }
    } catch(e) {
        clearInterval(interval);
        alert('通信エラー');
        showStep(2);
    }
});

btnRolling.addEventListener('click', async () => {
    showStep(3);

    const loadingText = document.getElementById('loading-text');
    const phases = [
        "日次の荷物プールを展開中...",
        "出荷済み・未到着・前倒し候補を日ごとに分類中...",
        "ローリング計画を計算中...",
        "赤字コンテナと前倒し効果を集計中..."
    ];
    let phaseIdx = 0;
    const interval = setInterval(() => {
        phaseIdx = (phaseIdx + 1) % phases.length;
        if(loadingText) loadingText.innerText = phases[phaseIdx];
    }, 800);

    const baseDate = document.getElementById('base-date').value;
    const rollingDays = getBoundedNumber('rolling-days', 30, 1, 90);

    try {
        const res = await fetch('/api/rolling', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ base_date: baseDate, days: rollingDays })
        });
        const data = await res.json();

        if(res.ok) {
            clearInterval(interval);
            renderRollingResults(data);
            showStep(4);
        } else {
            clearInterval(interval);
            alert('ローリング計算エラー: ' + data.error);
            showStep(2);
        }
    } catch(e) {
        clearInterval(interval);
        alert('通信エラー');
        showStep(2);
    }
});

btnScenario.addEventListener('click', async () => {
    showStep(3);

    const loadingText = document.getElementById('loading-text');
    if (loadingText) loadingText.innerText = "必須出荷幅ごとのシナリオを比較中...";

    const baseDate = document.getElementById('base-date').value;
    const mustShipWindowDays = getBoundedNumber('must-window', 7, 0, 30);

    try {
        const res = await fetch('/api/scenarios', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ base_date: baseDate, must_ship_window_days: mustShipWindowDays })
        });
        const data = await res.json();

        if(res.ok) {
            renderScenarioResults(data);
            showStep(4);
        } else {
            alert('シナリオ比較エラー: ' + data.error);
            showStep(2);
        }
    } catch(e) {
        alert('通信エラー');
        showStep(2);
    }
});

let currentContainersData = [];
let currentResultMode = 'single';

function renderResults(data) {
    currentResultMode = 'single';
    currentContainersData = data.containers;
    setSingleDayMetricLabels();
    const exportButton = document.getElementById('btn-export');
    const rollingExportButton = document.getElementById('btn-export-rolling');
    if (exportButton) exportButton.style.display = '';
    if (exportButton) exportButton.innerText = '現場への指示書を出力 (Excel)';
    if (rollingExportButton) rollingExportButton.style.display = 'none';
    
    document.getElementById('res-containers').innerText = data.containers.length;
    document.getElementById('res-pool').innerText = data.pool_count;
    document.getElementById('res-forwardable').innerText = data.unused_forwardable_count ?? 0;
    document.getElementById('res-hold').innerText = data.hold_count ?? 0;
    document.getElementById('res-future').innerText = data.future_count;
    document.getElementById('res-excluded').innerText = data.excluded_count ?? 0;
    renderValidationSummary(data);
    renderComparisonSummary(data.comparison);
    renderRiskSummary(data.review_queue, '次に確認する荷物');
    
    // 自然言語サマリーの生成
    const summaryDiv = document.getElementById('natural-language-summary');
    let summaryText = `必須出荷 <strong>${data.must_ship_count ?? 0}件</strong> を基準に、確定コンテナは <strong>${data.containers.length}本</strong> です。`;
    summaryText += `<br>今回の必須出荷幅は基準日から <strong>${data.must_ship_window_days ?? 7}日以内</strong> です。`;
    if (data.packing_strategy) summaryText += `<br>採用した3D配置戦略: <strong>${escapeHtml(data.packing_strategy)}</strong>`;
    if (data.total_pulls > 0) summaryText += `<br>体積充填率80%をクリアするため、現場にある前倒し候補から <strong>${data.total_pulls}件を補填</strong> しました。`;
    if (data.comparison && data.comparison.delta) {
        const d = data.comparison.delta;
        const changes = [];
        if (d.container_count > 0) changes.push(`コンテナ本数 <strong>${d.container_count}本削減</strong>`);
        if (d.alert_containers > 0) changes.push(`赤字コンテナ <strong>${d.alert_containers}本削減</strong>`);
        if (d.avg_volume_rate > 0) changes.push(`平均体積充填率 <strong>${d.avg_volume_rate}pt改善</strong>`);
        if (changes.length > 0) {
            summaryText += `<br>前倒しなしの場合と比べて、${changes.join('、')} です。`;
        }
    }
    if (data.pool_count > 0) summaryText += `<br>納期に余裕のある <strong>${data.pool_count}件</strong> は、次週のコンテナに保留（Push）されました。`;
    if ((data.excluded_count ?? 0) > 0) summaryText += `<br>寸法・重量・日付に問題がある <strong>${data.excluded_count}件</strong> は、安全のため最適化対象から除外しました。`;
    if ((data.hold_count ?? 0) > 0) summaryText += `<br>現場にはありますが前倒し不可の <strong>${data.hold_count}件</strong> は、今回の補填候補から除外しました。`;
    if (data.future_count > 0) summaryText += `<br>まだ現場に到着していない <strong>${data.future_count}件</strong> は、今回の積載候補から除外しました。`;
    if (data.alert_containers > 0 && (data.total_pulls ?? 0) === 0 && (data.unused_forwardable_count ?? 0) > 0) {
        summaryText += `<br>前倒し候補は <strong>${data.unused_forwardable_count}件</strong> 残っていますが、使っても体積80%到達の見込みが薄いため将来便向けに温存しました。`;
    }
    if (data.alert_containers > 0) summaryText += `<br><span style="color:#dc2626;">⚠️ <strong>${data.alert_containers}本</strong> のコンテナが「赤字（体積80%未満）」ですが、納期や手動指定により強制出荷となります。</span>`;
    summaryDiv.innerHTML = summaryText;
    
    const grid = document.getElementById('container-grid');
    grid.innerHTML = '';
    
    data.containers.forEach(c => {
        let statusClass = 'ok';
        let badgeText = '✅ 体積 80% クリア';
        
        if (c.is_alert) {
            statusClass = 'alert';
            badgeText = '🚨 赤字 / 納期強制出荷';
        } else if (c.weight_rate >= 95.0) {
            statusClass = 'warning';
            badgeText = '⚠️ 重量上限に接近';
        }
        
        // 重心アラートの計算
        // Python X (0-12000), Python Z (0-2400)
        let dx = Math.abs(c.cg_x - 6000) / 6000;
        let dz = c.cg_z / 2400;
        
        let cgAlertsHtml = '';
        if (dx > 0.2) cgAlertsHtml += `<div style="background:#fee2e2; color:#dc2626; padding:2px 6px; border-radius:4px; font-size:0.75rem; font-weight:600; display:inline-block; margin-right:4px;">🚨 前後偏荷重</div>`;
        else if (dx > 0.1) cgAlertsHtml += `<div style="background:#fef3c7; color:#d97706; padding:2px 6px; border-radius:4px; font-size:0.75rem; font-weight:600; display:inline-block; margin-right:4px;">⚠️ 前後偏荷重(注意)</div>`;
        
        if (dz > 0.55) cgAlertsHtml += `<div style="background:#fee2e2; color:#dc2626; padding:2px 6px; border-radius:4px; font-size:0.75rem; font-weight:600; display:inline-block;">🚨 高重心リスク</div>`;
        else if (dz > 0.45) cgAlertsHtml += `<div style="background:#fef3c7; color:#d97706; padding:2px 6px; border-radius:4px; font-size:0.75rem; font-weight:600; display:inline-block;">⚠️ 高重心(注意)</div>`;
        
        if (cgAlertsHtml === '') cgAlertsHtml = `<div style="background:#dcfce7; color:#16a34a; padding:2px 6px; border-radius:4px; font-size:0.75rem; font-weight:600; display:inline-block;">✅ 重心バランス良好</div>`;

        const alertReasonHtml = c.alert_reason_title ? `
            <div style="background:${c.is_alert ? '#fff1f2' : '#ecfdf5'}; border-left:4px solid ${c.is_alert ? '#ef4444' : '#10b981'}; padding:0.65rem 0.75rem; margin:0.75rem 0; border-radius:4px;">
                <div style="font-size:0.84rem; font-weight:700; color:${c.is_alert ? '#b91c1c' : '#047857'};">${escapeHtml(c.alert_reason_title)}</div>
                <div style="font-size:0.78rem; line-height:1.45; color:${c.is_alert ? '#7f1d1d' : '#065f46'}; margin-top:0.25rem;">${escapeHtml(c.alert_reason_detail)}</div>
            </div>
        ` : '';
        const geometryHtml = c.geometry_valid === false ? `
            <div style="background:#fef2f2; border-left:4px solid #dc2626; padding:0.55rem 0.75rem; margin:0.75rem 0; border-radius:4px;">
                <div style="font-size:0.84rem; font-weight:700; color:#991b1b;">3D配置要確認</div>
                <div style="font-size:0.78rem; line-height:1.45; color:#7f1d1d; margin-top:0.25rem;">${(c.geometry_warnings || []).map(escapeHtml).join(' / ')}</div>
            </div>
        ` : '';
        
        
        let logsHtml = '<div class="c-logs"><strong>【システムの最適化理由】</strong>（クリックで強制出荷をON/OFF）<br>';
        
        // 品名、ステータス、強制出荷フラグが同じものをグループ化して戸数（x個）を表示
        let itemGroups = {};
        c.items.forEach(i => {
            const constraintsKey = (i.constraint_tags || []).join(",");
            const key = i.name + "|" + i.status_msg + "|" + i.selection_reason + "|" + i.decision_reason + "|" + constraintsKey + "|" + i.is_force_ship;
            if(!itemGroups[key]) {
                itemGroups[key] = {
                    ids: [i.id],
                    name: i.name,
                    status_msg: i.status_msg,
                    selection_reason: i.selection_reason,
                    decision_reason: i.decision_reason,
                    constraint_tags: i.constraint_tags || [],
                    is_force_ship: i.is_force_ship,
                    is_manual_force_ship: i.is_manual_force_ship,
                    is_system_force_ship: i.is_system_force_ship,
                    count: 1
                };
            } else {
                itemGroups[key].ids.push(i.id);
                itemGroups[key].count++;
            }
        });
        
        Object.values(itemGroups).forEach(g => {
            const icon = g.is_force_ship ? '<span class="log-icon force">🚨</span>' : '<span class="log-icon">📦</span>';
            const reason = g.selection_reason ? `<span style="color:#64748b;font-size:0.8em;">[${escapeHtml(g.selection_reason)}]</span>` : '';
            const msg = g.status_msg ? `<span style="color:#f59e0b;font-size:0.8em;">(${escapeHtml(g.status_msg)})</span>` : '';
            const constraints = g.constraint_tags.length ? `<span style="color:#2563eb;font-size:0.8em;">{${g.constraint_tags.map(escapeHtml).join(' / ')}}</span>` : '';
            const decision = g.decision_reason ? `<div style="color:#64748b;font-size:0.78rem; margin-left:1.5rem; margin-top:0.1rem;">判断根拠: ${escapeHtml(g.decision_reason)}</div>` : '';
            const idsJson = JSON.stringify(g.ids).replace(/"/g, '&quot;');
            logsHtml += `<div class="log-item" style="cursor:pointer; padding: 2px; border-radius: 4px; transition: background 0.2s;" onmouseover="this.style.background='#f3f4f6'" onmouseout="this.style.background='transparent'" onclick="toggleOverride(${idsJson}, ${!g.is_manual_force_ship})">
                ${icon} ${escapeHtml(g.name)} <strong>x ${g.count}</strong> ${constraints} ${reason} ${msg}
                ${decision}
            </div>`;
        });
        
        logsHtml += '</div>';
        
        const card = document.createElement('div');
        card.className = `c-card ${statusClass}`;
        card.innerHTML = `
            <div class="c-badge">${badgeText}</div>
            <div class="c-title" style="display:flex; align-items:center; justify-content:space-between; gap:0.75rem;">
                <span>&#35336;&#30011;ID ${c.id}</span>
                <span style="font-size:0.75rem; color:#64748b; font-weight:600;">&#32013;&#21697;&#38918; ${c.display_order ?? ''}</span>
            </div>
            <div class="c-metric" style="border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; margin-bottom: 8px;">
                <span style="color:#6b7280; font-size:0.8rem;">最短納期: ${escapeHtml(c.earliest_due)}</span>
                <span style="color:#6b7280; font-size:0.8rem;">木箱期限: ${escapeHtml(c.earliest_exp)}</span>
            </div>
            <div class="c-metric">
                <span>重量</span>
                <span class="c-metric-val">${c.weight_val.toLocaleString()} kg <span style="font-size:0.75rem; color:#9ca3af;">/ ${c.weight_max.toLocaleString()}</span></span>
            </div>
            <div class="c-metric">
                <span>重量充填率</span>
                <span class="c-metric-val">${c.weight_rate}%</span>
            </div>
            <div class="c-metric">
                <span>体積充填率</span>
                <span class="c-metric-val">${c.volume_rate}%</span>
            </div>
            ${alertReasonHtml}
            ${geometryHtml}
            <div class="c-metric" style="border-bottom: 1px solid #e5e7eb; padding-bottom: 8px; margin-bottom: 8px;">
                <span style="font-size:0.8rem; font-weight:600; color:#4b5563;">重心評価</span>
                <div style="text-align:right;">${cgAlertsHtml}</div>
            </div>
            ${logsHtml}
            <div class="action-bar" style="margin-top: 1rem;">
                <button class="btn primary" style="width: 100%; padding: 0.5rem; background-color: #2563eb;" onmouseover="this.style.backgroundColor='#1d4ed8'" onmouseout="this.style.backgroundColor='#2563eb'" onclick="open3D('${c.id}')">👁️ 3Dレイアウトを見る</button>
            </div>
        `;
        grid.appendChild(card);
    });
}

function renderRollingResults(data) {
    currentResultMode = 'rolling';
    currentContainersData = [];
    setRollingMetricLabels();
    const exportButton = document.getElementById('btn-export');
    const rollingExportButton = document.getElementById('btn-export-rolling');
    if (exportButton) exportButton.style.display = 'none';
    if (rollingExportButton) rollingExportButton.style.display = '';

    document.getElementById('res-containers').innerText = data.total_containers;
    document.getElementById('res-pool').innerText = data.remaining_count;
    document.getElementById('res-forwardable').innerText = data.total_pulls;
    document.getElementById('res-hold').innerText = data.deadline_remaining_count ?? data.overdue_count;
    document.getElementById('res-future').innerText = 0;
    document.getElementById('res-excluded').innerText = data.excluded_count ?? 0;
    renderValidationSummary(data);
    renderRiskSummary(data.remaining_risks, '期間終了時点の未出荷リスク');

    const comparisonBox = document.getElementById('comparison-summary');
    if (comparisonBox) {
        const cmp = data.comparison;
        comparisonBox.style.display = 'block';
        let comparisonHtml = '';
        if (cmp) {
            comparisonHtml = `
                <div style="margin-top:0.75rem; display:flex; flex-wrap:wrap; gap:1rem; font-size:0.9rem; color:#475569;">
                    <span>前倒しなし総コンテナ: ${cmp.baseline.total_containers} → <strong>${cmp.optimized.total_containers}</strong>本 (${cmp.delta.total_containers >= 0 ? '-' : '+'}${Math.abs(cmp.delta.total_containers)}本)</span>
                    <span>出荷件数: ${cmp.baseline.total_shipped} → <strong>${cmp.optimized.total_shipped}</strong>件 (${cmp.delta.total_shipped >= 0 ? '+' : ''}${cmp.delta.total_shipped}件)</span>
                    <span>赤字コンテナ: ${cmp.baseline.total_alert_containers} → <strong>${cmp.optimized.total_alert_containers}</strong>本 (${cmp.delta.total_alert_containers >= 0 ? '-' : '+'}${Math.abs(cmp.delta.total_alert_containers)}本)</span>
                    <span>赤字率: ${cmp.baseline.alert_rate}% → <strong>${cmp.optimized.alert_rate}%</strong> (${cmp.delta.alert_rate >= 0 ? '-' : '+'}${Math.abs(cmp.delta.alert_rate)}pt)</span>
                    <span>期間後残: ${cmp.baseline.remaining_count} → <strong>${cmp.optimized.remaining_count}</strong>件 (${cmp.delta.remaining_count >= 0 ? '-' : '+'}${Math.abs(cmp.delta.remaining_count)}件)</span>
                    <span>体積充填率: ${cmp.baseline.avg_volume_rate}% → <strong>${cmp.optimized.avg_volume_rate}%</strong> (${cmp.delta.avg_volume_rate >= 0 ? '+' : ''}${cmp.delta.avg_volume_rate}pt)</span>
                </div>
            `;
        }
        comparisonBox.innerHTML = `
            <div style="font-weight:800; margin-bottom:0.5rem; color:#1e293b;">${escapeHtml(data.start_date)} から ${data.days}日間のローリング結果</div>
            <div style="display:flex; flex-wrap:wrap; gap:1rem; font-size:0.9rem; color:#475569;">
                <span>総出荷数: <strong>${data.total_shipped}</strong>件</span>
                <span>総コンテナ: <strong>${data.total_containers}</strong>本</span>
                <span>週換算: <strong>${data.weekly_container_rate}</strong>本/週</span>
                <span>前倒し補填: <strong>${data.total_pulls}</strong>件</span>
                <span>赤字コンテナ: <strong>${data.total_alert_containers}</strong>本</span>
                <span>赤字率: <strong>${data.alert_rate}%</strong></span>
                <span>平均体積充填率: <strong>${data.avg_volume_rate}%</strong></span>
                <span>平均重量充填率: <strong>${data.avg_weight_rate}%</strong></span>
                <span>期間後残: <strong>${data.remaining_count}</strong>件</span>
                <span>期限到来/超過残: <strong>${data.deadline_remaining_count ?? data.overdue_count}</strong>件</span>
            </div>
            ${comparisonHtml}
        `;
    }

    const summaryDiv = document.getElementById('natural-language-summary');
    let summaryText = `<strong>${escapeHtml(data.start_date)}〜${escapeHtml(data.end_date)}</strong> の日次ローリングで、<strong>${data.total_shipped}件</strong> を <strong>${data.total_containers}本</strong> のコンテナに割り当てました。`;
    if (data.total_pulls > 0) summaryText += `<br>期間中、現場にある納期先の荷物から <strong>${data.total_pulls}件</strong> を前倒し補填しました。`;
    if (data.comparison && data.comparison.delta) {
        const d = data.comparison.delta;
        const changes = [];
        if (d.total_shipped > 0) changes.push(`出荷件数 <strong>${d.total_shipped}件増加</strong>`);
        if (d.total_containers > 0) changes.push(`コンテナ本数 <strong>${d.total_containers}本削減</strong>`);
        if (d.total_alert_containers > 0) changes.push(`赤字コンテナ <strong>${d.total_alert_containers}本削減</strong>`);
        if (d.remaining_count > 0) changes.push(`期間後残 <strong>${d.remaining_count}件削減</strong>`);
        if (changes.length > 0) {
            summaryText += `<br>前倒しなしの${data.days}日計画と比べて、${changes.join('、')} です。`;
        }
    }
    if (data.total_alert_containers > 0) summaryText += `<br><span style="color:#dc2626;">赤字コンテナは <strong>${data.total_alert_containers}本</strong> 発生しています。</span>`;
    if ((data.deadline_remaining_count ?? data.overdue_count) > 0) summaryText += `<br><span style="color:#dc2626;">期間終了時点で期限到来または期限超過の未出荷が <strong>${data.deadline_remaining_count ?? data.overdue_count}件</strong> 残っています。</span>`;
    if ((data.excluded_count ?? 0) > 0) summaryText += `<br>入力チェックで <strong>${data.excluded_count}件</strong> を安全のため除外しました。`;
    summaryDiv.innerHTML = summaryText;

    const grid = document.getElementById('container-grid');
    grid.innerHTML = '';

    const activeDays = data.daily_results.filter(day =>
        day.containers > 0 || day.must_ship > 0 || day.pulls > 0 || (day.deadline_remaining ?? day.overdue_remaining) > 0
    );
    const daysToRender = activeDays.length ? activeDays : data.daily_results.slice(0, 7);

    daysToRender.forEach(day => {
        let statusClass = 'ok';
        let badgeText = '日次計画';
        if (day.alerts > 0 || (day.deadline_remaining ?? day.overdue_remaining) > 0) {
            statusClass = 'alert';
            badgeText = '要確認';
        } else if (day.pulls > 0) {
            statusClass = 'warning';
            badgeText = '前倒し補填';
        }

        const card = document.createElement('div');
        card.className = `c-card ${statusClass}`;
        card.innerHTML = `
            <div class="c-badge">${badgeText}</div>
            <div class="c-title">${escapeHtml(day.date)}</div>
            <div class="c-metric"><span>コンテナ</span><span class="c-metric-val">${day.containers} 本</span></div>
            <div class="c-metric"><span>出荷</span><span class="c-metric-val">${day.shipped} 件</span></div>
            <div class="c-metric"><span>必須出荷</span><span class="c-metric-val">${day.must_ship} 件</span></div>
            <div class="c-metric"><span>前倒し補填</span><span class="c-metric-val">${day.pulls} 件</span></div>
            <div class="c-metric"><span>赤字コンテナ</span><span class="c-metric-val">${day.alerts} 本</span></div>
            <div class="c-metric"><span>平均体積充填率</span><span class="c-metric-val">${day.avg_volume_rate}%</span></div>
            <div class="c-metric"><span>平均重量充填率</span><span class="c-metric-val">${day.avg_weight_rate}%</span></div>
            <div class="c-logs">
                前倒し候補 ${day.forwardable}件 / 未使用 ${day.unused_forwardable}件 / 未到着 ${day.future}件 / 期限到来/超過残 ${day.deadline_remaining ?? day.overdue_remaining}件
            </div>
        `;
        grid.appendChild(card);
    });
}

function renderScenarioResults(data) {
    currentResultMode = 'scenario';
    currentContainersData = [];
    setScenarioMetricLabels();
    const exportButton = document.getElementById('btn-export');
    const rollingExportButton = document.getElementById('btn-export-rolling');
    if (exportButton) {
        exportButton.style.display = '';
        exportButton.innerText = 'シナリオ比較を出力 (Excel)';
    }
    if (rollingExportButton) rollingExportButton.style.display = 'none';

    const scenarios = data.scenarios || [];
    const recommended = data.recommended || {};
    const minAlerts = scenarios.length ? Math.min(...scenarios.map(s => s.alert_containers)) : 0;
    const minContainers = scenarios.length ? Math.min(...scenarios.map(s => s.container_count)) : 0;
    const maxMustShip = scenarios.length ? Math.max(...scenarios.map(s => s.must_ship_count)) : 0;

    document.getElementById('res-containers').innerText = scenarios.length;
    document.getElementById('res-pool').innerText = recommended.must_ship_window_days ?? '-';
    document.getElementById('res-forwardable').innerText = minAlerts;
    document.getElementById('res-hold').innerText = minContainers;
    document.getElementById('res-future').innerText = maxMustShip;
    document.getElementById('res-excluded').innerText = data.excluded_count ?? 0;
    renderValidationSummary(data);
    renderRiskSummary([], '');

    const comparisonBox = document.getElementById('comparison-summary');
    if (comparisonBox) {
        comparisonBox.style.display = 'block';
        comparisonBox.innerHTML = `
            <div style="font-weight:800; margin-bottom:0.5rem; color:#1e293b;">必須出荷幅シナリオ比較</div>
            <div style="font-size:0.9rem; color:#475569;">
                推奨は <strong>${recommended.must_ship_window_days ?? '-'}日先読み</strong> です。
                赤字本数、コンテナ本数、平均体積充填率の順に評価しています。
            </div>
        `;
    }

    const summaryDiv = document.getElementById('natural-language-summary');
    summaryDiv.innerHTML = `
        <strong>${escapeHtml(data.base_date)}</strong> を基準に、必須出荷幅を ${scenarios.map(s => `${s.must_ship_window_days}日`).join(' / ')} で比較しました。<br>
        推奨は <strong>${recommended.must_ship_window_days ?? '-'}日</strong> で、
        コンテナ <strong>${recommended.container_count ?? 0}本</strong>、
        赤字 <strong>${recommended.alert_containers ?? 0}本</strong>、
        平均体積充填率 <strong>${recommended.avg_volume_rate ?? 0}%</strong> です。
    `;

    const grid = document.getElementById('container-grid');
    grid.innerHTML = '';

    scenarios.forEach(s => {
        let statusClass = s.recommended ? 'ok' : 'warning';
        if (s.alert_containers > minAlerts) statusClass = 'alert';
        const badgeText = s.recommended ? '推奨シナリオ' : '比較候補';

        const card = document.createElement('div');
        card.className = `c-card ${statusClass}`;
        card.innerHTML = `
            <div class="c-badge">${badgeText}</div>
            <div class="c-title">必須出荷幅 ${s.must_ship_window_days}日</div>
            <div class="c-metric"><span>コンテナ</span><span class="c-metric-val">${s.container_count} 本</span></div>
            <div class="c-metric"><span>赤字コンテナ</span><span class="c-metric-val">${s.alert_containers} 本</span></div>
            <div class="c-metric"><span>平均体積充填率</span><span class="c-metric-val">${s.avg_volume_rate}%</span></div>
            <div class="c-metric"><span>平均重量充填率</span><span class="c-metric-val">${s.avg_weight_rate}%</span></div>
            <div class="c-metric"><span>必須出荷</span><span class="c-metric-val">${s.must_ship_count} 件</span></div>
            <div class="c-metric"><span>前倒し補填</span><span class="c-metric-val">${s.total_pulls} 件</span></div>
            <div class="c-logs">
                保留 ${s.pool_count}件 / 前倒し候補残 ${s.unused_forwardable_count}件 / 前倒し不可 ${s.hold_count}件 / 未到着 ${s.future_count}件
            </div>
        `;
        grid.appendChild(card);
    });
}

// 手動オーバーライド機能
async function toggleOverride(itemIds, forceShip) {
    const actionName = forceShip ? "「強制出荷」" : "「強制出荷の解除」";
    const msg = `この荷物を ${actionName} に変更します。\n※変更後、システムは全体のパズルを再計算します。赤字コンテナが発生する可能性がありますがよろしいですか？`;
    
    if(!confirm(msg)) return;
    
    try {
        const res = await fetch('/api/override', { 
            method: 'POST', 
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({item_ids: itemIds, force_ship: forceShip})
        });
        if(res.ok) {
            // オーバーライド成功後、再度最適化を走らせて画面更新
            btnRun.click();
        } else {
            alert("エラーが発生しました");
        }
    } catch(e) {
        console.error(e);
        alert('通信エラー');
    }
}

// 現場用指示書ダウンロード
function downloadExcel() {
    if (currentResultMode === 'scenario') {
        window.location.href = '/api/export_scenarios';
        return;
    }
    window.location.href = '/api/export';
}

function downloadRollingExcel() {
    window.location.href = '/api/export_rolling';
}

// ==========================================
// 3D Visualization (Three.js)
// ==========================================
let scene, camera, renderer, controls;
let animId;
let interactableMeshes = [];
let raycaster = new THREE.Raycaster();
let mouse = new THREE.Vector2();

function init3D() {
    if(renderer) return; 
    const container = document.getElementById('3d-container');
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf3f4f6);
    
    camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 1000);
    camera.position.set(15, 10, 15);
    
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    container.appendChild(renderer.domElement);
    
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    
    // Window resize handler
    window.addEventListener('resize', () => {
        if(document.getElementById('modal-3d').style.display !== 'none') {
            camera.aspect = container.clientWidth / container.clientHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(container.clientWidth, container.clientHeight);
        }
    });
    
    // Mouse hover raycasting
    container.addEventListener('mousemove', (event) => {
        const rect = container.getBoundingClientRect();
        mouse.x = ((event.clientX - rect.left) / container.clientWidth) * 2 - 1;
        mouse.y = -((event.clientY - rect.top) / container.clientHeight) * 2 + 1;
        
        raycaster.setFromCamera(mouse, camera);
        const intersects = raycaster.intersectObjects(interactableMeshes);
        const tooltip = document.getElementById('3d-tooltip');
        
        if (intersects.length > 0) {
            const mesh = intersects[0].object;
            const item = mesh.userData.item;
            
            tooltip.style.display = 'block';
            tooltip.style.left = (event.clientX - rect.left + 20) + 'px';
            tooltip.style.top = (event.clientY - rect.top + 20) + 'px';
            
            const reason = item.selection_reason ? `<br><span style="color:#93c5fd;">${escapeHtml(item.selection_reason)}</span>` : '';
            const msg = item.status_msg ? `<br><span style="color:#f59e0b;">${escapeHtml(item.status_msg)}</span>` : '';
            const force = item.is_force_ship ? '<br><span style="color:#ef4444;">🚨 強制出荷</span>' : '';
            
            tooltip.innerHTML = `
                <strong style="font-size:1.1em;">📦 ${escapeHtml(item.name)}</strong><br>
                <div style="margin-top:4px; color:#d1d5db;">寸法: L ${item.l} × W ${item.w} × H ${item.h} mm</div>
                ${reason}${msg}${force}
            `;
        } else {
            tooltip.style.display = 'none';
        }
    });
    
    animate();
}

function animate() {
    animId = requestAnimationFrame(animate);
    if(controls) controls.update();
    if(renderer && scene && camera) renderer.render(scene, camera);
}

function close3D() {
    document.getElementById('modal-3d').style.display = 'none';
}

function open3D(containerId) {
    document.getElementById('modal-3d').style.display = 'flex';
    document.getElementById('modal-title').innerText = containerId + " の3Dレイアウト";
    
    // Slight delay to ensure DOM is ready and visible for sizing
    setTimeout(() => {
        init3D();
        
        // Clear old objects
        while(scene.children.length > 0){ 
            scene.remove(scene.children[0]); 
        }
        interactableMeshes = [];
        document.getElementById('3d-tooltip').style.display = 'none';
        
        // Add lights
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
        scene.add(ambientLight);
        const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
        dirLight.position.set(10, 20, 10);
        scene.add(dirLight);
        
        // Isuzu Container dimensions (mm -> m) (現場有効内寸)
        const cW = 2.300, cH = 2.400, cL = 12.0;
        
        // Draw container wireframe
        // Zファイティング（はみ出し錯覚）を防ぐため、枠線をほんの少しだけ大きく（+4mm）する
        const geometry = new THREE.BoxGeometry(cW + 0.004, cH + 0.004, cL + 0.004);
        const edges = new THREE.EdgesGeometry(geometry);
        const line = new THREE.LineSegments(edges, new THREE.LineBasicMaterial({ color: 0x000000, linewidth: 2 }));
        line.position.set(cW/2, cH/2, cL/2);
        scene.add(line);
        
        // Add Grid Helper (Shift to center of container base, make it long enough)
        const gridHelper = new THREE.GridHelper(16, 16, 0x888888, 0xcccccc);
        gridHelper.position.set(cW/2, 0, cL/2);
        scene.add(gridHelper);
        
        const cData = currentContainersData.find(c => c.id === containerId);
        if(!cData) return;
        
        // 統計パネルの更新
        const statsOverlay = document.getElementById('3d-stats-overlay');
        statsOverlay.innerHTML = `
            <div style="font-weight:800; margin-bottom: 0.5rem; color:#1f2937; border-bottom: 2px solid #e5e7eb; padding-bottom: 4px;">コンテナ情報・積載状況</div>
            <table style="width:100%; border-collapse: collapse; font-size: 0.9rem;">
                <tr><td style="color:#6b7280; padding:2px 0; width: 80px;">有効内寸</td><td style="font-weight:600; text-align:right;">L 12.0 × W 2.30 × H 2.40 m</td></tr>
                <tr><td style="color:#6b7280; padding:2px 0;">最大重量</td><td style="font-weight:600; text-align:right;">${cData.weight_max.toLocaleString()} kg</td></tr>
                <tr><td style="color:#6b7280; padding:2px 0;">積載重量</td><td style="font-weight:800; color:#2563eb; text-align:right;">${cData.weight_val.toLocaleString()} kg <span style="font-size:0.8em; color:#6b7280;">(${cData.weight_rate}%)</span></td></tr>
                <tr><td style="color:#6b7280; padding:2px 0;">体積充填</td><td style="font-weight:800; color:#2563eb; text-align:right;">${cData.volume_rate}%</td></tr>
            </table>
        `;
        
        cData.items.forEach(item => {
            // 元の寸法 (mm -> m)
            let item_l = item.l / 1000;
            let item_w = item.w / 1000;
            let item_h = item.h / 1000;
            
            // Python側で回転している場合、X軸方向とY軸方向の専有サイズが入れ替わる
            let pack_x_len = item.rotated ? item_w : item_l; // PythonのX軸方向（奥行き）
            let pack_y_len = item.rotated ? item_l : item_w; // PythonのY軸方向（横幅）
            let pack_z_len = item_h;                         // PythonのZ軸方向（高さ）
            
            // Three.jsの座標系へのマッピング
            const sizeX = pack_y_len;
            const sizeY = pack_z_len;
            const sizeZ = pack_x_len;
            
            const x = item.y / 1000;
            const y = item.z / 1000; 
            const z = item.x / 1000; 
            
            // 描画上の錯覚（枠線と完全に重なることで飛び出して見える現象）を完全に防ぐため、
            // 実際の計算サイズよりも「見た目だけ1cm小さく」描画して隙間を作ります。
            const visualMargin = 0.01; 
            const vSizeX = Math.max(0.01, sizeX - visualMargin);
            const vSizeY = Math.max(0.01, sizeY - visualMargin);
            const vSizeZ = Math.max(0.01, sizeZ - visualMargin);
            
            const boxGeo = new THREE.BoxGeometry(vSizeX, vSizeY, vSizeZ);
            
            // Color logic
            let color = 0x3b82f6; // Blue (normal)
            if(item.is_force_ship) color = 0xef4444; // Red (forced)
            else if(item.status_msg && item.status_msg.includes("前倒し")) color = 0x10b981; // Green (pulled)
            
            const material = new THREE.MeshStandardMaterial({ 
                color: color, 
                opacity: 1.0, 
                transparent: false,
                roughness: 0.5,
                metalness: 0.1,
                polygonOffset: true,
                polygonOffsetFactor: 1,
                polygonOffsetUnits: 1
            });
            const mesh = new THREE.Mesh(boxGeo, material);
            mesh.userData = { item: item }; // ホバー用データ保持
            interactableMeshes.push(mesh);
            
            // Edges for clarity (黒色の少し太い線にして輪郭をクッキリさせる)
            const boxEdges = new THREE.EdgesGeometry(boxGeo);
            const edgeLine = new THREE.LineSegments(boxEdges, new THREE.LineBasicMaterial({ color: 0x1e293b, linewidth: 2 }));
            mesh.add(edgeLine);
            
            // Three.js BoxGeometry sets origin to center, so shift it
            mesh.position.set(x + sizeX/2, y + sizeY/2, z + sizeZ/2);
            scene.add(mesh);
        });
        
        // 重心（Center of Gravity）マーカーの描画（箱に埋もれないように最前面に表示）
        const cgSphereGeo = new THREE.SphereGeometry(0.15, 16, 16);
        const cgSphereMat = new THREE.MeshBasicMaterial({ color: 0xff0000, depthTest: false, transparent: true });
        const cgSphere = new THREE.Mesh(cgSphereGeo, cgSphereMat);
        
        // Three.js座標系へマッピング
        const cgX = cData.cg_y / 1000;
        const cgY = cData.cg_z / 1000;
        const cgZ = cData.cg_x / 1000;
        cgSphere.position.set(cgX, cgY, cgZ);
        scene.add(cgSphere);
        
        // 重心位置から床への垂線（分かりやすさのため）
        const dropLineGeo = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(cgX, cgY, cgZ),
            new THREE.Vector3(cgX, 0, cgZ)
        ]);
        const dropLineMat = new THREE.LineDashedMaterial({ color: 0xff0000, linewidth: 2, dashSize: 0.1, gapSize: 0.1, depthTest: false, transparent: true });
        const dropLine = new THREE.Line(dropLineGeo, dropLineMat);
        dropLine.computeLineDistances();
        scene.add(dropLine);
        
        // コンテナ中心線（床面の点線）
        const centerLineGeo = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(cW/2, 0.01, 0),
            new THREE.Vector3(cW/2, 0.01, cL)
        ]);
        const centerLineMat = new THREE.LineDashedMaterial({ color: 0xff0000, linewidth: 1, dashSize: 0.4, gapSize: 0.2 });
        const centerLine = new THREE.Line(centerLineGeo, centerLineMat);
        centerLine.computeLineDistances();
        scene.add(centerLine);
        
        // Set camera angle to look at the open doors (assuming z=0 is deep end, z=12 is doors)
        camera.position.set(cW / 2, cH + 3, cL + 6);
        controls.target.set(cW/2, cH/2, cL/2);
        controls.update();
        
        // Force resize update
        const containerDom = document.getElementById('3d-container');
        camera.aspect = containerDom.clientWidth / containerDom.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(containerDom.clientWidth, containerDom.clientHeight);
    }, 50);
}
