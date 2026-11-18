# iter425: welfare money lands on accounts a person chose, fund payouts come
# out of a named account and print a signable voucher, and a director can pin
# someone to the handful of accounts they are allowed to touch.
import asyncio
import sys
import uuid

import pytest

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from deps import raw_db  # noqa: E402
from org_context import org_bypass, set_current_org  # noqa: E402
from routers import social_work as sw  # noqa: E402
from routers import funds  # noqa: E402
from routers.finance import account_access as acc  # noqa: E402

GLOBAL_ORG = "c1f75976-4d8c-4958-8703-ff2ff0b3f7cf"
CAMPUS = f"loc_w_{uuid.uuid4().hex[:6]}"
CASE = f"case_w_{uuid.uuid4().hex[:6]}"
TAG = uuid.uuid4().hex[:6]
ACCTS = {
    "fees": {"id": f"acc_fee_{TAG}", "code": f"9{TAG[:3]}1", "name": "School Fees Paid", "type": "expense"},
    "gifts": {"id": f"acc_gif_{TAG}", "code": f"9{TAG[:3]}2", "name": "Parent Contributions", "type": "revenue"},
    "cash": {"id": f"acc_csh_{TAG}", "code": f"9{TAG[:3]}3", "name": "Campus Cash Box", "type": "asset"},
    "bank": {"id": f"acc_bnk_{TAG}", "code": f"9{TAG[:3]}4", "name": "Campus Bank", "type": "asset"},
}
WORKER = {"id": f"usr_w_{TAG}", "role": "Staff", "name": "Esther",
          "organization_id": GLOBAL_ORG, "location_id": CAMPUS}
BOSS = {"id": f"usr_b_{TAG}", "role": "Director", "name": "Deborah",
        "organization_id": GLOBAL_ORG, "location_id": CAMPUS}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def campus():
    async def _mk():
        with org_bypass():
            await raw_db.locations.insert_one({"id": CAMPUS, "name": "Hope Campus", "organization_id": GLOBAL_ORG})
            await raw_db.social_cases.insert_one({
                "id": CASE, "organization_id": GLOBAL_ORG, "location_id": CAMPUS,
                "subject_id": f"child_{TAG}", "subject_name": "Amina", "category": "welfare_support",
                "status": "active",
            })
            await raw_db.finance_chart_of_accounts.insert_many([
                {**a, "active": True, "organization_id": GLOBAL_ORG} for a in ACCTS.values()
            ])
            await raw_db.users.insert_many([
                {**WORKER, "email": f"esther{TAG}@test.org", "status": "active"},
                {**BOSS, "email": f"deborah{TAG}@test.org", "status": "active"},
            ])
    _run(_mk())
    set_current_org(GLOBAL_ORG)
    yield

    async def _rm():
        with org_bypass():
            await raw_db.social_cases.delete_many({"id": CASE})
            await raw_db.locations.delete_many({"id": CAMPUS})
            await raw_db.finance_chart_of_accounts.delete_many({"id": {"$in": [a["id"] for a in ACCTS.values()]}})
            await raw_db.users.delete_many({"id": {"$in": [WORKER["id"], BOSS["id"]]}})
            await raw_db.finance_account_access.delete_many({"user_id": {"$in": [WORKER["id"], BOSS["id"]]}})
            await raw_db.social_child_payments.delete_many({"case_id": CASE})
            await raw_db.finance_journal_entries.delete_many({"location_id": CAMPUS})
            await raw_db.finance_deleted_entries.delete_many({"location_id": CAMPUS})
            await raw_db.donations.delete_many({"social_case_id": CASE})
            await raw_db.expenses.delete_many({"social_case_id": CASE})
            await raw_db.approval_requests.delete_many({"location_id": CAMPUS})
            await raw_db.financial.delete_many({"location_id": CAMPUS})
    _run(_rm())


def _pay(**over):
    body = {"kind": "tuition", "amount": 60000, "paid_to": "Hope Primary",
            "account_id": ACCTS["fees"]["id"], "money_account_id": ACCTS["cash"]["id"]}
    body.update(over)
    set_current_org(GLOBAL_ORG)
    return _run(sw.add_case_payment(CASE, body, WORKER))


def _je_for(payment):
    with org_bypass():
        return _run(raw_db.finance_journal_entries.find_one({"id": payment["journal_entry_id"]}, {"_id": 0}))


# --------------------------------------------- welfare money must name its home
def test_welfare_support_will_not_post_without_being_told_where(campus):
    with pytest.raises(Exception) as err:
        _pay(account_id="", money_account_id="")
    assert "Choose both accounts" in str(err.value)


