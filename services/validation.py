import datetime
from models import Container

def can_fit_container(item, container=None):
    container = container or Container(id="VALIDATION")
    if item.height > container.height or item.weight > container.max_weight:
        return False
    normal = item.length <= container.length and item.width <= container.width
    rotated = item.width <= container.length and item.length <= container.width
    return normal or rotated

def validate_items(items):
    issues = []
    invalid_item_ids = set()
    validation_container = Container(id="VALIDATION")

    for item in items:
        item_issues = []

        if item.length <= 0 or item.width <= 0 or item.height <= 0:
            item_issues.append(("error", "寸法が0以下です"))
        if item.weight <= 0:
            item_issues.append(("error", "重量が0以下です"))
        if item.due_date < item.creation_date:
            item_issues.append(("error", "納期が積載可能日より前です"))
        if item.expiration_date and item.expiration_date < item.creation_date:
            item_issues.append(("error", "保管期限が積載可能日より前です"))
        if not can_fit_container(item, validation_container):
            item_issues.append(("error", "有効内寸または最大重量を超えており積載できません"))

        if item.expiration_date and item.expiration_date < item.due_date:
            item_issues.append(("warning", "木箱期限が納期より前です"))

        for severity, message in item_issues:
            issues.append({
                "severity": severity,
                "item_id": item.id,
                "name": item.name,
                "message": message
            })
            if severity == "error":
                invalid_item_ids.add(item.id)

    return issues, invalid_item_ids

def build_validation_summary(issues):
    return {
        "errors": sum(1 for issue in issues if issue["severity"] == "error"),
        "warnings": sum(1 for issue in issues if issue["severity"] == "warning"),
        "total": len(issues)
    }

def build_data_readiness(input_profile, validation_issues):
    detected = (input_profile or {}).get("detected_columns", {})
    is_generated_simulation = bool((input_profile or {}).get("generated_simulation"))
    checks = [
        ("ケース寸法", True, "L/W/H/名称", "開示ケースマスタまたは入力Excelから取得"),
        ("重量", detected.get("weight", False), "重量列", "未入力の場合は1000kg補完または生成仮定になり、実務検証では要確認"),
        ("積載可能日", detected.get("creation", False), "積載可能日/到着日", "未入力の場合は当日扱いになり、時間軸評価が粗くなる"),
        ("納期", detected.get("due", False), "納期", "未入力の場合は7日後扱いになり、出荷判断の根拠が弱くなる"),
        ("木箱期限", detected.get("expiration", False), "木箱期限", "未入力の場合は木箱のみ21日補完または生成仮定"),
        ("積み方ロジック", True, "自動判定", "重量が重い荷物を先に低い位置へ置く"),
        ("前倒し候補", True, "自動判定", "現場にあり、期限に余裕がある荷物を補填候補にする"),
    ]
    rows = []
    ready_count = 0
    for item, ready, source, note in checks:
        if ready:
            ready_count += 1
        rows.append({
            "item": item,
            "status": "実データあり" if ready else "仮定/補完",
            "ready": ready,
            "source": source,
            "note": note,
        })

    score = round((ready_count / len(checks)) * 100, 1) if checks else 0
    if is_generated_simulation:
        score = min(score, 55.0)
        rows.insert(0, {
            "item": "データ性質",
            "status": "仮定シミュレーション",
            "ready": False,
            "source": "仮定根拠/仮定重量階級",
            "note": "開示ケース寸法を根拠にした検証用データ。重量・頻度・納期・制約は先方回答で差し替え対象",
        })
    risk_level = "実務検証向き" if score >= 80 else "要追加確認" if score >= 55 else "仮定検証向き"
    return {
        "score": score,
        "risk_level": risk_level,
        "checks": rows,
        "validation": build_validation_summary(validation_issues),
    }

def item_bounds(item):
    length = item.width if item.is_rotated else item.length
    width = item.length if item.is_rotated else item.width
    x = item.x if item.x is not None else 0
    y = item.y if item.y is not None else 0
    z = item.z if item.z is not None else 0
    return x, y, z, x + length, y + width, z + item.height

def ranges_overlap(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end

def boxes_overlap(a, b):
    ax1, ay1, az1, ax2, ay2, az2 = item_bounds(a)
    bx1, by1, bz1, bx2, by2, bz2 = item_bounds(b)
    return (
        ranges_overlap(ax1, ax2, bx1, bx2)
        and ranges_overlap(ay1, ay2, by1, by2)
        and ranges_overlap(az1, az2, bz1, bz2)
    )

def footprint_contains(support, item):
    sx1, sy1, _, sx2, sy2, sz2 = item_bounds(support)
    ix1, iy1, iz1, ix2, iy2, _ = item_bounds(item)
    return (
        abs(sz2 - iz1) < 0.001
        and sx1 <= ix1
        and sy1 <= iy1
        and sx2 >= ix2
        and sy2 >= iy2
    )

def validate_container_geometry(container):
    warnings = []
    for item in container.items:
        x1, y1, z1, x2, y2, z2 = item_bounds(item)
        if x1 < -0.001 or y1 < -0.001 or z1 < -0.001 or x2 > container.length + 0.001 or y2 > container.width + 0.001 or z2 > container.height + 0.001:
            warnings.append(f"{item.name}: コンテナ内寸外")
        if z1 > 0.001 and not any(footprint_contains(other, item) for other in container.items if other is not item):
            warnings.append(f"{item.name}: 底面支持なし")

    for idx, item in enumerate(container.items):
        for other in container.items[idx + 1:]:
            if boxes_overlap(item, other):
                warnings.append(f"{item.name} / {other.name}: 3D重なり")

    return {
        "valid": not warnings,
        "warnings": warnings[:10],
        "warning_count": len(warnings),
    }

def classify_items_for_day(items, current_date, must_ship_window_days=7):
    """
    plan_date 時点で荷物を Must / Forwardable / Future に分類する。
    Future は未到着なので、当日の3Dパッキングには渡さない。
    """
    target_date_limit = current_date + datetime.timedelta(days=must_ship_window_days)
    groups = {
        "must_ship": [],
        "forwardable": [],
        "hold": [],
        "future": [],
    }

    for item in items:
        if item.creation_date > current_date:
            item.selection_reason = "未到着"
            groups["future"].append(item)
            continue

        must_reasons = []
        if item.force_ship:
            must_reasons.append("手動強制")
        if item.due_date <= target_date_limit:
            must_reasons.append("納期接近")
        if item.expiration_date and item.expiration_date <= target_date_limit:
            must_reasons.append("木箱期限接近")

        if must_reasons:
            item.selection_reason = " / ".join(must_reasons)
            groups["must_ship"].append(item)
        elif item.allow_early_ship:
            item.selection_reason = "前倒し候補"
            groups["forwardable"].append(item)
        else:
            item.selection_reason = "前倒し不可"
            groups["hold"].append(item)

    return groups

def build_constraint_tags(item):
    return []

def nearest_deadline(item):
    candidates = [item.due_date]
    if item.expiration_date:
        candidates.append(item.expiration_date)
    return min(candidates)

