import copy
import json
import os


DEFAULT_SIMULATION_ASSUMPTIONS = {
    "class_weights": {
        "小型スチール": 0.18,
        "中型スチール": 0.34,
        "大型スチール": 0.18,
        "標準木箱": 0.24,
        "大型木箱/特殊木箱": 0.06,
    },
    "density_ranges": {
        "軽量": [80, 160],
        "標準": [180, 320],
        "重量物": [420, 700],
    },
    "density_mix": {
        "小型スチール": [["軽量", 0.15], ["標準", 0.50], ["重量物", 0.35]],
        "中型スチール": [["軽量", 0.15], ["標準", 0.45], ["重量物", 0.40]],
        "大型スチール": [["軽量", 0.20], ["標準", 0.35], ["重量物", 0.45]],
        "標準木箱": [["軽量", 0.30], ["標準", 0.45], ["重量物", 0.25]],
        "大型木箱/特殊木箱": [["軽量", 0.35], ["標準", 0.35], ["重量物", 0.30]],
    },
    "arrival_distribution": [
        {"label": "到着済み", "weight": 0.68, "offset_days": [-21, 0]},
        {"label": "近日到着", "weight": 0.20, "offset_days": [1, 10]},
        {"label": "将来到着", "weight": 0.12, "offset_days": [11, 28]},
    ],
    "due_offset_days": [1, 42],
    "due_after_arrival_days": [3, 28],
    "wood_expiration_days": [14, 21, 28],
    "max_item_weight_kg": 21500,
    "weight_variation": [0.90, 1.15],
    "allow_early_ship_probability": 0.86,
    "separation_probability": 0.07,
    "separation_groups": ["危険物A", "精密部品B", "混載注意C"],
    "stackable_unavailable_probability": {
        "大型木箱/特殊木箱": 0.35,
        "大型スチール": 0.35,
        "木箱": 0.18,
    },
    "floor_only_probability": {
        "重量物": 0.35,
        "大型木箱/特殊木箱": 0.50,
    },
    "priority_thresholds": [
        {"due_days": 7, "priority": 70},
        {"due_days": 14, "priority": 55},
        {"due_days": 999, "priority": 40},
    ],
}


def deep_merge(default_value, override_value):
    if isinstance(default_value, dict) and isinstance(override_value, dict):
        merged = copy.deepcopy(default_value)
        for key, value in override_value.items():
            merged[key] = deep_merge(merged[key], value) if key in merged else copy.deepcopy(value)
        return merged
    return copy.deepcopy(override_value)


def load_simulation_assumptions(path):
    assumptions = copy.deepcopy(DEFAULT_SIMULATION_ASSUMPTIONS)
    if not os.path.exists(path):
        return assumptions

    with open(path, "r", encoding="utf-8") as handle:
        override = json.load(handle)
    return deep_merge(assumptions, override)


def build_generation_parameter_rows(assumptions, row_count, seed):
    rows = [
        {
            "区分": "生成条件",
            "項目": "生成行数",
            "値": row_count,
            "扱い": "設定値",
            "説明": "シミュレーションデータシートに生成する荷物件数",
        },
        {
            "区分": "生成条件",
            "項目": "乱数シード",
            "値": seed,
            "扱い": "設定値",
            "説明": "同じ前提で同じデータを再現するための固定値",
        },
    ]

    for case_class, weight in assumptions.get("class_weights", {}).items():
        rows.append({
            "区分": "ケース出現頻度",
            "項目": case_class,
            "値": weight,
            "扱い": "仮定",
            "説明": "ケース階級ごとの相対出現比率",
        })

    for label, values in assumptions.get("density_ranges", {}).items():
        rows.append({
            "区分": "重量密度",
            "項目": label,
            "値": f"{values[0]} - {values[1]} kg/m3",
            "扱い": "仮定",
            "説明": "ケース体積に掛けて重量を生成する密度レンジ",
        })

    for case_class, mix in assumptions.get("density_mix", {}).items():
        rows.append({
            "区分": "重量階級ミックス",
            "項目": case_class,
            "値": " / ".join(f"{label}:{weight}" for label, weight in mix),
            "扱い": "仮定",
            "説明": "ケース階級ごとの軽量・標準・重量物の発生比率",
        })

    for bucket in assumptions.get("arrival_distribution", []):
        rows.append({
            "区分": "積載可能日分布",
            "項目": bucket.get("label", ""),
            "値": f"重み {bucket.get('weight')} / {bucket.get('offset_days', ['',''])[0]}〜{bucket.get('offset_days', ['',''])[1]}日",
            "扱い": "仮定",
            "説明": "基準日から見た現場到着タイミング",
        })

    rows.extend([
        {
            "区分": "納期分布",
            "項目": "納期オフセット",
            "値": f"{assumptions['due_offset_days'][0]} - {assumptions['due_offset_days'][1]}日",
            "扱い": "仮定",
            "説明": "基準日から見た納期の暫定範囲",
        },
        {
            "区分": "木箱期限",
            "項目": "木箱期限候補",
            "値": " / ".join(str(v) for v in assumptions.get("wood_expiration_days", [])),
            "扱い": "仮定",
            "説明": "木箱の保管期限を積載可能日から何日後に置くか",
        },
        {
            "区分": "制約",
            "項目": "前倒し可率",
            "値": assumptions.get("allow_early_ship_probability"),
            "扱い": "仮定",
            "説明": "納期前の荷物を赤字回避の補填候補にできる割合",
        },
        {
            "区分": "制約",
            "項目": "分離制約発生率",
            "値": assumptions.get("separation_probability"),
            "扱い": "仮定",
            "説明": "混載注意などの分離グループを付与する割合",
        },
    ])
    return rows
