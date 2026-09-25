"""
True Value of Video Games — Frozen Algorithm, Version 0.1

DO NOT MODIFY these formulas or parameters without explicit authorization
from the project owner. This file is the single source of truth for the math.

    TV = C x QM

Content:   C  = 100 * (1 - e^(-(H/85)^0.65))
Quality:   Cf = 1 - 1 / (1 + log10(max(n, 1)))
           Q  = Pc * (1 - Cf) + Pu * Cf
Modifier:  Q >= 70:  QM = 1 + 0.15 * ((Q - 70) / 30) ^ 1.5
           Q <  70:  QM = 1 - 0.50 * ((70 - Q) / 70) ^ 1.5
"""

import math

ALGORITHM_VERSION = "0.1"

# Content curve parameters (frozen)
K = 85.0
P = 0.65

# Quality modifier parameters (frozen)
BASELINE_Q = 70.0
EXPONENT = 1.5
MAX_BONUS = 0.15
MAX_PENALTY = 0.50


def content_score(hours: float) -> float:
    """C = 100 * (1 - e^(-(H/85)^0.65))"""
    if hours <= 0:
        return 0.0
    return 100.0 * (1.0 - math.exp(-((hours / K) ** P)))


def confidence_factor(review_count: int) -> float:
    """Cf = 1 - 1 / (1 + log10(max(n, 1)))"""
    n = max(review_count, 1)
    return 1.0 - 1.0 / (1.0 + math.log10(n))


def quality_score(critic_pct: float, user_pct: float, review_count: int) -> float:
    """Q = Peffective = Pc * (1 - Cf) + Pu * Cf"""
    cf = confidence_factor(review_count)
    return critic_pct * (1.0 - cf) + user_pct * cf


def quality_modifier(q: float) -> float:
    """Asymmetric modifier: max +15% bonus, max -50% penalty, baseline 70."""
    if q >= BASELINE_Q:
        return 1.0 + MAX_BONUS * ((q - BASELINE_Q) / 30.0) ** EXPONENT
    return 1.0 - MAX_PENALTY * ((BASELINE_Q - q) / 70.0) ** EXPONENT


def true_value(hours: float, critic_pct: float, user_pct: float, review_count: int) -> dict:
    """Run the full v0.1 algorithm and return every intermediate value."""
    c = content_score(hours)
    cf = confidence_factor(review_count)
    q = quality_score(critic_pct, user_pct, review_count)
    qm = quality_modifier(q)
    return {
        "C": c,
        "Cf": cf,
        "Q": q,
        "QM": qm,
        "TV": c * qm,
    }
