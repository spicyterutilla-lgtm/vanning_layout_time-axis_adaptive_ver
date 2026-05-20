import ast

with open('app.py', 'r', encoding='utf-8') as f:
    source = f.read()

tree = ast.parse(source)

funcs = ["read_generation_parameters", "build_simulation_context"]
code_blocks = []

class FuncVisitor(ast.NodeVisitor):
    def visit_FunctionDef(self, node):
        if node.name in funcs:
            start = node.lineno - 1
            end = node.end_lineno
            lines = source.split('\n')[start:end]
            code_blocks.append('\n'.join(lines))
        self.generic_visit(node)

visitor = FuncVisitor()
visitor.visit(tree)

with open('services/simulation.py', 'a', encoding='utf-8') as f:
    f.write('\n\n' + '\n\n'.join(code_blocks))
