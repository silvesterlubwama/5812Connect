"""iter387 — statutory lines: per-line opt-in vs everyone, and fixed-amount
earnings brackets."""
from routers.payroll_engine import apply_statutory_lines

EMPLOYER = {
    "name": "NSSF Employer", "type": "employer_contribution", "mode": "employer_cost",
    "is_percentage": True, "amount": 10,
}
PAYE = {
    "name": "PAYE", "type": "deduction", "is_percentage": True, "amount": 0,
    "bands": [{"up_to": 235000, "rate": 0}, {"up_to": 335000, "rate": 10},
              {"up_to": 410000, "rate": 20}, {"up_to": None, "rate": 30}],
}


def _sal(overrides=None):
    return {"statutory_overrides": overrides or {}}


def test_everyone_line_applies_without_any_override():
    line = {**EMPLOYER, "applies_to": "everyone"}
    assert apply_statutory_lines([line], _sal(), 1_000_000)["employer_cost"] == 100_000


def test_opt_in_line_is_off_until_switched_on():
    line = {**EMPLOYER, "applies_to": "opt_in"}
    assert apply_statutory_lines([line], _sal(), 1_000_000)["employer_cost"] == 0
    # A rate alone is not consent — the switch has to be on.
    assert apply_statutory_lines([line], _sal({"nssf_employer": {"amount": 7}}), 1_000_000)["employer_cost"] == 0
    assert apply_statutory_lines([line], _sal({"nssf_employer": {"enabled": True}}), 1_000_000)["employer_cost"] == 100_000
    assert apply_statutory_lines([line], _sal({"nssf_employer": {"enabled": False}}), 1_000_000)["employer_cost"] == 0


def test_opt_in_honours_a_per_person_rate_once_switched_on():
    line = {**EMPLOYER, "applies_to": "opt_in"}
    out = apply_statutory_lines(
        [line], _sal({"nssf_employer": {"enabled": True, "amount": 7, "is_percentage": True}}), 1_000_000)
    assert out["employer_cost"] == 70_000


def test_missing_applies_to_defaults_to_everyone():
    """Existing campus data has no applies_to — it must keep working as before."""
    assert apply_statutory_lines([dict(PAYE)], _sal(), 1_000_000)["employee_deductions"] == 202_000


def test_opt_out_still_works_on_an_everyone_line():
    assert apply_statutory_lines([dict(PAYE)], _sal({"paye": {"enabled": False}}), 1_000_000)["employee_deductions"] == 0


BRACKETS = {
    "name": "Local Service Tax", "type": "deduction", "band_mode": "bracket_amount",
    "bands": [{"up_to": 200000, "amount": 0}, {"up_to": 400000, "amount": 5000},
              {"up_to": 600000, "amount": 10000}, {"up_to": None, "amount": 25000}],
}


def test_fixed_amount_brackets_pick_exactly_one_band():
    cases = {150_000: 0, 200_000: 0, 300_000: 5_000, 400_000: 5_000,
             500_000: 10_000, 600_000: 10_000, 900_000: 25_000}
    for gross, expected in cases.items():
        out = apply_statutory_lines([dict(BRACKETS)], _sal(), gross)
        assert out["employee_deductions"] == expected, f"gross {gross}"


def test_brackets_without_a_catch_all_charge_nothing_above_the_top():
    line = {**BRACKETS, "bands": [{"up_to": 200000, "amount": 1000}, {"up_to": 400000, "amount": 5000}]}
    assert apply_statutory_lines([line], _sal(), 5_000_000)["employee_deductions"] == 0


def test_brackets_are_not_progressive():
    """A progressive reading of the same table would stack the bands; the
    bracket mode must charge only the band the earner falls in."""
    out = apply_statutory_lines([dict(BRACKETS)], _sal(), 900_000)
    assert out["employee_deductions"] == 25_000
    assert len(out["items"]) == 1
    assert out["items"][0]["details"] == "top bracket"


def test_bracket_mode_is_stamped_on_the_payslip_item():
    out = apply_statutory_lines([dict(BRACKETS)], _sal(), 300_000)
    assert out["items"][0]["band_mode"] == "bracket_amount"
    out2 = apply_statutory_lines([dict(PAYE)], _sal(), 300_000)
    assert out2["items"][0]["band_mode"] == "progressive"
