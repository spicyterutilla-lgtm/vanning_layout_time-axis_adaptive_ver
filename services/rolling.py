import copy
import datetime
from services.session import SESSION_DATA, ROLLING_PLANNING_WINDOW_DAYS, ROLLING_FORCE_SHIP_WINDOW_DAYS, ROLLING_PLANNING_WINDOW_CANDIDATES
from services.validation import classify_items_for_day
from services.session import reset_runtime_state
from services.utils import build_remaining_risks, summarize_containers
from vanning_engine import VanningEngine, VOLUME_TARGET_RATE

def run_rolling_simulation(items, start_date, days=30, allow_pull=True, planning_window_days=0, force_ship_window_days=0):
    ledger_items = copy.deepcopy(items)
    shipped_ids = set()
    daily_results = []
    total_containers = 0
    total_alert_containers = 0
    total_pulls = 0
    volume_rates = []
    weight_rates = []

    for offset in range(days):
        plan_date = start_date + datetime.timedelta(days=offset)
        remaining_items = [item for item in ledger_items if item.id not in shipped_ids]
        reset_runtime_state(remaining_items)
        day_groups = classify_items_for_day(remaining_items, plan_date, must_ship_window_days=planning_window_days)

        engine = VanningEngine()
        forwardable_items = day_groups["forwardable"] if allow_pull else []
        containers, pool, unused_forwardable = engine.run_time_axis_packing(
            day_groups["must_ship"],
            forwardable_items,
            plan_date,
            force_ship_window_days=force_ship_window_days,
            allow_partial_red_pull=allow_pull
        )

        shipped_today_ids = {item.id for c in containers for item in c.items}
        shipped_ids.update(shipped_today_ids)

        shipped_today = sum(len(c.items) for c in containers)
        pull_count = sum(
            1
            for c in containers
            for item in c.items
            if item.status_msg and "前倒し" in item.status_msg
        )
        alerts = sum(1 for c in containers if c.fill_rate_volume < VOLUME_TARGET_RATE)
        avg_volume = round(sum(c.fill_rate_volume for c in containers) / len(containers), 1) if containers else 0
        avg_weight = round(sum(c.fill_rate_weight for c in containers) / len(containers), 1) if containers else 0

        total_containers += len(containers)
        total_alert_containers += alerts
        total_pulls += pull_count
        if containers:
            volume_rates.extend(c.fill_rate_volume for c in containers)
            weight_rates.extend(c.fill_rate_weight for c in containers)

        deadline_remaining = sum(
            1 for item in remaining_items
            if item.id not in shipped_today_ids
            and (item.due_date <= plan_date or (item.expiration_date and item.expiration_date <= plan_date))
        )

        daily_results.append({
            "date": plan_date.strftime("%Y-%m-%d"),
            "containers": len(containers),
            "shipped": shipped_today,
            "pulls": pull_count,
            "alerts": alerts,
            "must_ship": len(day_groups["must_ship"]),
            "forwardable": len(day_groups["forwardable"]),
            "unused_forwardable": len(unused_forwardable) if allow_pull else len(day_groups["forwardable"]),
            "hold": len(day_groups["hold"]),
            "future": len(day_groups["future"]),
            "pool": len(pool),
            "overdue_remaining": deadline_remaining,
            "deadline_remaining": deadline_remaining,
            "avg_volume_rate": avg_volume,
            "avg_weight_rate": avg_weight,
        })

    remaining_items = [item for item in ledger_items if item.id not in shipped_ids]
    period_end = start_date + datetime.timedelta(days=days - 1)
    overdue_count = sum(
        1 for item in remaining_items
        if item.due_date <= period_end or (item.expiration_date and item.expiration_date <= period_end)
    )

    return {
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": period_end.strftime("%Y-%m-%d"),
        "days": days,
        "planning_window_days": planning_window_days,
        "force_ship_window_days": force_ship_window_days,
        "daily_results": daily_results,
        "total_containers": total_containers,
        "total_shipped": len(shipped_ids),
        "total_pulls": total_pulls,
        "total_alert_containers": total_alert_containers,
        "alert_rate": round((total_alert_containers / total_containers) * 100, 1) if total_containers else 0,
        "weekly_container_rate": round((total_containers / days) * 7, 1) if days else 0,
        "remaining_count": len(remaining_items),
        "overdue_count": overdue_count,
        "deadline_remaining_count": overdue_count,
        "remaining_risks": build_remaining_risks(remaining_items, period_end),
        "avg_volume_rate": round(sum(volume_rates) / len(volume_rates), 1) if volume_rates else 0,
        "avg_weight_rate": round(sum(weight_rates) / len(weight_rates), 1) if weight_rates else 0,
    }

def rolling_planning_candidates(days, item_count=0):
    horizon = max(0, days)
    candidate_pool = ROLLING_PLANNING_WINDOW_CANDIDATES
    if item_count >= 750:
        candidate_pool = (3, 7, 14)
    elif item_count >= 300:
        candidate_pool = (0, 5, 7, 10, 14)
    candidates = [window for window in candidate_pool if window <= horizon]
    return candidates or [0]

def rolling_result_score(result):
    return (
        result["overdue_count"],
        result["total_alert_containers"],
        result["total_containers"],
        result["remaining_count"],
        -result["avg_volume_rate"],
        abs(result.get("planning_window_days", 0) - ROLLING_PLANNING_WINDOW_DAYS),
        result["total_pulls"],
    )

