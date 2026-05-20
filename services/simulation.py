import copy
import datetime
import os
import pandas as pd
from services.session import CASE_MASTER_FILE, CASE_MASTER_CACHE
from services.validation import classify_items_for_day
from services.session import reset_runtime_state
from vanning_engine import VanningEngine, VOLUME_TARGET_RATE

def read_generation_parameters(filepath):
    try:
        df = pd.read_excel(filepath, sheet_name="生成パラメータ")
    except Exception:
        return {}

    params = {}
    for _, row in df.iterrows():
        key = str(row.get("項目", "")).strip()
        if key:
            params[key] = row.get("値", "")
    return params

def coerce_float(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None

def parameter_rate_to_percent(value):
    numeric = coerce_float(value)
    if numeric is None:
        return None
    return round(numeric * 100, 1) if 0 <= numeric <= 1 else round(numeric, 1)

def safe_rate(count, total):
    return round((count / total) * 100, 1) if total else 0

def build_simulation_context(items, input_profile=None, generation_parameters=None):
    if not items:
        return None

    input_profile = input_profile or {}
    generation_parameters = generation_parameters or {}
    total = len(items)
    today = datetime.date.today()
    due_dates = [item.due_date for item in items if item.due_date]
    weights = [item.weight for item in items if item.weight is not None]

    wood_deadline_count = sum(1 for item in items if item.expiration_date)
    future_count = sum(1 for item in items if item.creation_date > today)
    arrived_count = total - future_count
    is_generated = bool(input_profile.get("generated_simulation"))
    detected = input_profile.get("detected_columns", {})
    if is_generated:
        source_rows = [
            {"item": "ケース寸法・箱タイプ", "status": "開示資料ベース", "basis": "ケースマスタ", "note": "いすゞロジスティック開示ケースリストの寸法を使用"},
            {"item": "重量", "status": "仮定", "basis": "重量密度レンジ", "note": "先方回答が来たら実績重量・階級で差し替え"},
            {"item": "出現頻度", "status": "仮定", "basis": "ケース階級比率", "note": "実際の週次・月次出現比率で更新対象"},
            {"item": "積載可能日・納期", "status": "仮定", "basis": "日付分布", "note": "入荷日・納期分布の回答待ち"},
            {"item": "木箱期限", "status": "仮定", "basis": "木箱期限候補", "note": "木箱保管期限ルールの回答待ち"},
            {"item": "積み方", "status": "自動判定", "basis": "重量順・3D配置", "note": "重量が重い荷物を先に低い位置へ配置"},
        ]
        summary_note = "寸法は開示資料ベース、重量・頻度・日付は暫定仮定です。積み方は重量順で自動判定します。"
    else:
        source_rows = [
            {"item": "ケース寸法・品名", "status": "入力Excel", "basis": "L/W/H/名称", "note": "読み込んだExcelの値を使用"},
            {"item": "重量", "status": "入力Excel" if detected.get("weight") else "補完", "basis": "重量列", "note": "列がない場合は補完値のため要確認"},
            {"item": "積載可能日", "status": "入力Excel" if detected.get("creation") else "補完", "basis": "積載可能日/到着日", "note": "列がない場合は当日扱い"},
            {"item": "納期", "status": "入力Excel" if detected.get("due") else "補完", "basis": "納期", "note": "列がない場合は7日後扱い"},
            {"item": "木箱期限", "status": "入力Excel" if detected.get("expiration") else "補完", "basis": "木箱期限", "note": "列がない場合は木箱のみ補完"},
            {"item": "積み方", "status": "自動判定", "basis": "重量順・3D配置", "note": "重量が重い荷物を先に低い位置へ配置"},
        ]
        summary_note = "読み込んだExcelの主要列を優先し、積み方と前倒し候補は自動判定しています。"

    return {
        "is_generated": is_generated,
        "loaded_count": total,
        "generated_rows_setting": coerce_float(generation_parameters.get("生成行数")),
        "seed": str(generation_parameters.get("乱数シード", "")).strip(),
        "placement_policy": "重量が重い荷物を先に低い位置へ置き、体積80%を目標に補填します。",
        "wood_deadline_rate": safe_rate(wood_deadline_count, total),
        "arrived_rate": safe_rate(arrived_count, total),
        "future_rate": safe_rate(future_count, total),
        "due_min": min(due_dates).strftime("%Y-%m-%d") if due_dates else "",
        "due_max": max(due_dates).strftime("%Y-%m-%d") if due_dates else "",
        "avg_weight": round(sum(weights) / len(weights)) if weights else 0,
        "summary_note": summary_note,
        "source_rows": source_rows,
    }

def load_case_master_rows():
    project_root = os.path.dirname(os.path.dirname(__file__))
    case_path = os.path.join(project_root, CASE_MASTER_FILE)
    if not os.path.exists(case_path):
        raise FileNotFoundError(f"ケースマスタが見つかりません: {case_path}")

    case_mtime = os.path.getmtime(case_path)
    if (
        CASE_MASTER_CACHE["path"] == case_path
        and CASE_MASTER_CACHE["mtime"] == case_mtime
        and CASE_MASTER_CACHE["rows"] is not None
    ):
        return copy.deepcopy(CASE_MASTER_CACHE["rows"])

    df_raw = pd.read_excel(case_path, sheet_name=0, header=None)
    header_row_idx = 0
    for idx in range(min(10, len(df_raw))):
        values = {str(value).strip() for value in df_raw.iloc[idx].values if not pd.isna(value)}
        if {"分類", "資材名称", "L", "W", "H"}.issubset(values):
            header_row_idx = idx
            break

    df = pd.read_excel(case_path, sheet_name=0, header=header_row_idx)
    rows = []
    for _, row in df.iterrows():
        try:
            category = str(row["分類"]).strip()
            material_name = str(row["資材名称"]).strip()
            length = float(row["L"])
            width = float(row["W"])
            height = float(row["H"])
        except (KeyError, TypeError, ValueError):
            continue

        if not category or category == "nan" or not material_name or material_name == "nan":
            continue

        volume_m3 = (length * width * height) / 1_000_000_000
        footprint_m2 = (length * width) / 1_000_000
        rows.append({
            "分類": category,
            "No": row.get("№", row.get("No", "")),
            "資材名称": material_name,
            "L": int(length),
            "W": int(width),
            "H": int(height),
            "体積m3": round(volume_m3, 3),
            "床面積m2": round(footprint_m2, 3),
            "ケース階級": classify_case_profile(category, volume_m3, height),
        })

    if not rows:
        raise ValueError("ケースマスタから有効なケース寸法を読み取れませんでした。")
    CASE_MASTER_CACHE.update({"path": case_path, "mtime": case_mtime, "rows": copy.deepcopy(rows)})
    return rows

def classify_case_profile(category, volume_m3, height):
    if category == "木箱":
        if volume_m3 >= 8.0 or height >= 1800:
            return "大型木箱/特殊木箱"
        return "標準木箱"
    if volume_m3 >= 4.5 or height >= 1400:
        return "大型スチール"
    if volume_m3 >= 2.0:
        return "中型スチール"
    return "小型スチール"

def weighted_choice(randomizer, weighted_values):
    total = sum(weight for _, weight in weighted_values)
    cursor = randomizer.uniform(0, total)
    upto = 0
    for value, weight in weighted_values:
        upto += weight
        if cursor <= upto:
            return value
    return weighted_values[-1][0]

def generate_case_based_simulation_rows(case_master, row_count=200, assumptions=None, seed=20260516):
    import random

    assumptions = assumptions or {}
    randomizer = random.Random(seed)
    today = datetime.date.today()
    class_weights = assumptions["class_weights"]
    density_ranges = assumptions["density_ranges"]
    density_mix = assumptions["density_mix"]
    weight_variation = assumptions["weight_variation"]
    max_item_weight_kg = assumptions["max_item_weight_kg"]
    arrival_distribution = [
        (bucket, bucket.get("weight", 0))
        for bucket in assumptions["arrival_distribution"]
        if bucket.get("weight", 0) > 0
    ]

    by_class = {}
    for case in case_master:
        by_class.setdefault(case["ケース階級"], []).append(case)
    available_classes = [(case_class, class_weights.get(case_class, 0.1)) for case_class in by_class]

    rows = []
    for index in range(1, row_count + 1):
        case_class = weighted_choice(randomizer, available_classes)
        case = randomizer.choice(by_class[case_class])
        density_class = weighted_choice(randomizer, density_mix[case_class])
        density_min, density_max = density_ranges[density_class]
        density = randomizer.uniform(density_min, density_max)
        weight = max(40, min(max_item_weight_kg, case["体積m3"] * density * randomizer.uniform(*weight_variation)))
        weight = round(weight / 10) * 10

        arrival_bucket = weighted_choice(randomizer, arrival_distribution)
        creation_offset = randomizer.randint(*arrival_bucket["offset_days"])

        due_offset = max(
            creation_offset + randomizer.randint(*assumptions["due_after_arrival_days"]),
            randomizer.randint(*assumptions["due_offset_days"])
        )
        creation_date = today + datetime.timedelta(days=creation_offset)
        due_date = today + datetime.timedelta(days=due_offset)

        is_wood = case["分類"] == "木箱"
        expiration_date = ""
        if is_wood:
            expiration_offset = max(due_offset, creation_offset + randomizer.choice(assumptions["wood_expiration_days"]))
            expiration_date = (today + datetime.timedelta(days=expiration_offset)).strftime("%Y-%m-%d")

        priority = next(
            row["priority"]
            for row in assumptions["priority_thresholds"]
            if due_offset <= row["due_days"]
        )
        item_name = f"ISZ-{case_class}-{case['資材名称']}-{index:04d}"

        rows.append({
            "品名": item_name,
            "ケース分類": case["分類"],
            "ケースNo": case["No"],
            "資材名称": case["資材名称"],
            "ケース階級": case_class,
            "L": case["L"],
            "W": case["W"],
            "H": case["H"],
            "体積m3": case["体積m3"],
            "重量": weight,
            "仮定重量階級": density_class,
            "積載可能日": creation_date.strftime("%Y-%m-%d"),
            "納期": due_date.strftime("%Y-%m-%d"),
            "木箱期限": expiration_date,
            "優先度": priority,
            "仮定根拠": "寸法は開示ケースリスト準拠。重量・頻度・納期は暫定仮定。積み方は重量順で自動判定。",
        })
    return rows

def build_case_class_summary_rows(case_master):
    summary = {}
    for case in case_master:
        case_class = case["ケース階級"]
        bucket = summary.setdefault(case_class, {
            "ケース階級": case_class,
            "件数": 0,
            "分類": set(),
            "最小体積m3": None,
            "最大体積m3": None,
            "平均体積m3": 0,
            "最小L": None,
            "最大L": None,
            "最小W": None,
            "最大W": None,
            "最小H": None,
            "最大H": None,
        })
        bucket["件数"] += 1
        bucket["分類"].add(case["分類"])
        bucket["平均体積m3"] += case["体積m3"]
        for source, min_key, max_key in [
            ("体積m3", "最小体積m3", "最大体積m3"),
            ("L", "最小L", "最大L"),
            ("W", "最小W", "最大W"),
            ("H", "最小H", "最大H"),
        ]:
            value = case[source]
            bucket[min_key] = value if bucket[min_key] is None else min(bucket[min_key], value)
            bucket[max_key] = value if bucket[max_key] is None else max(bucket[max_key], value)

    rows = []
    class_order = ["小型スチール", "中型スチール", "大型スチール", "標準木箱", "大型木箱/特殊木箱"]
    for case_class in class_order:
        if case_class not in summary:
            continue
        bucket = summary[case_class]
        rows.append({
            "ケース階級": bucket["ケース階級"],
            "件数": bucket["件数"],
            "分類": "/".join(sorted(bucket["分類"])),
            "最小体積m3": round(bucket["最小体積m3"], 3),
            "最大体積m3": round(bucket["最大体積m3"], 3),
            "平均体積m3": round(bucket["平均体積m3"] / bucket["件数"], 3),
            "L範囲": f"{int(bucket['最小L'])} - {int(bucket['最大L'])}",
            "W範囲": f"{int(bucket['最小W'])} - {int(bucket['最大W'])}",
            "H範囲": f"{int(bucket['最小H'])} - {int(bucket['最大H'])}",
        })
    return rows

def build_case_assumptions_rows(row_count=200):
    return [
        {"項目": "ケース寸法", "扱い": "開示資料ベース", "内容": "いすゞロジスティック開示資料「ケースリスト」のL/W/Hをケースマスタとして使用"},
        {"項目": "ケース種類", "扱い": "開示資料ベース", "内容": "木箱10種類、スチール21種類を保持し、生成時は5つのケース階級へ分類"},
        {"項目": "ケース階級", "扱い": "モデル化", "内容": "小型スチール/中型スチール/大型スチール/標準木箱/大型木箱・特殊木箱"},
        {"項目": "運用規模", "扱い": "先方回答", "内容": f"週に50〜100本のバンニングレイアウトを行う規模感。今回の生成行数は{row_count}件"},
        {"項目": "重量", "扱い": "仮定", "内容": "軽量・標準・重量物の密度レンジをケース体積に掛けて生成。先方回答が来たら差し替え対象"},
        {"項目": "出現頻度", "扱い": "仮定", "内容": "ケース階級ごとの発生比率を暫定設定。実績頻度が分かり次第、置き換え可能"},
        {"項目": "日別入荷量/納期分布", "扱い": "仮定", "内容": "30日ローリング検証用に、到着済み・近日到着・将来到着を混在させて生成"},
        {"項目": "木箱期限", "扱い": "仮定", "内容": "木箱のみ、積載可能日から14/21/28日のいずれかで暫定付与し、納期より前には置かない"},
        {"項目": "積み方", "扱い": "自動判定", "内容": "床置き・段積み可否・分離制約は入力項目にせず、重量が重い荷物から低い位置へ配置"},
        {"項目": "赤字判定", "扱い": "業務ルール", "内容": "体積充填率80%未満を赤字候補として評価。重量充填率は安全制約として扱う"},
    ]