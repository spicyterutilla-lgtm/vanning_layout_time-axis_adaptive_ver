import os

# 簡易的なオンメモリセッション（プロトタイプ用）
SESSION_DATA = {"items": [], "validation_issues": [], "invalid_item_ids": set()}
SYSTEM_STATUS_KEYWORDS = ("前倒し", "保留プール", "赤字強制出荷")
ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
ROLLING_PLANNING_WINDOW_DAYS = 7
ROLLING_FORCE_SHIP_WINDOW_DAYS = 0
ROLLING_PLANNING_WINDOW_CANDIDATES = (0, 3, 5, 7, 10, 14, 21)
CASE_MASTER_FILE = "(抜粋)ケースリスト.xlsx"
SIMULATION_ASSUMPTIONS_FILE = "simulation_assumptions.json"
CASE_MASTER_CACHE = {"path": None, "mtime": None, "rows": None}

def clear_last_results():
    for key in ("last_containers", "last_rolling", "last_review_queue", "last_scenarios"):
        SESSION_DATA.pop(key, None)

def reset_runtime_state(items):
    """再計算前に、前回の配置結果とシステム判定だけをクリアする。"""
    for item in items:
        item.x = item.y = item.z = None
        item.is_rotated = False
        item.selection_reason = ""
        item.decision_reason = ""
        if hasattr(item, "system_force_ship"):
            item.system_force_ship = False

        if any(keyword in str(item.status_msg) for keyword in SYSTEM_STATUS_KEYWORDS):
            item.status_msg = ""

        if item.force_ship and not item.status_msg:
            item.status_msg = "手動オーバーライド：現場指示による強制出荷"

def build_valid_items():
    items = SESSION_DATA.get("items", [])
    invalid_item_ids = SESSION_DATA.get("invalid_item_ids", set())
    return [item for item in items if item.id not in invalid_item_ids], invalid_item_ids
