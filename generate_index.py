"""
generate_index.py
ui_test.html をベースに、モックデータ部分だけ実APIに差し替えた
index.html を UTF-8 で生成するスクリプト
"""
import re, sys

src = open('static/ui_test.html', 'r', encoding='utf-8').read()

# 1. タイトル変更 (UIテスト版 -> 本番)
src = src.replace(
    '<title>【UIテスト】いすゞ KDバンニングシミュレーター</title>',
    '<title>いすゞ KDバンニングシミュレーター</title>'
)

# 2. ロゴのバッジを「UIテスト版」-> 「β版」
src = src.replace(
    '>UIテスト版<',
    '>β版<'
)

# 3. ドロップゾーンのダミーテキストを実際のものに差し替え
src = src.replace(
    '<div style="font-size:0.9rem; margin-top:0.75rem; color: var(--text-muted);">読込完了: 1,240件 (06/01 - 06/15)</div>',
    '<div id="upload-status" style="font-size:0.9rem; margin-top:0.75rem; color: var(--text-muted);">読込完了: 待機中</div>\n'
    '                        <input type="file" id="file-input" hidden accept=".xlsx,.xls">'
)

# 4. 日付 input の固定値を削除（JSで今日をセット）
src = src.replace(
    '<input type="date" value="2026-06-01" style="width:100%; padding: 0.75rem;">',
    '<input type="date" id="base-date" style="width:100%; padding: 0.75rem;">\n'
    '                                <button class="btn-today" id="btn-today" type="button">本日</button>'
)

# 5. 「最適化を実行」ボタンの onclick を削除（script.js が addEventListener で処理）
src = src.replace(
    'onclick="startOptimization()"',
    'id="btn-run"'
)

# 6. ストーリーパネル Step1 の固定値 id を追加
src = src.replace(
    '>出荷対象: <strong id="val-items"',
    '>出荷対象: <strong id="val-items"'
)
# val-volume id 追加
src = src.replace(
    '(総体積: 約2,400m³)',
    '(総体積: 約<span id="val-volume">-</span>m³)'
)
# 理論値 id 追加
src = src.replace(
    '>40台<',
    '><span id="val-theoretical">40台</span><'
)
# グリーディ id 追加
src = src.replace(
    '>55台<',
    '><span id="val-greedy">55台</span><'
)
# 警告 id 追加
src = src.replace(
    '>警告: 理論値より15台オーバー<',
    '><span id="val-warning">警告: 理論値より15台オーバー</span><'
)
# step1 data id
src = src.replace(
    '<span style="font-size:0.7rem; color:var(--text-muted); margin-top:2px;">(2,400m³ ÷ 有効容積60m³ = 40)</span>',
    '<span style="font-size:0.7rem; color:var(--text-muted); margin-top:2px;" id="val-theoretical-note">(2,400m³ ÷ 有効容積60m³ = 40)</span>'
)

# 7. dp3-result に id 追加
src = src.replace(
    '隙間を極限まで減らし、全量を【51台】に収めるプランが完成しました！',
    '<span id="dp3-result">隙間を極限まで減らし、全量を【51台】に収めるプランが完成しました！</span>'
)

# 8. Step3 結果の固定値に id 追加
src = src.replace(
    '>55台<', '><span id="r3-greedy-count">55台</span><', 1
)
src = src.replace(
    '>51<span style="font-size:0.9rem; margin-left:2px;">台</span><',
    '><strong id="r3-final-count" style="font-size:1.6rem; color:var(--primary); line-height:1;">51<span style="font-size:0.9rem; margin-left:2px;">台</span></strong><'
)
src = src.replace(
    '>4台削減<',
    '><span id="r3-reduction" style="background:var(--success); color:white; padding:3px 8px; border-radius:4px; font-size:0.75rem; font-weight:bold; margin-left:0.25rem;">4台削減</span><'
)
src = src.replace(
    '>86.4<span style="font-size:0.9rem; margin-left:2px;">%</span><',
    '><strong id="r3-final-rate" style="font-size:1.6rem; color:var(--success); line-height:1;">86.4<span style="font-size:0.9rem; margin-left:2px;">%</span></strong><'
)
src = src.replace(
    '>高密度積載<',
    '><span id="r3-rate-label" style="font-size:0.75rem; font-weight:bold; margin-left:0.25rem; color:var(--success);">高密度積載</span><', 1
)

