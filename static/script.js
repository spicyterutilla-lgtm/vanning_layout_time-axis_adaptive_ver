const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const btnRun = document.getElementById('btn-run');

// 画面遷移関数
function showStep(stepNum) {
    document.querySelectorAll('.step-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.step').forEach(el => el.classList.remove('active'));
    
    document.getElementById(`step-${stepNum}`).classList.remove('hidden');
    document.getElementById(`step-${stepNum}-nav`).classList.add('active');
}

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
        "赤字回避のため、未来の荷物から前倒し候補を探索中...",
        "Guillotineアルゴリズムによる3Dパッキングを実行中...",
        "最終的なレイアウト結果を生成中..."
    ];
    let phaseIdx = 0;
    const interval = setInterval(() => {
        phaseIdx = (phaseIdx + 1) % phases.length;
        if(loadingText) loadingText.innerText = phases[phaseIdx];
    }, 800);
    
    const baseDate = document.getElementById('base-date').value;
    
    try {
        const res = await fetch('/api/optimize', { 
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ base_date: baseDate })
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

let currentContainersData = [];

function renderResults(data) {
    currentContainersData = data.containers;
    
    document.getElementById('res-containers').innerText = data.containers.length;
    document.getElementById('res-pool').innerText = data.pool_count;
    document.getElementById('res-future').innerText = data.future_count;
    
    // 自然言語サマリーの生成
    const summaryDiv = document.getElementById('natural-language-summary');
    let summaryText = `今週出荷が確定したコンテナは <strong>${data.containers.length}本</strong> です。`;
    if (data.total_pulls > 0) summaryText += `<br>充填率80%をクリアするため、来週以降の荷物から <strong>${data.total_pulls}件を前倒しで補填</strong> しました。`;
    if (data.pool_count > 0) summaryText += `<br>納期に余裕のある <strong>${data.pool_count}件</strong> は、次週のコンテナに保留（Push）されました。`;
    if (data.alert_containers > 0) summaryText += `<br><span style="color:#dc2626;">⚠️ <strong>${data.alert_containers}本</strong> のコンテナが「赤字（80%未満）」ですが、納期や手動指定により強制出荷となります。</span>`;
    summaryDiv.innerHTML = summaryText;
    
    const grid = document.getElementById('container-grid');
    grid.innerHTML = '';
    
    data.containers.forEach(c => {
        let statusClass = 'ok';
        let badgeText = '✅ 体積 80% クリア';
        
        if (c.is_alert) {
            statusClass = 'alert';
            badgeText = '🚨 赤字 / 納期強制出荷';
        } else if (c.weight_rate >= 80.0 && c.volume_rate < 80.0) {
            statusClass = 'warning';
            badgeText = '⚠️ 重量限界到達'; // 重量制限によりこれ以上積めないためクリア
        }
        
        
        let logsHtml = '<div class="c-logs"><strong>【システムの最適化理由】</strong>（クリックで強制出荷をON/OFF）<br>';
        
        // 品名、ステータス、強制出荷フラグが同じものをグループ化して戸数（x個）を表示
        let itemGroups = {};
        c.items.forEach(i => {
            const key = i.name + "|" + i.status_msg + "|" + i.is_force_ship;
            if(!itemGroups[key]) {
                itemGroups[key] = {
                    ids: [i.id],
                    name: i.name,
                    status_msg: i.status_msg,
                    is_force_ship: i.is_force_ship,
                    count: 1
                };
            } else {
                itemGroups[key].ids.push(i.id);
                itemGroups[key].count++;
            }
        });
        
        Object.values(itemGroups).forEach(g => {
            const icon = g.is_force_ship ? '<span class="log-icon force">🚨</span>' : '<span class="log-icon">📦</span>';
            const msg = g.status_msg ? `<span style="color:#f59e0b;font-size:0.8em;">(${g.status_msg})</span>` : '';
            const idsJson = JSON.stringify(g.ids).replace(/"/g, '&quot;');
            logsHtml += `<div class="log-item" style="cursor:pointer; padding: 2px; border-radius: 4px; transition: background 0.2s;" onmouseover="this.style.background='#f3f4f6'" onmouseout="this.style.background='transparent'" onclick="toggleOverride(${idsJson}, ${!g.is_force_ship})">
                ${icon} ${g.name} <strong>x ${g.count}</strong> ${msg}
            </div>`;
        });
        
        logsHtml += '</div>';
        
        const card = document.createElement('div');
        card.className = `c-card ${statusClass}`;
        card.innerHTML = `
            <div class="c-badge">${badgeText}</div>
            <div class="c-title">${c.id}</div>
            <div class="c-metric" style="border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; margin-bottom: 8px;">
                <span style="color:#6b7280; font-size:0.8rem;">最短納期: ${c.earliest_due}</span>
                <span style="color:#6b7280; font-size:0.8rem;">木箱期限: ${c.earliest_exp}</span>
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
            ${logsHtml}
            <div class="action-bar" style="margin-top: 1rem;">
                <button class="btn primary" style="width: 100%; padding: 0.5rem; background-color: #2563eb;" onmouseover="this.style.backgroundColor='#1d4ed8'" onmouseout="this.style.backgroundColor='#2563eb'" onclick="open3D('${c.id}')">👁️ 3Dレイアウトを見る</button>
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
    window.location.href = '/api/export';
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
            
            const msg = item.status_msg ? `<br><span style="color:#f59e0b;">${item.status_msg}</span>` : '';
            const force = item.is_force_ship ? '<br><span style="color:#ef4444;">🚨 強制出荷</span>' : '';
            
            tooltip.innerHTML = `
                <strong style="font-size:1.1em;">📦 ${item.name}</strong><br>
                <div style="margin-top:4px; color:#d1d5db;">寸法: L ${item.l} × W ${item.w} × H ${item.h} mm</div>
                ${msg}${force}
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
        
        // Isuzu Container dimensions (mm -> m)
        const cW = 2.352, cH = 2.385, cL = 12.0;
        
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
                <tr><td style="color:#6b7280; padding:2px 0; width: 80px;">内寸寸法</td><td style="font-weight:600; text-align:right;">L 12.0 × W 2.35 × H 2.38 m</td></tr>
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