def summarize_rolling_trial(result):
    return {
        "planning_window_days": result.get("planning_window_days", 0),
        "force_ship_window_days": result.get("force_ship_window_days", 0),
        "total_containers": result["total_containers"],
        "total_shipped": result["total_shipped"],
        "total_pulls": result["total_pulls"],
        "total_alert_containers": result["total_alert_containers"],
        "alert_rate": result.get("alert_rate", 0),
        "weekly_container_rate": result.get("weekly_container_rate", 0),
        "remaining_count": result["remaining_count"],
        "overdue_count": result["overdue_count"],
        "avg_volume_rate": result["avg_volume_rate"],
        "avg_weight_rate": result["avg_weight_rate"],
        "score": rolling_result_score(result),
    }

def run_adaptive_rolling_simulation(items, start_date, days=30, allow_pull=True):
    trials = []
    best_result = None
    best_score = None

    for planning_window_days in rolling_planning_candidates(days, item_count=len(items)):
        result = run_rolling_simulation(
            items,
            start_date,
            days,
            allow_pull=allow_pull,
            planning_window_days=planning_window_days,
            force_ship_window_days=ROLLING_FORCE_SHIP_WINDOW_DAYS
        )
        score = rolling_result_score(result)
        trials.append(summarize_rolling_trial(result))
        if best_score is None or score < best_score:
            best_score = score
            best_result = result

    best_result["strategy"] = "adaptive_planning_window"
    best_result["strategy_trials"] = trials
    return best_result

def build_rolling_comparison(baseline, optimized):
    return {
        "baseline": {
            "total_containers": baseline["total_containers"],
            "total_shipped": baseline["total_shipped"],
            "total_pulls": baseline["total_pulls"],
            "total_alert_containers": baseline["total_alert_containers"],
            "alert_rate": baseline.get("alert_rate", 0),
            "weekly_container_rate": baseline.get("weekly_container_rate", 0),
            "remaining_count": baseline["remaining_count"],
            "overdue_count": baseline["overdue_count"],
            "avg_volume_rate": baseline["avg_volume_rate"],
            "avg_weight_rate": baseline["avg_weight_rate"],
        },
        "optimized": {
            "total_containers": optimized["total_containers"],
            "total_shipped": optimized["total_shipped"],
            "total_pulls": optimized["total_pulls"],
            "total_alert_containers": optimized["total_alert_containers"],
            "alert_rate": optimized.get("alert_rate", 0),
            "weekly_container_rate": optimized.get("weekly_container_rate", 0),
            "remaining_count": optimized["remaining_count"],
            "overdue_count": optimized["overdue_count"],
            "avg_volume_rate": optimized["avg_volume_rate"],
            "avg_weight_rate": optimized["avg_weight_rate"],
        },
        "delta": {
            "total_containers": baseline["total_containers"] - optimized["total_containers"],
            "total_shipped": optimized["total_shipped"] - baseline["total_shipped"],
            "total_alert_containers": baseline["total_alert_containers"] - optimized["total_alert_containers"],
            "alert_rate": round(baseline.get("alert_rate", 0) - optimized.get("alert_rate", 0), 1),
            "weekly_container_rate": round(baseline.get("weekly_container_rate", 0) - optimized.get("weekly_container_rate", 0), 1),
            "remaining_count": baseline["remaining_count"] - optimized["remaining_count"],
            "overdue_count": baseline["overdue_count"] - optimized["overdue_count"],
            "avg_volume_rate": round(optimized["avg_volume_rate"] - baseline["avg_volume_rate"], 1),
            "avg_weight_rate": round(optimized["avg_weight_rate"] - baseline["avg_weight_rate"], 1),
        }
    }

def run_single_day_scenario(items, current_date, must_ship_window_days):
    scenario_items = copy.deepcopy(items)
    reset_runtime_state(scenario_items)
    day_groups = classify_items_for_day(scenario_items, current_date, must_ship_window_days)
    engine = VanningEngine()
    containers, pool, unused_forwardable = engine.run_time_axis_packing(
        day_groups["must_ship"],
        day_groups["forwardable"],
        current_date,
        allow_partial_red_pull=True
    )
    container_summary = summarize_containers(containers)
    total_pulls = sum(
        1
        for container in containers
        for item in container.items
        if item.status_msg and "前倒し" in item.status_msg
    )
    return {
        "must_ship_window_days": must_ship_window_days,
        "container_count": container_summary["container_count"],
        "alert_containers": container_summary["alert_containers"],
        "avg_volume_rate": container_summary["avg_volume_rate"],
        "avg_weight_rate": container_summary["avg_weight_rate"],
        "total_pulls": total_pulls,
        "must_ship_count": len(day_groups["must_ship"]),
        "pool_count": len(pool),
        "unused_forwardable_count": len(unused_forwardable),
        "forwardable_count": len(day_groups["forwardable"]),
        "hold_count": len(day_groups["hold"]),
        "future_count": len(day_groups["future"]),
    }

def single_day_scenario_score(scenario):
    return (
        scenario["alert_containers"],
        scenario["container_count"],
        -scenario["avg_volume_rate"],
        scenario["pool_count"],
        scenario["unused_forwardable_count"],
        scenario["must_ship_window_days"],
    )