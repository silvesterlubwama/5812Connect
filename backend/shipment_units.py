"""Shipping unit conversions — accept imperial OR metric inputs, store
canonical SI (cm + kg) on disk so the rest of the app stays unit-blind.

Parsing rules
─────────────
Dimensions  →  centimetres (float, 0..several-hundred-thousand)
    "33"          → 83.82  (interpreted as INCHES when units='imperial', else cm)
    "33in"        → 83.82
    33.5          → 85.09  (raw number — context decides; default cm)
    "2'9\""       → 83.82  (feet + inches)
    "2ft 9in"     → 83.82
    "0.84m"       → 84.0
    "84cm"        → 84.0
    "84 cm"       → 84.0
    "84"          → 84.0   (default cm in metric mode)

Weight  →  kilograms (float)
    "5lb"         → 2.268
    "5 lbs"       → 2.268
    "5.5 lbs 8oz" → 2.722  (lbs+oz combo)
    "8oz"         → 0.227
    "2.3kg"       → 2.3
    "2300g"       → 2.3
    "5"           → 2.268 in imperial mode (lbs), 5.0 in metric mode (kg)

Formatters for display
──────────────────────
format_dim_cm(cm, units)    → "2'9\"" / "83.8 cm"
format_weight_kg(kg, units) → "5 lb 0 oz" / "2.27 kg"
"""
from __future__ import annotations
import re
from typing import Tuple

CM_PER_INCH = 2.54
KG_PER_LB = 0.45359237
KG_PER_OZ = 0.028349523125

DIM_FEET_INCHES_RE = re.compile(
    r"""^\s*
    (?:(?P<ft>\d+(?:\.\d+)?)\s*(?:'|ft|feet|foot)\s*)?
    (?:(?P<in>\d+(?:\.\d+)?)\s*(?:\"|in|inch|inches))?
    \s*$""",
    re.VERBOSE | re.IGNORECASE,
)
WEIGHT_LB_OZ_RE = re.compile(
    r"""^\s*
    (?:(?P<lb>\d+(?:\.\d+)?)\s*(?:lb|lbs|pound|pounds)\s*)?
    (?:(?P<oz>\d+(?:\.\d+)?)\s*(?:oz|ounce|ounces))?
    \s*$""",
    re.VERBOSE | re.IGNORECASE,
)


def parse_dim_to_cm(value, units: str = "metric") -> float:
    """Parse a dimension input into canonical centimetres.

    `units` only matters when the input is a bare number with no unit suffix
    — in imperial mode "33" is read as inches; in metric mode it's cm.
    """
    if value is None or value == "":
        return 0.0
    # Pure number → bare → interpret by `units`
    if isinstance(value, (int, float)):
        return float(value) * (CM_PER_INCH if units == "imperial" else 1.0)
    s = str(value).strip().lower()
    if not s:
        return 0.0
    # Explicit metric suffixes
    if s.endswith("mm"):
        try:
            return float(s[:-2].strip()) / 10.0
        except ValueError:
            return 0.0
    if s.endswith("cm"):
        try:
            return float(s[:-2].strip())
        except ValueError:
            return 0.0
    if s.endswith("m") and not s.endswith("cm") and not s.endswith("mm"):
        try:
            return float(s[:-1].strip()) * 100.0
        except ValueError:
            return 0.0
    # Feet+inches forms — `2'9"`, `2ft 9in`, `9in`, `2'`
    if any(t in s for t in ("'", '"', "ft", "in", "foot", "feet", "inch")):
        m = DIM_FEET_INCHES_RE.match(s)
        if m:
            ft = float(m.group("ft") or 0)
            inches = float(m.group("in") or 0)
            return (ft * 12 + inches) * CM_PER_INCH
    # Bare number string fallback — same rule as numeric path above
    try:
        return float(s) * (CM_PER_INCH if units == "imperial" else 1.0)
    except ValueError:
        return 0.0


def parse_weight_to_kg(value, units: str = "metric") -> float:
    """Parse a weight input into canonical kilograms."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value) * (KG_PER_LB if units == "imperial" else 1.0)
    s = str(value).strip().lower()
    if not s:
        return 0.0
    if s.endswith("kg"):
        try:
            return float(s[:-2].strip())
        except ValueError:
            return 0.0
    if s.endswith("g") and not s.endswith("kg"):
        try:
            return float(s[:-1].strip()) / 1000.0
        except ValueError:
            return 0.0
    if any(t in s for t in ("lb", "oz", "pound", "ounce")):
        m = WEIGHT_LB_OZ_RE.match(s)
        if m:
            lbs = float(m.group("lb") or 0)
            ozs = float(m.group("oz") or 0)
            return lbs * KG_PER_LB + ozs * KG_PER_OZ
    try:
        return float(s) * (KG_PER_LB if units == "imperial" else 1.0)
    except ValueError:
        return 0.0


def cm_to_feet_inches(cm: float) -> Tuple[int, float]:
    """Return (whole_feet, remaining_inches)."""
    total_in = float(cm) / CM_PER_INCH
    feet = int(total_in // 12)
    inches = total_in - feet * 12
    return feet, inches


def format_dim_cm(cm: float, units: str = "metric") -> str:
    """Stringify a stored cm value back into the user's preferred units."""
    cm = float(cm or 0)
    if units == "imperial":
        feet, inches = cm_to_feet_inches(cm)
        if feet and inches >= 0.05:
            return f"{feet}'{inches:.0f}\""
        if feet:
            return f"{feet}'"
        return f"{inches:.1f}\""
    if cm >= 100:
        return f"{cm/100:.2f} m"
    return f"{cm:.1f} cm"


def kg_to_lb_oz(kg: float) -> Tuple[float, float]:
    """Return (whole_lbs, remaining_ozs)."""
    total_lb = float(kg) / KG_PER_LB
    lbs = int(total_lb)
    ozs = (total_lb - lbs) * 16
    return lbs, ozs


def format_weight_kg(kg: float, units: str = "metric") -> str:
    kg = float(kg or 0)
    if units == "imperial":
        lbs, ozs = kg_to_lb_oz(kg)
        if lbs and ozs >= 0.5:
            return f"{lbs} lb {ozs:.0f} oz"
        if lbs:
            return f"{lbs} lb"
        return f"{ozs:.1f} oz"
    if kg < 1:
        return f"{kg*1000:.0f} g"
    return f"{kg:.2f} kg"
