import copy
import json
import os


DEFAULT_SIMULATION_ASSUMPTIONS = {
    "assumption_profile": {
        "name": "開示資料・回答ベース検証条件",
        "version": "v1.0 / 2026-05-26",
        "policy": "非開示の重量・頻度・納入日分布・木箱期限は、検証用の採用仮定として固定する",
    },
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
    "planning_timeline": {
        "cargo_information_lead_days": 14,
        "layout_confirmation_lead_days": 14,
        "vanning_start_lead_days": 7,
        "vanning_end_lead_days": 2,
    },
    "arrival_distribution": [
        {"label": "積込み開始時に納入済み", "weight": 0.68, "offset_days": [-7, 0]},
        {"label": "積込み期間中に納入", "weight": 0.20, "offset_days": [1, 5]},
        {"label": "完了期限後に納入予定", "weight": 0.12, "offset_days": [6, 10]},
    ],
    "wood_expiration_days": [14, 21, 28],
    "max_item_weight_kg": 21500,
    "weight_variation": [0.90, 1.15],
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
    timeline = assumptions.get("planning_timeline", {})
    profile = assumptions.get("assumption_profile", {})
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
        {
            "区分": "検証前提",
            "項目": "前提プロファイル名",
            "値": profile.get("name", "開示資料・回答ベース検証条件"),
            "扱い": "採用方針",
            "説明": "成果発表および比較検証で使用する前提条件の名称",
        },
        {
            "区分": "検証前提",
            "項目": "前提バージョン",
            "値": profile.get("version", "v1.0 / 2026-05-26"),
            "扱い": "採用方針",
            "説明": "同一条件で結果を再現するための前提バージョン",
        },
        {
            "区分": "検証前提",
            "項目": "非開示値の扱い",
            "値": profile.get("policy", ""),
            "扱い": "採用方針",
            "説明": "実値の追加開示を前提にせず、明示した仮定で評価する",
        },
        {
            "区分": "先方回答ベースの日程",
            "項目": "出荷情報受領",
            "値": f"船積日の約{timeline.get('cargo_information_lead_days', 21)}日前",
            "扱い": "先方回答",
            "説明": "量や宛先など、出荷予定貨物の情報を受け取る時期",
        },
        {
            "区分": "先方回答ベースの日程",
            "項目": "船・コンテナ数・レイアウト確定",
            "値": f"船積日の約{timeline.get('layout_confirmation_lead_days', 14)}日前",
            "扱い": "先方回答",
            "説明": "船の確定と必要コンテナの注文に合わせてレイアウトを決定する時期",
        },
        {
            "区分": "先方回答ベースの日程",
            "項目": "バンニング実施期間",
            "値": f"船積日の約{timeline.get('vanning_start_lead_days', 7)}日前〜{timeline.get('vanning_end_lead_days', 2)}日前",
            "扱い": "先方回答",
            "説明": "コンテナへの詰め込みを毎日順次実施する期間",
        },
    ]

    for case_class, weight in assumptions.get("class_weights", {}).items():
        rows.append({
            "区分": "ケース出現頻度",
            "項目": case_class,
            "値": weight,
            "扱い": "採用仮定",
            "説明": "非開示のため検証条件として採用するケース階級ごとの相対出現比率",
        })

    for label, values in assumptions.get("density_ranges", {}).items():
        rows.append({
            "区分": "重量密度",
            "項目": label,
            "値": f"{values[0]} - {values[1]} kg/m3",
            "扱い": "採用仮定",
            "説明": "非開示のため検証条件として採用する重量生成用の密度レンジ",
        })

    for case_class, mix in assumptions.get("density_mix", {}).items():
        rows.append({
            "区分": "重量階級ミックス",
            "項目": case_class,
            "値": " / ".join(f"{label}:{weight}" for label, weight in mix),
            "扱い": "採用仮定",
            "説明": "非開示のため検証条件として採用する軽量・標準・重量物の発生比率",
        })

    for bucket in assumptions.get("arrival_distribution", []):
        rows.append({
            "区分": "納入予定日分布",
            "項目": bucket.get("label", ""),
            "値": f"重み {bucket.get('weight')} / {bucket.get('offset_days', ['',''])[0]}〜{bucket.get('offset_days', ['',''])[1]}日",
            "扱い": "採用仮定",
            "説明": "バンニング開始日から見た納入予定日の検証用分布",
        })

    rows.extend([
        {
            "区分": "木箱期限",
            "項目": "木箱期限候補",
            "値": " / ".join(str(v) for v in assumptions.get("wood_expiration_days", [])),
            "扱い": "採用仮定",
            "説明": "非開示のため検証条件として採用する木箱保管期限の日数",
        },
        {
            "区分": "積み方",
            "項目": "配置方針",
            "値": "大底面優先・重量逆転禁止",
            "扱い": "自動判定",
            "説明": "床置き・段積み可否・分離制約は生成シートに持たせず、大きい底面を土台にして上側が下側より重くならないよう配置する",
        },
    ])
    return rows