# 9. タイムラインの固定日付に id を追加
src = src.replace('>2026-05-28<', '><span id="tl-date1">2026-05-28</span><')
src = src.replace('>2026-06-04<', '><span id="tl-date2">2026-06-04</span><')
src = src.replace('>2026-06-11 ~ 2026-06-16<', '><span id="tl-date3">2026-06-11 ~ 2026-06-16</span><')
src = src.replace('>2026-06-18<', '><span id="tl-date4">2026-06-18</span><')

# 10. フィルターボタンに件数 id を追加
src = src.replace(
    '>すべて表示 (3)<',
    '>すべて表示 (<span id="filter-count-all">0</span>)<'
)
src = src.replace(
    '>出荷必須 (1)<',
    '>目標未達 (<span id="filter-count-alert">0</span>)<'
)
src = src.replace(
    '>出荷OK (2)<',
    '>出荷可 (<span id="filter-count-ok">0</span>)<'
)
# 3つ目のフィルター（見送り候補）は削除  
src = src.replace(
    '<button class="filter-btn" onclick="filterCards(\'delay\', this)" style="background:transparent; border:1px solid #cbd5e1; color:#64748b; border-radius:99px; padding:0.3rem 0.8rem; font-size:0.8rem; font-weight:bold; cursor:pointer;">見送り候補 (0)</button>',
    ''
)

# 11. コンテナグリッドの固定カードを空にして JS で生成
# container-grid の中身だけ削除（JS で renderCards する）
src = re.sub(
    r'(<div class="container-grid list-view" style="padding: 0 16px 16px 16px;">)(.*?)(</div>\s*</div>\s*</div>\s*</main>)',
    r'\1\n                    <!-- カードはJSで動的生成 -->\n                \3',
    src,
    flags=re.DOTALL
)

# 12. モーダルを ui_test.html のモック → script.js の 3D 描画用に置換
old_modal = re.search(r'<!-- ミクロ画面.*?</div>\s*</div>\s*</div>', src, re.DOTALL)
new_modal = """    <!-- 3D モーダル -->
    <div class="modal-overlay" id="modal-3d">
        <div class="modal-content">
            <div class="modal-header">
                <div><h3 id="modal-title">3Dレイアウト</h3></div>
                <div class="legend" id="color-legend-normal">
                    <span><span style="color:#3b82f6;">■</span> 通常</span>
                    <span><span style="color:#10b981;">■</span> 空き埋め</span>
                    <span><span style="color:#ef4444;">■</span> 強制出荷</span>
                    <span><span style="color:#ff0000; font-size:1.1em;">●</span> 重心</span>
                </div>
                <div style="margin-left:auto;">
                    <button id="toggle-color-mode" class="btn-ghost" style="padding:4px 8px; font-size:12px;">🎨 仕向け地で色分け</button>
                </div>
                <button class="modal-close" onclick="close3D()">&times;</button>
            </div>
            <div class="modal-body" id="3d-container">
                <div class="stats-overlay" id="3d-stats-overlay"></div>
                <div class="tooltip-3d" id="3d-tooltip"></div>
            </div>
        </div>
    </div>"""

if old_modal:
    src = src[:old_modal.start()] + new_modal + src[old_modal.end():]

# 13. 既存の <script> ブロックを全て除去し、script.js の読み込みに置換
src = re.sub(r'<script>.*?</script>', '', src, flags=re.DOTALL)
# </body> の直前に script.js を挿入
src = src.replace('</body>', '\n<script src="script.js?v=3"></script>\n</body>')

# 14. filter-bar の filter-btn を正規化 (must-ship -> alert, ok -> ok)
src = src.replace("filterCards('must-ship'", "filterCards('alert'")

# 書き出し (UTF-8 BOM なし)
with open('static/index.html', 'w', encoding='utf-8', newline='\n') as f:
    f.write(src)

print('Done! index.html written.')
# 検証
with open('static/index.html', 'r', encoding='utf-8') as f:
    out = f.read()
print('Japanese OK:', '最適化' in out)
print('val-items OK:', 'id="val-items"' in out)
print('btn-run OK:', 'id="btn-run"' in out)
print('script.js OK:', 'script.js?v=3' in out)
print('Lines:', out.count('\n'))
