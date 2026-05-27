import datetime
import math
from models import Container
from vanning_engine import VOLUME_TARGET_RATE

def read_bounded_int(data, key, default, min_value, max_value):
    try:
        value = int(data.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(min_value, min(value, max_value))

def parse_base_date(value):
    if not value:
        return datetime.date.today(), None
    try:
        return datetime.datetime.strptime(value, '%Y-%m-%d').date(), None
    except (TypeError, ValueError):
        return None, "作業基準日は YYYY-MM-DD 形式で指定してください"

def summarize_containers(containers, target_volume_rate=80.0):
    if not containers:
        return {
            "container_count": 0,
            "alert_containers": 0,
            "avg_volume_rate": 0,
            "avg_weight_rate": 0,
        }

    return {
        "container_count": len(containers),
        "alert_containers": sum(1 for c in containers if c.fill_rate_volume < target_volume_rate),
        "avg_volume_rate": round(sum(c.fill_rate_volume for c in containers) / len(containers), 1),
        "avg_weight_rate": round(sum(c.fill_rate_weight for c in containers) / len(containers), 1),
    }

def build_efficiency_summary(containers, target_volume_rate=80.0):
    """Return capacity lower bounds and achieved results for an explainable plan."""
    if not containers:
        return {
            "container_count": 0,
            "capacity_lower_bound": 0,
            "container_gap_to_lower_bound": 0,
            "volume_lower_bound": 0,
            "weight_lower_bound": 0,
            "alert_containers": 0,
            "volume_only_minimum_alerts": 0,
            "avg_volume_rate": 0,
            "avg_weight_rate": 0,
        }

    reference = containers[0] if containers else Container(id="SUMMARY")
    total_volume = sum(container.current_volume_m3 for container in containers)
    total_weight = sum(container.current_weight for container in containers)
    volume_lower_bound = math.ceil(total_volume / reference.max_volume_m3)
    weight_lower_bound = math.ceil(total_weight / reference.max_weight)
    capacity_lower_bound = max(volume_lower_bound, weight_lower_bound)
    maximum_target_containers_by_volume = math.floor(
        total_volume / (reference.max_volume_m3 * (target_volume_rate / 100))
    )
    actual_count = len(containers)
    alert_count = sum(1 for c in containers if c.fill_rate_volume < target_volume_rate)

    return {
        "container_count": actual_count,
        "capacity_lower_bound": capacity_lower_bound,
        "container_gap_to_lower_bound": actual_count - capacity_lower_bound,
        "volume_lower_bound": volume_lower_bound,
        "weight_lower_bound": weight_lower_bound,
        "alert_containers": alert_count,
        "volume_only_minimum_alerts": max(0, actual_count - maximum_target_containers_by_volume),
        "avg_volume_rate": round(sum(c.fill_rate_volume for c in containers) / actual_count, 1),
        "avg_weight_rate": round(sum(c.fill_rate_weight for c in containers) / actual_count, 1),
        "total_volume_m3": round(total_volume, 2),
        "total_weight_kg": round(total_weight, 1),
        "target_volume_rate": target_volume_rate,
        "lower_bound_note": "容量と重量のみから計算した理論下限です。寸法による3D配置制約を含む最適本数の保証値ではありません。",
    }

def output_container_sort_key(container):
    earliest_due = None
    earliest_expiration = None
    for item in container.items:
        earliest_due = item.due_date if earliest_due is None else min(earliest_due, item.due_date)
        if item.expiration_date:
            earliest_expiration = (
                item.expiration_date
                if earliest_expiration is None
                else min(earliest_expiration, item.expiration_date)
            )
    return (
        earliest_due or datetime.date.max,
        earliest_expiration or datetime.date.max,
        container.id,
    )

def order_containers_for_output(containers):
    return sorted(containers, key=output_container_sort_key)

def build_comparison(baseline_containers, optimized_containers, target_volume_rate=80.0):
    baseline = summarize_containers(baseline_containers, target_volume_rate)
    optimized = summarize_containers(optimized_containers, target_volume_rate)
    return {
        "baseline": baseline,
        "optimized": optimized,
        "delta": {
            "container_count": baseline["container_count"] - optimized["container_count"],
            "alert_containers": baseline["alert_containers"] - optimized["alert_containers"],
            "avg_volume_rate": round(optimized["avg_volume_rate"] - baseline["avg_volume_rate"], 1),
            "avg_weight_rate": round(optimized["avg_weight_rate"] - baseline["avg_weight_rate"], 1),
        }
    }

def build_forwardable_blocker_counts(engine, container, candidate_items, target_volume_rate=80.0):
    counts = {}
    if container.fill_rate_volume >= target_volume_rate:
        return counts
    for item in candidate_items:
        reason = engine.explain_unfit_reason(container, item)
        counts[reason] = counts.get(reason, 0) + 1
    return counts

def format_blocker_counts(blocker_counts):
    if not blocker_counts:
        return ""
    order = ["重量上限", "重量ソフト上限", "3D配置", "採用可能"]
    parts = []
    for key in order:
        if blocker_counts.get(key):
            parts.append(f"{key}{blocker_counts[key]}件")
    for key, value in blocker_counts.items():
        if key not in order and value:
            parts.append(f"{key}{value}件")
    return " / ".join(parts[:3])

def build_item_brief(item, reference_date, reason):
    days_until_due = (item.due_date - reference_date).days
    days_until_expiration = (item.expiration_date - reference_date).days if item.expiration_date else None
    return {
        "id": item.id,
        "name": item.name,
        "reason": reason,
        "creation_date": item.creation_date.strftime("%Y-%m-%d"),
        "due_date": item.due_date.strftime("%Y-%m-%d"),
        "expiration_date": item.expiration_date.strftime("%Y-%m-%d") if item.expiration_date else "",
        "days_until_due": days_until_due,
        "days_until_expiration": days_until_expiration,
        "priority": item.priority,
        "allow_early_ship": item.allow_early_ship,
        "constraint_tags": [],
        "selection_reason": item.selection_reason,
        "decision_reason": item.decision_reason or item.selection_reason or reason,
        "status_msg": item.status_msg,
    }

def review_sort_key(entry):
    exp_days = entry["days_until_expiration"]
    nearest_days = min(
        entry["days_until_due"],
        exp_days if exp_days is not None else entry["days_until_due"]
    )
    risk_rank = 0 if nearest_days < 0 else 1 if nearest_days <= 7 else 2
    return (risk_rank, nearest_days, -entry["priority"], entry["due_date"], entry["name"])

def build_review_queue(pool_items, unused_forwardable, hold_items, future_items, current_date, limit=12):
    seen = set()
    entries = []
    sources = [
        (pool_items, "保留プール: 3D配置または充填率判断で今回未確定"),
        (unused_forwardable, "未使用の追加積載候補: 今回の80%未満対策には未採用"),
        (hold_items, "追加積載対象外: 積込期限または木箱期限まで待機"),
        (future_items, "未納入: 納入予定日待ち"),
    ]

    for items, reason in sources:
        for item in items:
            if item.id in seen:
                continue
            seen.add(item.id)
            entries.append(build_item_brief(item, current_date, reason))

    return sorted(entries, key=review_sort_key)[:limit]

def build_remaining_risks(remaining_items, reference_date, limit=20):
    entries = []
    for item in remaining_items:
        if item.due_date <= reference_date or (item.expiration_date and item.expiration_date <= reference_date):
            reason = "期間終了時点で期限到来/超過"
        elif item.creation_date > reference_date:
            reason = "期間内に未到着"
        elif not item.allow_early_ship:
            reason = "追加積載対象外で待機"
        else:
            reason = "期間内で未出荷"
        entries.append(build_item_brief(item, reference_date, reason))

    return sorted(entries, key=review_sort_key)[:limit]


def build_container_alert_summary(container, current_date, must_ship_window_days, blocker_counts=None):
    is_alert = container.fill_rate_volume < VOLUME_TARGET_RATE
    pulled_count = sum(1 for item in container.items if item.status_msg and "前倒し" in item.status_msg)
    if not is_alert:
        if pulled_count:
            return {
                "title": "追加積載で80%クリア",
                "detail": f"空きスペースへの追加積載{pulled_count}件により、体積充填率{container.fill_rate_volume:.1f}%となりました。"
            }
        return {"title": "", "detail": ""}

    limit_date = current_date + datetime.timedelta(days=must_ship_window_days)
    manual_count = sum(1 for item in container.items if item.force_ship)
    due_count = sum(1 for item in container.items if item.due_date <= limit_date)
    exp_count = sum(1 for item in container.items if item.expiration_date and item.expiration_date <= limit_date)

    reasons = []
    if manual_count:
        reasons.append(f"手動指定{manual_count}件")
    if due_count:
        reasons.append(f"積込期限対象{due_count}件")
    if exp_count:
        reasons.append(f"木箱期限{must_ship_window_days}日以内{exp_count}件")
    if not reasons:
        reasons.append("期限優先の必須出荷")

    supplement = (
        f"追加積載{pulled_count}件後も体積{container.fill_rate_volume:.1f}%です。"
        if pulled_count
        else "追加積載できる荷物は3D配置または重量上限により採用できませんでした。"
    )
    blocker_text = format_blocker_counts(blocker_counts or {})
    if blocker_text:
        supplement += f" 未採用候補の主因: {blocker_text}。"
    return {
        "title": "80%未満でも期限優先で出荷",
        "detail": f"{' / '.join(reasons)}のため保留不可。{supplement}"
    }
