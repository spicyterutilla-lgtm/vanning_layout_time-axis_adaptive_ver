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

def build_simulation_context(items, input_profile=None, generation_parameters=None, dataset_kind="standard", source_filename=""):
    if not items:
        return None

    input_profile = input_profile or {}
    generation_parameters = generation_parameters or {}
    total = len(items)
    today = datetime.date.today()
    due_dates = [item.due_date for item in items if item.due_date]
    weights = [item.weight for item in items if item.weight is not None]

    evaluation_date = today
    vanning_end_parameter = str(generation_parameters.get("バンニング完了期限", "")).strip()
    if vanning_end_parameter:
        try:
            evaluation_date = datetime.datetime.strptime(vanning_end_parameter, "%Y-%m-%d").date()
        except ValueError:
            evaluation_date = today
    wood_deadline_count = sum(1 for item in items if item.expiration_date)
    future_count = sum(1 for item in items if item.creation_date > evaluation_date)
    arrived_count = total - future_count
    is_generated = bool(input_profile.get("generated_simulation"))
    is_trial = dataset_kind == "trial" or bool(input_profile.get("trial_dataset"))
    detected = input_profile.get("detected_columns", {})
    if is_trial:
        source_rows = [
            {"item": "データ区分", "status": "試験データ", "basis": "別枠読込", "note": "標準シミュレーションデータを置き換えず、確認用として計算"},
            {"item": "ケース寸法・重量", "status": "入力Excel", "basis": "L/W/H/重量", "note": "送付された貨物リストの入力値をそのまま使用"},
            {"item": "納入予定日", "status": "入力Excel" if detected.get("creation") else "補完", "basis": "積載可能日/納入予定日", "note": "積載可能日を納入予定日として評価"},
            {"item": "積込期限", "status": "入力Excel" if detected.get("due") else "補完", "basis": "納期/バンニング完了期限", "note": "納期を積込期限として評価"},
            {"item": "積み方", "status": "自動判定", "basis": "底面優先・3D配置", "note": "水平方向90度回転と重量上下制約を適用"},
        ]
        summary_note = "試験データとして別枠で読み込んだ入力Excelによる結果です。標準シミュレーションデータや先方回答ベースの生成条件とは混同せず、確認用として扱います。"
    elif is_generated:
        source_rows = [
            {"item": "ケース寸法・箱タイプ", "status": "開示資料ベース", "basis": "ケースマスタ", "note": "いすゞロジスティック開示ケースリストの寸法を使用"},
            {"item": "計画工程", "status": "先方回答ベース", "basis": "船積日からのリードタイム", "note": "情報受領は約3週間前、レイアウト確定は約2週間前、積込みは約1週間前から2日前まで"},
            {"item": "管理項目", "status": "項目は先方回答", "basis": "開示回答", "note": "仕向け地・部品コード・車両コード・梱包前後重量・依頼コード等を追加。値は匿名サンプル"},
            {"item": "重量", "status": "採用仮定", "basis": "重量密度レンジ", "note": "実値非開示のため、検証条件として密度レンジから生成"},
            {"item": "出現頻度", "status": "採用仮定", "basis": "ケース階級比率", "note": "実績頻度非開示のため、週次規模検証用の比率を採用"},
            {"item": "納入予定日分布", "status": "採用仮定", "basis": "日付分布", "note": "管理項目であることは回答済み。分布は検証条件として採用"},
            {"item": "木箱期限", "status": "採用仮定", "basis": "木箱期限候補", "note": "期限ルール非開示のため、14/21/28日を検証条件として採用"},
            {"item": "積み方", "status": "自動判定", "basis": "底面優先・3D配置", "note": "大きい底面を土台にし、上の荷物が下側より重くならないよう配置"},
        ]
        summary_note = "工程・管理項目の種類・運用規模は先方回答ベース、寸法は開示資料ベースです。非開示の重量・頻度・納入日分布・木箱期限は、明示した採用仮定で評価しています。"
    else:
        source_rows = [
            {"item": "ケース寸法・品名", "status": "入力Excel", "basis": "L/W/H/名称", "note": "読み込んだExcelの値を使用"},
            {"item": "重量", "status": "入力Excel" if detected.get("weight") else "補完", "basis": "重量列", "note": "列がない場合は補完値のため要確認"},
            {"item": "納入予定日", "status": "入力Excel" if detected.get("creation") else "補完", "basis": "納入予定日/積載可能日/到着日", "note": "列がない場合は当日扱い"},
            {"item": "積込期限", "status": "入力Excel" if detected.get("due") else "補完", "basis": "バンニング完了期限/納期", "note": "列がない場合は7日後扱い"},
            {"item": "木箱期限", "status": "入力Excel" if detected.get("expiration") else "補完", "basis": "木箱期限", "note": "列がない場合は木箱のみ補完"},
            {"item": "積み方", "status": "自動判定", "basis": "底面優先・3D配置", "note": "大きい底面を土台にし、上の荷物が下側より重くならないよう配置"},
        ]
        summary_note = "読み込んだExcelの主要列を優先し、積み方と追加積載候補は自動判定しています。"

    return {
        "is_generated": is_generated,
        "is_trial": is_trial,
        "dataset_kind": dataset_kind,
        "dataset_label": "試験データ" if is_trial else "標準データ",
        "source_filename": source_filename,
        "loaded_count": total,
        "generated_rows_setting": coerce_float(generation_parameters.get("生成行数")),
        "seed": str(generation_parameters.get("乱数シード", "")).strip(),
        "assumption_profile_name": str(generation_parameters.get("前提プロファイル名", "")).strip(),
        "assumption_profile_version": str(generation_parameters.get("前提バージョン", "")).strip(),
        "assumption_policy": str(generation_parameters.get("非開示値の扱い", "")).strip(),
        "cargo_information_date": str(generation_parameters.get("出荷情報受領日", "")).strip(),
        "layout_confirmation_date": str(generation_parameters.get("レイアウト確定期限", "")).strip(),
        "vanning_start_date": str(generation_parameters.get("バンニング開始日", "")).strip(),
        "vanning_end_date": str(generation_parameters.get("バンニング完了期限", "")).strip(),
        "vessel_loading_date": str(generation_parameters.get("船積日", "")).strip(),
        "recommended_base_date": str(generation_parameters.get("出荷情報受領日", "")).strip(),
        "availability_reference_label": "完了期限時点" if is_generated and vanning_end_parameter else "本日時点",
        "placement_policy": "大きい底面を土台にし、上側が下側より重くならない配置で体積80%を目標にします。",
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

def build_planning_dates(assumptions, planning_date=None):
    info_date = planning_date or datetime.date.today()
    timeline = assumptions.get("planning_timeline", {})
    cargo_lead = int(timeline.get("cargo_information_lead_days", 21))
    layout_lead = int(timeline.get("layout_confirmation_lead_days", 14))
    vanning_start_lead = int(timeline.get("vanning_start_lead_days", 7))
    vanning_end_lead = int(timeline.get("vanning_end_lead_days", 2))
    
    vessel_loading_date = info_date + datetime.timedelta(days=cargo_lead)
    
    return {
        "出荷情報受領日": info_date,
        "レイアウト確定期限": vessel_loading_date - datetime.timedelta(days=layout_lead),
        "バンニング開始日": vessel_loading_date - datetime.timedelta(days=vanning_start_lead),
        "バンニング完了期限": vessel_loading_date - datetime.timedelta(days=vanning_end_lead),
        "船積日": vessel_loading_date,
    }

def generate_case_based_simulation_rows(case_master, row_count=800, assumptions=None, seed=20260516, planning_dates=None):
    import random

    assumptions = assumptions or {}
    randomizer = random.Random(seed)
    planning_dates = planning_dates or build_planning_dates(assumptions)
    vanning_start_date = planning_dates["バンニング開始日"]
    vanning_end_date = planning_dates["バンニング完了期限"]
    vessel_loading_date = planning_dates["船積日"]
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
        creation_date = vanning_start_date + datetime.timedelta(days=creation_offset)
        due_date = vanning_end_date

        is_wood = case["分類"] == "木箱"
        expiration_date = ""
        if is_wood:
            expiration_date_value = max(
                due_date,
                creation_date + datetime.timedelta(days=randomizer.choice(assumptions["wood_expiration_days"]))
            )
            expiration_date = expiration_date_value.strftime("%Y-%m-%d")

        priority = 70 if creation_date > vanning_end_date else 50
        item_name = f"ISZ-{case_class}-{case['資材名称']}-{index:04d}"
        packed_weight = weight
        unpacked_weight = max(10, round((packed_weight * 0.95) / 10) * 10)

        rows.append({
            "依頼コード": f"REQ-{vessel_loading_date.strftime('%Y%m%d')}-{index:04d}",
            "出荷者名": "サンプル出荷者-01",
            "受取者名": "サンプル受取者-01",
            "仕向け地": "サンプル仕向地-01",
            "部品コード": f"PART-{index:05d}",
            "車両コード": f"VEH-{((index - 1) % 5) + 1:02d}",
            "品名": item_name,
            "ケース分類": case["分類"],
            "ケースNo": case["No"],
            "資材名称": case["資材名称"],
            "ケース階級": case_class,
            "L": case["L"],
            "W": case["W"],
            "H": case["H"],
            "体積m3": case["体積m3"],
            "梱包前重量": unpacked_weight,
            "梱包後重量": packed_weight,
            "仮定重量階級": density_class,
            "出荷情報受領日": planning_dates["出荷情報受領日"].strftime("%Y-%m-%d"),
            "レイアウト確定期限": planning_dates["レイアウト確定期限"].strftime("%Y-%m-%d"),
            "納入予定日": creation_date.strftime("%Y-%m-%d"),
            "バンニング開始日": vanning_start_date.strftime("%Y-%m-%d"),
            "バンニング完了期限": vanning_end_date.strftime("%Y-%m-%d"),
            "船積日": vessel_loading_date.strftime("%Y-%m-%d"),
            "木箱期限": expiration_date,
            "優先度": priority,
            "仮定根拠": "工程と管理項目は先方回答準拠。寸法は開示資料準拠。非開示の重量・頻度・納入日分布・各コード値は検証用の採用仮定。",
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

def build_case_assumptions_rows(row_count=800):
    return [
        {"項目": "ケース寸法", "扱い": "開示資料ベース", "内容": "いすゞロジスティック開示資料「ケースリスト」のL/W/Hをケースマスタとして使用"},
        {"項目": "ケース種類", "扱い": "開示資料ベース", "内容": "木箱10種類、スチール21種類を保持し、生成時は5つのケース階級へ分類"},
        {"項目": "ケース階級", "扱い": "モデル化", "内容": "小型スチール/中型スチール/大型スチール/標準木箱/大型木箱・特殊木箱"},
        {"項目": "運用規模", "扱い": "先方回答", "内容": f"週に50〜100本のバンニングレイアウトを行う規模感。今回の生成行数は{row_count}件"},
        {"項目": "計画工程", "扱い": "先方回答", "内容": "船積日の約3週間前に貨物情報を受領し、約2週間前に船・必要コンテナ量・レイアウトを確定"},
        {"項目": "積込み期間", "扱い": "先方回答", "内容": "船積日の約1週間前から2日前までの間に毎日順次バンニングを実施"},
        {"項目": "管理項目", "扱い": "先方回答", "内容": "出荷者名/受取者名/仕向け地/部品コード/車両コード/梱包前重量/梱包後重量/依頼コード/納入予定日を保持"},
        {"項目": "非開示値の扱い", "扱い": "採用方針", "内容": "実値の追加開示を前提にせず、明示した検証用仮定を固定して結果を比較・説明する"},
        {"項目": "管理項目の値", "扱い": "採用仮定", "内容": "出荷者名・仕向け地・各コード等の値は匿名の検証用サンプルを採用"},
        {"項目": "重量", "扱い": "採用仮定", "内容": "実重量は非開示のため、梱包後重量は密度レンジから生成し、梱包前重量は梱包後重量の95%として採用"},
        {"項目": "出現頻度", "扱い": "採用仮定", "内容": "実績頻度は非開示のため、週50〜100本規模の検証に使用するケース階級比率を採用"},
        {"項目": "納入予定日分布", "扱い": "採用仮定", "内容": "納入予定日を管理することは先方回答済み。日ごとの発生分布と期限後納入率は検証用に採用"},
        {"項目": "木箱期限", "扱い": "採用仮定", "内容": "期限ルールは非開示のため、木箱のみ納入予定日から14/21/28日のいずれかを採用し、積込期限より前には置かない"},
        {"項目": "積み方", "扱い": "自動判定", "内容": "床置き・段積み可否・分離制約は入力項目にせず、大きい底面を土台にして上側が下側より重くならないよう配置"},
        {"項目": "赤字判定", "扱い": "業務ルール", "内容": "体積充填率80%未満を赤字候補として評価。重量充填率は安全制約として扱う"},
    ]
