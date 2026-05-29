import re

# Read both files
with open('static/index.html', 'r', encoding='utf-8') as f:
    idx_text = f.read()
    
with open('static/ui_test.html', 'r', encoding='utf-8') as f:
    ui_text = f.read()

# Extract new modal from ui_test.html
# It starts at `<div class="modal-overlay" id="modal-test"` and ends at the closing div before `<script>`
start_idx = ui_text.find('<div class="modal-overlay" id="modal-test"')
end_idx = ui_text.find('</script>', start_idx)
# Find the exact closing div for modal-overlay
# Let's just use string parsing to get the modal block up to line 998
modal_lines = ui_text.split('\n')[894:998]
new_modal_html = '\n'.join(modal_lines)

# Now, we need to adapt the new_modal_html for our actual system.
# We replace id="modal-test" with id="modal-3d"
new_modal_html = new_modal_html.replace('id="modal-test"', 'id="modal-3d"')
new_modal_html = new_modal_html.replace("getElementById('modal-test')", "close3D()")

# Replace the hardcoded `C-005` title with a dynamic span
new_modal_html = new_modal_html.replace(
    '<h3 style="margin:0; font-size:1.2rem;">C-005 <span',
    '<h3 style="margin:0; font-size:1.2rem;" id="modal-title">C-005 <span'
)

# In the left side, replace the mock `.iso-container` with our real `#3d-container`
# The mock iso-container is:
mock_iso = """                        <div class="iso-container">
                            <span style="color:#94a3b8; font-weight:700; font-size:1.5rem; position:absolute; top:-30px;">C-005 Area</span>
                            <div class="iso-item" id="iso-red"></div>
                            <div class="iso-item pull" id="iso-green"></div>
                        </div>"""

real_3d = """                        <div id="3d-container" style="flex:1; width:100%; position:relative; min-height: 400px; display:flex; justify-content:center; align-items:center;">
                            <div class="stats-overlay" id="3d-stats-overlay"></div>
                            <div class="tooltip-3d" id="3d-tooltip"></div>
                        </div>"""

new_modal_html = new_modal_html.replace(mock_iso, real_3d)

# In the sidebar, give the `drag-list` an ID so we can inject items
new_modal_html = new_modal_html.replace(
    '<div class="drag-list">',
    '<div class="drag-list" id="modal-drag-list">'
)

# And clear the hardcoded drag items inside `modal-drag-list`
drag_list_start = new_modal_html.find('<div class="drag-list" id="modal-drag-list">')
drag_list_end = new_modal_html.find('</div>', new_modal_html.find('<!-- Drag Item 3 -->') + 200) # This is sloppy, let's just use regex

new_modal_html = re.sub(
    r'<div class="drag-list" id="modal-drag-list">.*?</div>\s*<div style="font-size: 0\.75rem;',
    '<div class="drag-list" id="modal-drag-list"></div>\n                        <div style="font-size: 0.75rem;',
    new_modal_html,
    flags=re.DOTALL
)

# Add the color mode button to the top of the workspace-3d
new_modal_html = new_modal_html.replace(
    '👁️ 透過モード</button>',
    '👁️ 透過モード</button>\n                            <button id="toggle-color-mode" class="btn-ghost" style="background:white; font-size: 0.8rem; padding: 6px 12px;">🎨 仕向け地で色分け</button>'
)

# Now find the old modal-3d in index.html and replace it
old_modal_start = idx_text.find('<!-- 3D モーダル -->')
old_modal_end = idx_text.find('</div>\n</div>\n\n<script src="script.js?v=3"></script>')

if old_modal_start != -1 and old_modal_end != -1:
    final_html = idx_text[:old_modal_start] + '<!-- 3D モーダル (新UI) -->\n' + new_modal_html + '\n    ' + idx_text[old_modal_end:]
    with open('static/index.html', 'w', encoding='utf-8') as f:
        f.write(final_html)
    print("Successfully replaced modal in index.html")
else:
    print("Could not find old modal bounds in index.html")