def test_school_fees_leave_the_cash_box_and_land_on_the_chosen_expense(campus):
    p = _pay(amount=60000)
    je = _je_for(p)
    debit = next(l for l in je["lines"] if l["debit"] > 0)
    credit = next(l for l in je["lines"] if l["credit"] > 0)
    assert debit["account_code"] == ACCTS["fees"]["code"] and debit["debit"] == 60000
    assert credit["account_code"] == ACCTS["cash"]["code"] and credit["credit"] == 60000
    assert p["account_name"] == "School Fees Paid" and p["money_account_name"] == "Campus Cash Box"
    assert p["direction"] == "out" and p["posted"] is True


def test_support_from_the_parents_is_its_own_type_of_income(campus):
    p = _pay(kind="parent_support", amount=25000, account_id=ACCTS["gifts"]["id"],
             money_account_id=ACCTS["bank"]["id"], paid_to="Amina's mother")
    assert p["direction"] == "in" and p["payer_type"] == "parent"
    je = _je_for(p)
    debit = next(l for l in je["lines"] if l["debit"] > 0)
    credit = next(l for l in je["lines"] if l["credit"] > 0)
    assert debit["account_code"] == ACCTS["bank"]["code"]        # money arrives
    assert credit["account_code"] == ACCTS["gifts"]["code"]      # income recognised
    assert je["source"] == "parent_contribution"
    with org_bypass():
        mirror = _run(raw_db.donations.find_one({"social_payment_id": p["id"]}, {"_id": 0}))
    assert mirror["type"] == "parent_contribution"


def test_money_cannot_be_parked_on_the_wrong_kind_of_account(campus):
    with pytest.raises(Exception) as err:
        _pay(kind="parent_support", account_id=ACCTS["fees"]["id"], money_account_id=ACCTS["bank"]["id"])
    assert "not an income account" in str(err.value)
    with pytest.raises(Exception) as err:
        _pay(money_account_id=ACCTS["gifts"]["id"])
    assert "not a cash or bank account" in str(err.value)


def test_deleting_a_payment_takes_it_back_out_of_the_books(campus):
    p = _pay(amount=12000)
    assert _je_for(p) is not None
    set_current_org(GLOBAL_ORG)
    res = _run(sw.delete_case_payment(CASE, p["id"], BOSS))
    assert res["deleted"] is True
    with org_bypass():
        left = _run(raw_db.finance_journal_entries.find_one({"id": p["journal_entry_id"]}))
        kept = _run(raw_db.finance_deleted_entries.find_one({"je_id": p["journal_entry_id"]}))
    assert left is None, "the entry still sits in the ledger after the payment was deleted"
    assert kept is not None, "nothing was kept for the audit trail"


# --------------------------------------------- only the accounts you were given
def test_a_person_with_no_grant_sees_the_whole_chart(campus):
    set_current_org(GLOBAL_ORG)
    res = _run(acc.my_accounts(with_balances=False, current_user=WORKER))
    assert res["restricted"] is False
    assert any(a["id"] == ACCTS["cash"]["id"] for a in res["accounts"])


def test_once_pinned_a_person_only_sees_their_own_accounts(campus):
    set_current_org(GLOBAL_ORG)
    _run(acc.set_grant(WORKER["id"], {"account_ids": [ACCTS["fees"]["id"], ACCTS["cash"]["id"]]}, BOSS))
    res = _run(acc.my_accounts(with_balances=True, current_user=WORKER))
    assert res["restricted"] is True
    assert sorted(a["id"] for a in res["accounts"]) == sorted([ACCTS["fees"]["id"], ACCTS["cash"]["id"]])
    assert all("balance" in a for a in res["accounts"])


def test_posting_outside_your_accounts_is_refused(campus):
    set_current_org(GLOBAL_ORG)
    _run(acc.set_grant(WORKER["id"], {"account_ids": [ACCTS["fees"]["id"], ACCTS["cash"]["id"]]}, BOSS))
    with pytest.raises(Exception) as err:
        _pay(kind="parent_support", account_id=ACCTS["gifts"]["id"], money_account_id=ACCTS["bank"]["id"])
    assert "not been given access" in str(err.value)
    # And the accounts they DO hold still work.
    assert _pay(amount=1000)["posted"] is True


def test_a_director_is_never_locked_out_of_an_account(campus):
    set_current_org(GLOBAL_ORG)
    _run(acc.set_grant(BOSS["id"], {"account_ids": [ACCTS["cash"]["id"]]}, BOSS))
    res = _run(acc.my_accounts(with_balances=False, current_user=BOSS))
    assert res["restricted"] is False


