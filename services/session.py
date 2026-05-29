import os

# 簡易的なオンメモリセッション
SESSION_DATA = {
    "items": [],
    "validation_issues": [],
    "invalid_item_ids": set(),
    "input_profile": {},
    "simulation_context": None,
}
SYSTEM_STATUS_KEYWORDS = ("前倒し", "保留プール", "赤字強制出荷")
ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
CASE_MASTER_FILE = "(抜粋)ケースリスト.xlsx"
SIMULATION_ASSUMPTIONS_FILE = "simulation_assumptions.json"
CASE_MASTER_CACHE = {"path": None, "mtime": None, "rows": None}

def clear_last_results():
    for key in (
        "last_containers", "last_review_queue",
        "last_optimization_summary", "last_alert_summaries", "last_base_date",
        "last_must_ship_window_days",
    ):
        SESSION_DATA.pop(key, None)

def reset_runtime_state(items):
    """計算前に強制出荷フラグ等のランタイム状態をリセットする"""
    for item in items:
        if not getattr(item, 'is_manual_force_ship', False):
            item.force_ship = False
            item.system_force_ship = False

def build_valid_items():
    items = SESSION_DATA.get("items", [])
    invalid_ids = SESSION_DATA.get("invalid_item_ids", set())
    valid = [i for i in items if i.id not in invalid_ids]
    return valid, invalid_ids
