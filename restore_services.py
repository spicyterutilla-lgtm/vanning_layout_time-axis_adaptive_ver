import ast

with open('app.py', 'r', encoding='utf-8') as f:
    source = f.read()

tree = ast.parse(source)

simulation_funcs = [
    "coerce_float", "parameter_rate_to_percent", "safe_rate",
    "build_simulation_context", "read_generation_parameters",
    "load_case_master_rows", "classify_case_profile", "weighted_choice",
    "generate_case_based_simulation_rows", "build_case_class_summary_rows",
    "build_case_assumptions_rows"
]

rolling_funcs = [
    "run_rolling_simulation", "rolling_planning_candidates",
    "rolling_result_score", "summarize_rolling_trial",
    "run_adaptive_rolling_simulation", "build_rolling_comparison",
    "run_single_day_scenario", "single_day_scenario_score"
]

sim_blocks = []
rol_blocks = []

class FuncVisitor(ast.NodeVisitor):
    def visit_FunctionDef(self, node):
        if node.name in simulation_funcs:
            lines = source.split('\n')[node.lineno-1:node.end_lineno]
            sim_blocks.append('\n'.join(lines))
        elif node.name in rolling_funcs:
            lines = source.split('\n')[node.lineno-1:node.end_lineno]
            rol_blocks.append('\n'.join(lines))
        self.generic_visit(node)

visitor = FuncVisitor()
visitor.visit(tree)

sim_header = """import copy
import datetime
import os
import pandas as pd
from services.session import CASE_MASTER_FILE, CASE_MASTER_CACHE
from services.validation import classify_items_for_day
from services.session import reset_runtime_state
from vanning_engine import VanningEngine, VOLUME_TARGET_RATE

"""

rol_header = """import copy
import datetime
from services.session import SESSION_DATA, ROLLING_PLANNING_WINDOW_DAYS, ROLLING_FORCE_SHIP_WINDOW_DAYS, ROLLING_PLANNING_WINDOW_CANDIDATES
from services.validation import classify_items_for_day
from services.session import reset_runtime_state
from services.utils import build_remaining_risks, summarize_containers
from vanning_engine import VanningEngine, VOLUME_TARGET_RATE

"""

with open('services/simulation.py', 'w', encoding='utf-8') as f:
    f.write(sim_header + '\n\n'.join(sim_blocks))

with open('services/rolling.py', 'w', encoding='utf-8') as f:
    f.write(rol_header + '\n\n'.join(rol_blocks))
