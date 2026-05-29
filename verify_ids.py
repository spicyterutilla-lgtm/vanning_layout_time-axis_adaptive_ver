import re

with open('static/index.html', 'r', encoding='utf-8') as f:
    html = f.read()
with open('static/script.js', 'r', encoding='utf-8') as f:
    js = f.read()

# find all getElementById in js
js_ids = re.findall(r"getElementById\(['\"](.*?)['\"]\)", js)
js_ids = set(js_ids)

# find all id= in html
html_ids = re.findall(r"id=['\"](.*?)['\"]", html)
html_ids = set(html_ids)

missing = js_ids - html_ids
if missing:
    print('Missing IDs in HTML that JS expects:', missing)
else:
    print('All good!')