def test_clearing_the_list_frees_the_person_again(campus):
    set_current_org(GLOBAL_ORG)
    _run(acc.set_grant(WORKER["id"], {"account_ids": [ACCTS["cash"]["id"]]}, BOSS))
    out = _run(acc.set_grant(WORKER["id"], {"account_ids": []}, BOSS))
    assert "unrestricted" in out["message"]
    assert _run(acc.my_accounts(with_balances=False, current_user=WORKER))["restricted"] is False


# --------------------------------------------- fund requests pay out and print
@pytest.fixture
def approved_request(campus):
    req = {
        "id": f"areq_{TAG}", "subject_kind": "fund_request", "status": "approved",
        "title": "Advance — fuel for the school run", "summary": "Fuel for the school run",
        "amount": 150000, "currency": "UGX", "location_id": CAMPUS,
        "submitted_by": WORKER["id"], "submitted_by_name": "Esther",
        "metadata": {"kind": "advance", "category": "Transport"},
        "step_states": [{"step_index": 0, "status": "approved", "approvals": [
            {"user_id": BOSS["id"], "user_name": "Deborah", "user_role": "Director",
             "outcome": "approved", "at": "2026-06-01T08:00:00+00:00"}]}],
        "created_at": "2026-06-01T07:00:00+00:00",
    }
    with org_bypass():
        _run(raw_db.approval_requests.insert_one(dict(req)))
    set_current_org(GLOBAL_ORG)
    return req


def _admin():
    return {**BOSS, "role": "system_admin"}


def test_a_payout_must_say_which_account_the_money_leaves(approved_request):
    with pytest.raises(Exception) as err:
        _run(funds.mark_paid(approved_request["id"], {}, _admin()))
    assert "Choose which account the funds come out of" in str(err.value)


def test_paying_a_request_moves_real_money_and_stamps_a_voucher(approved_request):
    res = _run(funds.mark_paid(approved_request["id"], {
        "paid_from_account_id": ACCTS["bank"]["id"],
        "expense_account_id": ACCTS["fees"]["id"],
        "notes": "Mobile money ABC123",
    }, _admin()))
    assert res["voucher_no"].startswith("FV-")
    assert res["paid_from_account_name"] == "Campus Bank"
    with org_bypass():
        je = _run(raw_db.finance_journal_entries.find_one({"id": res["journal_entry_id"]}, {"_id": 0}))
    debit = next(l for l in je["lines"] if l["debit"] > 0)
    credit = next(l for l in je["lines"] if l["credit"] > 0)
    assert debit["account_code"] == ACCTS["fees"]["code"] and debit["debit"] == 150000
    assert credit["account_code"] == ACCTS["bank"]["code"]
    # Paying twice doesn't pay twice.
    again = _run(funds.mark_paid(approved_request["id"], {
        "paid_from_account_id": ACCTS["bank"]["id"], "expense_account_id": ACCTS["fees"]["id"]}, _admin()))
    assert again["message"] == "Already paid" and again["expense_id"] == res["expense_id"]


def test_the_voucher_can_be_signed_for(approved_request):
    _run(funds.mark_paid(approved_request["id"], {
        "paid_from_account_id": ACCTS["bank"]["id"], "expense_account_id": ACCTS["fees"]["id"]}, _admin()))
    resp = _run(funds.fund_voucher(approved_request["id"], _admin()))
    html = resp.body.decode()
    assert "Payment Voucher" in html
    assert "One hundred and fifty thousand shillings only" in html
    assert "Received by" in html and "Approved by" in html and "Prepared by" in html
    assert "Campus Bank" in html and "Deborah" in html


def test_a_stranger_cannot_print_someone_elses_voucher(approved_request):
    outsider = {"id": "usr_nosey", "role": "Staff", "name": "Nosey",
                "organization_id": GLOBAL_ORG, "location_id": CAMPUS}
    with pytest.raises(Exception) as err:
        _run(funds.fund_voucher(approved_request["id"], outsider))
    assert "Only the submitter or finance" in str(err.value)


def test_amounts_are_written_out_the_way_a_signature_needs_them():
    assert funds._amount_in_words(2500, "UGX") == "Two thousand five hundred shillings only"
    assert funds._amount_in_words(1_250_500, "UGX").startswith("One million two hundred and fifty thousand")
    assert funds._amount_in_words(42, "USD") == "Forty-two USD only"
