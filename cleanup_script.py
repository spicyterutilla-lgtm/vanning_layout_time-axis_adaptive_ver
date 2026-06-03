import re

filepath = r'c:\Users\goat\ソリューション開発Ⅰ\vanning_layout_time-axis_adaptive_ver\static\script.js'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Remove addOptimizationLog
content = re.sub(r'function addOptimizationLog\(.*?\)\s*\{.*?\n\}\n', '', content, flags=re.DOTALL)
# Remove renderOptimizationTabs
content = re.sub(r'function renderOptimizationTabs\(\)\s*\{.*?\n\}\n', '', content, flags=re.DOTALL)
# Remove runDeepOptimization
content = re.sub(r'async function runDeepOptimization\(\)\s*\{.*?\n\}\n', '', content, flags=re.DOTALL)

# Remove variables
content = re.sub(r'let optimizationHistory = \[\];\nlet currentOptimizationIndex = 0;\n', '', content)
content = re.sub(r'optimizationHistory = \[.*?\];\n\s*currentOptimizationIndex = 0;\n\s*renderOptimizationTabs\(\);\n', '', content, flags=re.DOTALL)
content = re.sub(r'addOptimizationLog\(.*?\);\n', '', content)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print("done")
