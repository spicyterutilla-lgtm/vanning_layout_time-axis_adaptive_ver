import ast

with open('app.py', 'r', encoding='utf-8') as f:
    source = f.read()

tree = ast.parse(source)

export_funcs = ["export_rolling_excel", "export_scenarios_excel", "export_excel"]
export_code = ""

# AST to get function code
class FuncVisitor(ast.NodeVisitor):
    def __init__(self, target_funcs):
        self.target_funcs = target_funcs
        self.code_blocks = []

    def visit_FunctionDef(self, node):
        if node.name in self.target_funcs:
            # We use the lines from the source
            start = node.lineno - 1
            end = node.end_lineno
            lines = source.split('\n')[start:end]
            
            # check decorators
            decorator_lines = []
            for dec in node.decorator_list:
                dec_start = dec.lineno - 1
                if dec_start < start:
                    start = dec_start
            
            lines = source.split('\n')[start:end]
            self.code_blocks.append('\n'.join(lines))
        self.generic_visit(node)

visitor = FuncVisitor(export_funcs)
visitor.visit(tree)

header = """import os
from io import BytesIO
import datetime
import pandas as pd
from flask import request, jsonify, send_file
from services.session import SESSION_DATA
from services.utils import build_container_alert_summary, build_item_brief

"""

with open('routes/export.py', 'w', encoding='utf-8') as f:
    f.write(header + '\n\n'.join(visitor.code_blocks))
