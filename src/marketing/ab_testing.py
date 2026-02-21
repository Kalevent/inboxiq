"""
A/B test evaluation for nurture email campaigns.

Runs weekly via Celery Beat. For each campaign_type + sequence_day combination
that has both A and B sends, it:
  1. Computes open rates for each variant
  2. Runs a two-proportion z-test to check statistical significance
  3. Logs the winner (or "inconclusive") so the team can act on it

The variants are:
  A — pain-point focused subject / body (baseline)
  B — ROI / case-study focused subject / body

Note: We do NOT auto-pause the losing variant because email marketing requires
human review before changing the audience experience. The evaluation result is
logged and should be reviewed in the admin dashboard.

Minimum sample requirements (per variant per step):
  MIN_SAMPLE = 50 sends   — below this we skip (too few to be meaningful)
  SIGNIFICANCE_THRESHOLD = 0.05   — p < 0.05 to call a winner
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Tuple

from src.celery_inboxiq import celery
from src.extensions import db
from src.models import NurtureEmailSend

logger = logging.getLogger(__name__)

MIN_SAMPLE = 50
SIGNIFICANCE_THRESHOLD = 0.05


def _z_test_two_proportions(opens_a: int, sends_a: int, opens_b: int, sends_b: int) -> Tuple[float, float]:
    """
    Two-proportion z-test for open rate A vs B.

    Returns (z_score, p_value). p_value is two-tailed.
    Returns (0.0, 1.0) if denominator is zero.
    """
    if sends_a == 0 or sends_b == 0:
        return 0.0, 1.0

    p_a = opens_a / sends_a
    p_b = opens_b / sends_b
    p_pool = (opens_a + opens_b) / (sends_a + sends_b)

    se = math.sqrt(p_pool * (1 - p_pool) * (1 / sends_a + 1 / sends_b))
    if se == 0:
        return 0.0, 1.0

    z = (p_a - p_b) / se
    # Two-tailed p-value using erfc (no scipy dependency)
    p_value = math.erfc(abs(z) / math.sqrt(2))
    return round(z, 4), round(p_value, 6)


def _evaluate_step(campaign_type: str, sequence_day: int, lookback_days: int = 30) -> Dict[str, Any]:
    """
    Evaluate A/B test for one campaign_type + sequence_day combination.

    Returns a summary dict with winner, open rates, z-score, and p-value.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    rows = db.session.query(
        NurtureEmailSend.ab_variant,
        db.func.count().label("sends"),
        db.func.sum(db.cast(NurtureEmailSend.opened, db.Integer)).label("opens"),
    ).filter(
        NurtureEmailSend.campaign_type == campaign_type,
        NurtureEmailSend.sequence_day == sequence_day,
        NurtureEmailSend.ab_variant.in_(["A", "B"]),
        NurtureEmailSend.sent_at >= cutoff,
    ).group_by(NurtureEmailSend.ab_variant).all()

    stats: Dict[str, Dict[str, int]] = {}
    for row in rows:
        stats[row.ab_variant] = {"sends": row.sends, "opens": int(row.opens or 0)}

    result: Dict[str, Any] = {
        "campaign_type": campaign_type,
        "sequence_day": sequence_day,
        "lookback_days": lookback_days,
        "winner": "inconclusive",
        "reason": "insufficient_data",
    }

    if "A" not in stats or "B" not in stats:
        result["reason"] = "missing_variant"
        return result

    sends_a = stats["A"]["sends"]
    opens_a = stats["A"]["opens"]
    sends_b = stats["B"]["sends"]
    opens_b = stats["B"]["opens"]

    result["variant_a"] = {"sends": sends_a, "opens": opens_a, "open_rate": round(opens_a / sends_a, 4) if sends_a else 0}
    result["variant_b"] = {"sends": sends_b, "opens": opens_b, "open_rate": round(opens_b / sends_b, 4) if sends_b else 0}

    if sends_a < MIN_SAMPLE or sends_b < MIN_SAMPLE:
        result["reason"] = f"below_min_sample ({MIN_SAMPLE})"
        return result

    z, p = _z_test_two_proportions(opens_a, sends_a, opens_b, sends_b)
    result["z_score"] = z
    result["p_value"] = p

    if p >= SIGNIFICANCE_THRESHOLD:
        result["reason"] = f"not_significant (p={p})"
        return result

    # Significant — pick winner by open rate
    rate_a = opens_a / sends_a
    rate_b = opens_b / sends_b
    if rate_a > rate_b:
        result["winner"] = "A"
        result["lift_pct"] = round((rate_a - rate_b) / rate_b * 100, 1) if rate_b else 0
    else:
        result["winner"] = "B"
        result["lift_pct"] = round((rate_b - rate_a) / rate_a * 100, 1) if rate_a else 0

    result["reason"] = f"significant (p={p})"
    return result


@celery.task(name="marketing.evaluate_nurture_ab_tests")
def evaluate_nurture_ab_tests() -> Dict[str, Any]:
    """
    Weekly A/B test evaluation for all nurture campaign steps.

    Logs results at INFO level. Does NOT auto-pause variants — human review required.

    Returns:
        Dict mapping "campaign_type:day" to evaluation result.
    """
    steps = [
        ("discovery", 1),
        ("discovery", 3),
        ("discovery", 7),
        ("discovery", 14),
        ("discovery", 21),
        ("consideration", 1),
        ("consideration", 3),
        ("consideration", 7),
        ("consideration", 14),
    ]

    results: Dict[str, Any] = {}
    for campaign_type, day in steps:
        key = f"{campaign_type}:day{day}"
        try:
            eval_result = _evaluate_step(campaign_type, day)
            results[key] = eval_result

            if eval_result["winner"] in ("A", "B"):
                logger.info(
                    "[AB TEST] %s — winner: Variant %s (lift=%.1f%%, p=%.4f) | "
                    "A: %d sends %.1f%% open | B: %d sends %.1f%% open",
                    key,
                    eval_result["winner"],
                    eval_result.get("lift_pct", 0),
                    eval_result.get("p_value", 1),
                    eval_result.get("variant_a", {}).get("sends", 0),
                    eval_result.get("variant_a", {}).get("open_rate", 0) * 100,
                    eval_result.get("variant_b", {}).get("sends", 0),
                    eval_result.get("variant_b", {}).get("open_rate", 0) * 100,
                )
            else:
                logger.info(
                    "[AB TEST] %s — inconclusive (%s)",
                    key, eval_result.get("reason", "unknown"),
                )
        except Exception as exc:
            logger.error("[AB TEST] Error evaluating %s: %s", key, exc)
            results[key] = {"error": str(exc)}

    return results
