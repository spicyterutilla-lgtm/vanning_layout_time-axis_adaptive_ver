import re

with open('static/index.html', 'r', encoding='utf-8') as f:
    html = f.read()
with open('static/script.js', 'r', encoding='utf-8') as f:
    js = f.read()

js_ids = set(re.findall(r"getElementById\(['\"](.*?)['\"]\)", js))
html_ids = set(re.findall(r"id=['\"](.*?)['\"]", html))

missing = js_ids - html_ids
# ignore dynamically created ones
ignore = {'ai-loading-text', 'ai-timer'}
missing = missing - ignore

if missing:
    print('Missing IDs in HTML that JS expects:', missing)
else:
    print('All good!')
