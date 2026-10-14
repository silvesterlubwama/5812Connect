"""iter389 — collection windows (LST runs Jul-Oct only) and the employer
covering an employee's first instalment."""
from routers.payroll_engine import apply_statutory_lines, cycle_label, in_collection_window

LST = {
    "name": "LST (Local Service Tax)", "type": "deduction", "is_percentage": False,
    "amount": 0, "band_mode": "bracket_amount", "active_months": [7, 8, 9, 10],
    "liability_account_code": "2200",
    "bands": [{"up_to": 100000, "amount": 0}, {"up_to": 400000, "amount": 5000},
              {"up_to": None, "amount": 25000}],
}
NSSF = {"name": "NSSF Employee", "type": "deduction", "is_percentage": True, "amount": 5}


def _sal(overrides=None):
    return {"statutory_overrides": overrides or {}}


def test_line_only_collects_inside_its_window():
    for month in ("07", "08", "09", "10"):
        out = apply_statutory_lines([dict(LST)], _sal(), 500_000, period=f"2026-{month}")
        assert out["employee_deductions"] == 25_000, month
    for month in ("01", "05", "06", "11", "12"):
        out = apply_statutory_lines([dict(LST)], _sal(), 500_000, period=f"2026-{month}")
        assert out["employee_deductions"] == 0, month
        assert out["items"] == []


def test_a_line_with_no_window_runs_every_month():
    for month in ("01", "07", "12"):
        out = apply_statutory_lines([dict(NSSF)], _sal(), 500_000, period=f"2026-{month}")
        assert out["employee_deductions"] == 25_000


def test_window_is_ignored_when_no_period_is_supplied():
    """Older callers that don't pass a period must not silently lose deductions."""
    assert apply_statutory_lines([dict(LST)], _sal(), 500_000)["employee_deductions"] == 25_000


def test_a_late_joiner_simply_misses_the_collection():
    out = apply_statutory_lines([dict(LST)], _sal(), 500_000, period="2027-01")
    assert out["employee_deductions"] == 0


def test_employer_covers_the_whole_first_instalment():
    sal = _sal({"lst_local_service_tax": {"employer_pays": True}})
    out = apply_statutory_lines([dict(LST)], sal, 500_000, period="2026-07")
    # Nothing off the employee, the employer bears it, the authority is still owed it.
    assert out["employee_deductions"] == 0
    assert out["employer_cost"] == 25_000
    assert out["withheld_liability"] == 25_000
    item = out["items"][0]
    assert item["type"] == "employer_contribution"
    assert item["covered_for_employee"] is True
    assert item["liability_account_code"] == "2200"
    # The caller is told to lock it to this cycle.
    assert out["cycle_stamps"] == {"lst_local_service_tax": "2026:lst_local_service_tax"}


def test_employer_covers_a_share_and_the_employee_pays_the_rest():
    sal = _sal({"lst_local_service_tax": {"employer_pays": True, "employer_share": 60}})
    out = apply_statutory_lines([dict(LST)], sal, 500_000, period="2026-07")
    assert out["employer_cost"] == 15_000
    assert out["employee_deductions"] == 10_000
    assert out["withheld_liability"] == 25_000      # authority still owed the full amount
    assert len(out["items"]) == 2


def test_employer_help_lasts_exactly_one_cycle():
    ov = {"lst_local_service_tax": {"employer_pays": True,
                                    "employer_pays_cycle": "2026:lst_local_service_tax"}}
    # Still inside the stamped cycle — covered.
    out = apply_statutory_lines([dict(LST)], _sal(ov), 500_000, period="2026-09")
    assert out["employer_cost"] == 25_000 and out["employee_deductions"] == 0
    # Next year's cycle — back on the employee.
    out = apply_statutory_lines([dict(LST)], _sal(ov), 500_000, period="2027-07")
    assert out["employer_cost"] == 0 and out["employee_deductions"] == 25_000
    assert out["cycle_stamps"] == {}


def test_employer_cover_is_not_added_to_gross_so_paye_is_untouched():
    paye = {"name": "PAYE", "type": "deduction", "is_percentage": True, "amount": 30}
    sal = _sal({"lst_local_service_tax": {"employer_pays": True}})
    covered = apply_statutory_lines([dict(LST), paye], sal, 500_000, period="2026-07")
    plain = apply_statutory_lines([paye], _sal(), 500_000, period="2026-07")
    paye_line = next(i for i in covered["items"] if i["name"] == "PAYE")
    assert paye_line["calculated_amount"] == plain["items"][0]["calculated_amount"]


def test_cycle_label_handles_a_window_that_wraps_the_year_end():
    wrapped = {**LST, "active_months": [11, 12, 1, 2]}
    assert cycle_label(wrapped, "2026-11") == cycle_label(wrapped, "2027-01")
    assert cycle_label(wrapped, "2026-11").startswith("2026:")
    # A normal window is labelled by its own calendar year.
    assert cycle_label(LST, "2026-07") == "2026:lst_local_service_tax"
    assert in_collection_window(wrapped, "2027-01") is True
    assert in_collection_window(wrapped, "2027-03") is False


def test_no_employer_cover_without_the_flag():
    sal = _sal({"lst_local_service_tax": {"employer_share": 100}})
    out = apply_statutory_lines([dict(LST)], sal, 500_000, period="2026-07")
    assert out["employee_deductions"] == 25_000
    assert out["employer_cost"] == 0
