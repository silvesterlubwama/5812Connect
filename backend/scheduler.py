"""Background schedulers and cron helpers.

Extracted from server.py in iter302 to keep the main app entrypoint focused
on wiring (routes/middleware/lifecycle). Behaviour is byte-for-byte the same
as before — every function below was lifted verbatim from server.py and only
its module home changed. server.py re-imports each name so callers using
`from server import _fire_overdue_task_director_digest` still work.
"""
import asyncio
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone

from deps import db, logger

# Daily auto-backup tracker (module-level so the scheduler can mark it idempotently)
_last_auto_backup_date = None


async def _send_push_to_user(user_id: str, title: str, body: str, url: str = "/tasks"):
    """Send a Web Push notification to all devices of a user."""
    try:
        from pywebpush import webpush
        vapid_private = os.environ.get("VAPID_PRIVATE_KEY", "")
        vapid_email = os.environ.get("VAPID_EMAIL", "admin@5812.org")
        if not vapid_private:
            return
        subs = await db.push_subscriptions.find({"user_id": user_id}, {"_id": 0}).to_list(10)
        payload = json.dumps({"title": title, "body": body, "icon": "/icon-192.png", "url": url})
        for sub in subs:
            try:
                webpush(subscription_info=sub["subscription"], data=payload, vapid_private_key=vapid_private, vapid_claims={"sub": f"mailto:{vapid_email}"})
            except Exception as e:
                logger.warning(f"Push send failed for {user_id}: {e}")
                if "expired" in str(e).lower() or "unsubscribe" in str(e).lower():
                    await db.push_subscriptions.delete_one({"user_id": user_id, "subscription.endpoint": sub["subscription"].get("endpoint")})
    except Exception as e:
        logger.warning(f"Push notification error: {e}")


async def _run_due_date_reminder_scheduler():
    """Hourly background task: notify assignees when their task is due tomorrow or today.
    Also fires a daily birthday/anniversary check at ~08:00 local UTC."""
    await asyncio.sleep(30)  # short initial delay to let startup finish
    last_birthday_check_date = None
    while True:
        try:
            tomorrow = (date.today() + timedelta(days=1)).isoformat()
            today_str = date.today().isoformat()

            # Tasks due tomorrow
            due_tasks = await db.tasks.find({
                "due_date": tomorrow,
                "is_archived": {"$ne": True},
                "status": {"$ne": "done"},
                "$or": [{"snooze_until": {"$exists": False}}, {"snooze_until": {"$lte": today_str}}],
            }, {"_id": 0, "id": 1, "title": 1, "assignees": 1, "assignee": 1, "board_id": 1}).to_list(200)

            for task in due_tasks:
                assignees = list(task.get("assignees") or [])
                if task.get("assignee") and task["assignee"] not in assignees:
                    assignees.append(task["assignee"])
                for uid in assignees:
                    await _send_push_to_user(uid, "Task Due Tomorrow", f'"{task["title"]}" is due tomorrow', f"/tasks?task={task['id']}")

            # Tasks due today
            today_tasks = await db.tasks.find({
                "due_date": today_str,
                "is_archived": {"$ne": True},
                "status": {"$ne": "done"},
                "$or": [{"snooze_until": {"$exists": False}}, {"snooze_until": {"$lte": today_str}}],
            }, {"_id": 0, "id": 1, "title": 1, "assignees": 1, "assignee": 1, "board_id": 1}).to_list(200)

            for task in today_tasks:
                assignees = list(task.get("assignees") or [])
                if task.get("assignee") and task["assignee"] not in assignees:
                    assignees.append(task["assignee"])
                for uid in assignees:
                    await _send_push_to_user(uid, "Task Due Today", f'"{task["title"]}" is due today!', f"/tasks?task={task['id']}")

            total = len(due_tasks) + len(today_tasks)
            if total:
                logger.info(f"Sent due-date reminders for {total} tasks ({len(today_tasks)} today, {len(due_tasks)} tomorrow)")

            # Daily birthday & anniversary check (once per day, during 08:00-09:00 UTC hour)
            now = datetime.now(timezone.utc)
            if last_birthday_check_date != date.today() and now.hour == 8:
                await _fire_birthday_anniversary_notifications()
                await _fire_scheduled_customer_statements()
                await _fire_overdue_payment_reminders()
                await _fire_overdue_task_emails()
                await _fire_overdue_task_director_digest()
                await _fire_payday_payslip_generation()
                # Phase A: recurring journal entries / bills
                try:
                    from routers.bank import fire_due_recurring_entries
                    await fire_due_recurring_entries()
                except Exception as e:
                    logger.error(f"fire_due_recurring_entries: {e}")
                last_birthday_check_date = date.today()

            # Daily AUTO-BACKUP — runs once per day during the midnight UTC hour.
            # Writes to /app/backend/backups/, prunes anything older than 30 days.
            global _last_auto_backup_date
            if _last_auto_backup_date != date.today() and now.hour == 0:
                await _fire_auto_backup()
                _last_auto_backup_date = date.today()
        except Exception as e:
            logger.error(f"Due-date scheduler error: {e}")
        await asyncio.sleep(3600)  # Run every hour


async def _fire_scheduled_customer_statements():
    """Daily 08:00 UTC: check scheduled statements due today (weekly/monthly) and auto-email them."""
    try:
        today = datetime.now(timezone.utc)
        weekday = today.weekday()  # 0=Mon
        dom = today.day
        scheds = await db.statement_schedules.find({"active": True}, {"_id": 0}).to_list(1000)
        for s in scheds:
            cadence = s.get("cadence")
            due = False
            if cadence == "weekly" and (s.get("day_of_week") or 0) == weekday:
                due = True
            elif cadence == "monthly" and (s.get("day_of_month") or 1) == dom:
                due = True
            if not due:
                continue
            try:
                from routers.statements import _render_statement_html, _html_to_pdf
                # Compute period: weekly = last 7 days, monthly = last month
                if cadence == "weekly":
                    pf = (today - timedelta(days=7)).strftime("%Y-%m-%d")
                else:
                    pf = (today.replace(day=1) - timedelta(days=1)).replace(day=1).strftime("%Y-%m-%d")
                pt = today.strftime("%Y-%m-%d")
                customer = await db.customer_accounts.find_one({"id": s.get("customer_id")}, {"_id": 0}) or {}
                sale_q = {
                    "$or": [{"customer_id": s.get("customer_id")}, {"customer_name": customer.get("name", "")}],
                    "voided": {"$ne": True},
                    "created_at": {"$gte": pf + "T00:00:00", "$lte": pt + "T23:59:59.999"},
                }
                sales = await db.sales.find(sale_q, {"_id": 0}).to_list(2000)
                if not sales:
                    continue  # skip empty statements
                to_email = s.get("email_override") or customer.get("email")
                if not to_email:
                    continue
                html = _render_statement_html(customer, sales, pf, pt)
                pdf = _html_to_pdf(html)
                import resend
                resend.api_key = os.environ.get("RESEND_API_KEY", "")
                sender = os.environ.get("SENDER_EMAIL", "no-reply@5812global.org")
                if not resend.api_key:
                    continue
                resend.Emails.send({
                    "from": sender, "to": to_email,
                    "subject": f"Your 58:12 {cadence} statement ({pf} → {pt})",
                    "html": f"<p>Hi {customer.get('name', '')},</p><p>Your {cadence} statement is attached.</p><p>— 58:12 Global</p>",
                    "attachments": [{"filename": f"statement-{pf}-{pt}.pdf", "content": list(pdf)}],
                })
                await db.statement_emails.insert_one({
                    "id": f"stmt_{uuid.uuid4().hex[:8]}",
                    "customer_id": s.get("customer_id"),
                    "customer_name": customer.get("name"),
                    "to_email": to_email,
                    "period_from": pf, "period_to": pt,
                    "sales_count": len(sales),
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "auto_scheduled": True,
                    "cadence": cadence,
                })
            except Exception as e:
                logger.error(f"Auto-statement send for customer {s.get('customer_id')}: {e}")
    except Exception as e:
        logger.error(f"Scheduled statements error: {e}")


async def _fire_auto_backup():
    """Daily 00:00 UTC: snapshot the full app to /app/backend/backups/.
    Keeps the last 30 daily backups, prunes older ones. Audit-included so
    historical changes don't disappear from the rolling cold store."""
    import os as _os
    BACKUPS_DIR = "/app/backend/backups"
    try:
        from routers.backup import _build_tarball
    except Exception as e:
        logger.error(f"auto-backup: backup module unavailable: {e}")
        return
    try:
        _os.makedirs(BACKUPS_DIR, exist_ok=True)
        system_user = {"id": "system_scheduler", "name": "System Auto-Backup"}
        blob = await _build_tarball(include_audit=True, current_user=system_user)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = _os.path.join(BACKUPS_DIR, f"auto-daily-{stamp}.tar.gz")
        with open(path, "wb") as f:
            f.write(blob)
        logger.info(f"Auto-backup written: {path} ({len(blob)} bytes)")
        # Prune anything older than 30 days
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        pruned = 0
        for fn in _os.listdir(BACKUPS_DIR):
            if not fn.startswith("auto-daily-") or not fn.endswith(".tar.gz"):
                continue
            full = _os.path.join(BACKUPS_DIR, fn)
            try:
                if datetime.fromtimestamp(_os.path.getmtime(full), tz=timezone.utc) < cutoff:
                    _os.unlink(full)
                    pruned += 1
            except Exception:
                pass
        if pruned:
            logger.info(f"Auto-backup pruned {pruned} archives older than 30 days")
    except Exception as e:
        logger.error(f"Auto-backup error: {e}")


async def _fire_overdue_task_emails():
    """Daily 08:00 UTC: email assignees about tasks past their due_date that are still open.
    Idempotent — tracked via `task_overdue_emails` collection so each (task_id, assignee) pair
    receives at most one email per 3-day window. Uses the dynamic email config so admin
    updates via the Integrations UI take effect without redeploying."""
    try:
        from email_helpers import send_notification_email
        today_iso = date.today().isoformat()
        cutoff_3d = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        # Open tasks past due (respects per-task snoozes)
        overdue = await db.tasks.find({
            "due_date": {"$lt": today_iso, "$ne": ""},
            "is_archived": {"$ne": True},
            "status": {"$ne": "done"},
            "$or": [{"snooze_until": {"$exists": False}}, {"snooze_until": {"$lte": today_iso}}],
        }, {"_id": 0, "id": 1, "title": 1, "due_date": 1, "assignees": 1, "assignee": 1, "board_id": 1, "description": 1}).to_list(500)
        if not overdue:
            return
        sent_count = 0
        for task in overdue:
            assignees = list(task.get("assignees") or [])
            if task.get("assignee") and task["assignee"] not in assignees:
                assignees.append(task["assignee"])
            if not assignees:
                continue
            for uid in assignees:
                # Idempotency guard
                exists = await db.task_overdue_emails.find_one({
                    "task_id": task["id"], "user_id": uid,
                    "sent_at": {"$gt": cutoff_3d},
                })
                if exists:
                    continue
                user = await db.users.find_one({"id": uid}, {"_id": 0, "email": 1, "name": 1})
                if not user or not user.get("email"):
                    continue
                # Always send push + write an in-app notification (deep-linked
                # to the specific task card so clicking the bell jumps straight
                # to it). Idempotency for the in-app row is enforced by the
                # existing `task_overdue_emails` insert below — the email row
                # is only inserted once per 3-day window, so we mirror the
                # in-app write into the same gate to prevent duplicates in
                # the bell dropdown.
                deep_link = f"/tasks?task={task['id']}"
                try:
                    await _send_push_to_user(uid, "Task Overdue", f'"{task["title"]}" is past due', deep_link)
                except Exception:
                    pass
                days_late = (date.today() - date.fromisoformat(task["due_date"])).days
                try:
                    from routers.notifications import create_notification
                    await create_notification(
                        f"Task overdue: {task.get('title') or ''}",
                        f"{days_late} day(s) past due (due {task['due_date']})",
                        uid, "warning", deep_link,
                    )
                except Exception as ne:
                    logger.warning(f"task overdue in-app notify for {uid}: {ne}")
                title = (task.get("title") or "").replace("<", "&lt;").replace(">", "&gt;")
                desc = (task.get("description") or "")[:300].replace("<", "&lt;").replace(">", "&gt;")
                body = (
                    f"<p>Hi {(user.get('name') or '').split()[0] or 'there'},</p>"
                    f"<p>Your task <strong>{title}</strong> is <strong>{days_late} day(s) past due</strong> "
                    f"(due {task['due_date']}).</p>"
                    f"{f'<p>{desc}</p>' if desc else ''}"
                    f"<p>Please log in to update it or push the due date.</p>"
                )
                send_ok = False
                try:
                    send_ok = await send_notification_email(
                        user["email"],
                        f"Task overdue: {title} ({days_late}d late)",
                        body,
                    )
                    if send_ok:
                        sent_count += 1
                except Exception as e:
                    logger.warning(f"task overdue email to {user.get('email')}: {e}")
                # Always write idempotency row so we don't retry every day even when Resend
                # rejects (e.g. testing-mode sender restrictions). Staff can re-send manually
                # via the existing per-task UI if needed.
                try:
                    await db.task_overdue_emails.insert_one({
                        "id": f"toe_{uuid.uuid4().hex[:8]}",
                        "task_id": task["id"], "user_id": uid,
                        "user_email": user["email"], "days_late": days_late,
                        "sent_at": datetime.now(timezone.utc).isoformat(),
                        "delivered": send_ok,
                    })
                except Exception as e:
                    logger.warning(f"task_overdue_emails insert: {e}")
        if sent_count:
            logger.info(f"Sent {sent_count} overdue-task emails")
    except Exception as e:
        logger.error(f"Overdue task email scheduler error: {e}")


async def _fire_overdue_task_director_digest():
    """Daily 08:00 UTC: send each director a SINGLE morning digest email listing
    every overdue task in their scope. Complements `_fire_overdue_task_emails`
    (which targets individual assignees). Idempotent — one row in
    `task_director_digests` per (director, date) means the same director never
    gets two digests in one day even if the scheduler ticks twice.

    Scope rules:
      - admin / system_admin / Executive Director / Adviser → all campuses
      - Director / Regional Director → user.location_ids ∪ user.active_campus_id
    Task→location resolves via `task.location_id` when present, else falls back
    to the parent board's location_id.
    """
    try:
        from email_helpers import send_notification_email
        today_iso = date.today().isoformat()
        overdue = await db.tasks.find({
            "due_date": {"$lt": today_iso, "$ne": ""},
            "is_archived": {"$ne": True},
            "status": {"$ne": "done"},
            "$or": [{"snooze_until": {"$exists": False}}, {"snooze_until": {"$lte": today_iso}}],
        }, {"_id": 0, "id": 1, "title": 1, "due_date": 1, "assignees": 1, "assignee": 1,
             "location_id": 1, "board_id": 1}).to_list(2000)
        if not overdue:
            return

        # Preload assignee names + board→location fallbacks in one pass
        assignee_ids = set()
        board_ids = set()
        for t in overdue:
            for uid in (t.get("assignees") or []):
                assignee_ids.add(uid)
            if t.get("assignee"):
                assignee_ids.add(t["assignee"])
            if t.get("board_id"):
                board_ids.add(t["board_id"])
        assignee_names = {}
        if assignee_ids:
            async for u in db.users.find({"id": {"$in": list(assignee_ids)}},
                                          {"_id": 0, "id": 1, "name": 1}):
                assignee_names[u["id"]] = u.get("name", "")
        board_locs = {}
        if board_ids:
            async for b in db.boards.find({"id": {"$in": list(board_ids)}},
                                           {"_id": 0, "id": 1, "location_id": 1}):
                if b.get("location_id"):
                    board_locs[b["id"]] = b["location_id"]

        # Every director+ role receives the digest
        director_roles = ["director", "Director", "Executive Director", "Adviser",
                          "Regional Director", "admin", "system_admin"]
        global_roles = {"admin", "system_admin", "Executive Director", "Adviser"}
        directors = await db.users.find({
            "role": {"$in": director_roles},
            "status": {"$ne": "deleted"},
            "email": {"$exists": True, "$ne": ""},
        }, {"_id": 0, "id": 1, "email": 1, "name": 1, "role": 1,
             "location_ids": 1, "active_campus_id": 1}).to_list(500)

        sent = 0
        for d in directors:
            already = await db.task_director_digests.find_one({"user_id": d["id"], "date": today_iso})
            if already:
                continue
            if d.get("role") in global_roles:
                scope_ids = None  # everything
            else:
                scope_ids = set(d.get("location_ids") or [])
                if d.get("active_campus_id"):
                    scope_ids.add(d["active_campus_id"])
                if not scope_ids:
                    continue
            mine = []
            for t in overdue:
                loc = t.get("location_id") or board_locs.get(t.get("board_id"))
                if scope_ids is None or (loc and loc in scope_ids):
                    mine.append(t)
            if not mine:
                continue

            def _row(t):
                days_late = (date.today() - date.fromisoformat(t["due_date"])).days
                title = (t.get("title") or "").replace("<", "&lt;").replace(">", "&gt;")
                asgn_ids = list(t.get("assignees") or [])
                if t.get("assignee") and t["assignee"] not in asgn_ids:
                    asgn_ids.append(t["assignee"])
                asgn_str = ", ".join(assignee_names.get(u, u[:8]) for u in asgn_ids) or "—"
                return (
                    "<tr>"
                    f"<td style='padding:6px 8px;border-bottom:1px solid #eee'>{title}</td>"
                    f"<td style='padding:6px 8px;border-bottom:1px solid #eee;color:#dc2626;font-weight:600'>{days_late}d</td>"
                    f"<td style='padding:6px 8px;border-bottom:1px solid #eee;font-family:monospace;font-size:11px'>{t['due_date']}</td>"
                    f"<td style='padding:6px 8px;border-bottom:1px solid #eee'>{asgn_str}</td>"
                    "</tr>"
                )
            rows_html = "".join(_row(t) for t in mine[:200])
            first_name = ((d.get("name") or "").split()[0] if d.get("name") else "") or "there"
            body = (
                f"<p>Hi {first_name},</p>"
                f"<p>Here is your morning digest of <strong>{len(mine)} overdue task(s)</strong> in your scope.</p>"
                "<table style='border-collapse:collapse;width:100%;font-size:13px'>"
                "<thead><tr style='background:#f8fafc;text-align:left'>"
                "<th style='padding:6px 8px'>Task</th>"
                "<th style='padding:6px 8px'>Late</th>"
                "<th style='padding:6px 8px'>Due</th>"
                "<th style='padding:6px 8px'>Assignee(s)</th>"
                f"</tr></thead><tbody>{rows_html}</tbody></table>"
                "<p style='margin-top:12px;color:#64748b;font-size:12px'>"
                "Log in to review, reassign, or push these dates."
                "</p>"
            )
            send_ok = False
            try:
                send_ok = await send_notification_email(
                    d["email"],
                    f"Morning digest — {len(mine)} overdue task(s) at your campus",
                    body,
                )
                if send_ok:
                    sent += 1
            except Exception as e:
                logger.warning(f"director digest to {d.get('email')}: {e}")
            try:
                await db.task_director_digests.insert_one({
                    "id": f"tdd_{uuid.uuid4().hex[:8]}",
                    "user_id": d["id"], "email": d["email"], "date": today_iso,
                    "task_count": len(mine),
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "delivered": send_ok,
                })
            except Exception:
                pass
        if sent:
            logger.info(f"Sent overdue-task digest to {sent} director(s)")
    except Exception as e:
        logger.error(f"Director digest scheduler error: {e}")


async def _fire_payday_payslip_generation():
    """Daily 08:00 UTC: auto-generate draft payslips for any campus whose payday is today.
    Idempotent — _generate_payslips_for skips salaries that already have a payslip for the period."""
    try:
        today = datetime.now(timezone.utc)
        today_iso = today.strftime("%Y-%m-%d")
        today_day = today.day
        period = f"{today.year:04d}-{today.month:02d}"
        # Match the same logic as POST /hr/payslips/generate-payday
        settings = await db.hr_settings.find({
            "hr_enabled": True,
            "$or": [{"next_pay_date": today_iso}, {"pay_day": today_day}],
        }, {"_id": 0, "location_id": 1, "pay_day": 1, "next_pay_date": 1}).to_list(100)
        if not settings:
            return
        from routers.hr import _generate_payslips_for
        system_user = {"id": "system_scheduler", "name": "System Scheduler", "role": "system_admin"}
        total = 0
        for s in settings:
            loc_id = s.get("location_id") or ""
            if not loc_id:
                continue
            try:
                res = await _generate_payslips_for(period, loc_id, system_user)
                total += res.get("generated", 0)
                # Advance next_pay_date by 1 month if it matched today (avoid re-firing tomorrow)
                if s.get("next_pay_date") == today_iso:
                    # Compute next month same day; if day overflows, clamp to last of month.
                    month = today.month + 1
                    year = today.year + (1 if month > 12 else 0)
                    if month > 12:
                        month -= 12
                    try:
                        next_dt = today.replace(year=year, month=month)
                    except ValueError:
                        # day overflow (e.g. 31st → Feb) — fall back to last day of next month
                        import calendar as _cal
                        last_day = _cal.monthrange(year, month)[1]
                        next_dt = today.replace(year=year, month=month, day=last_day)
                    await db.hr_settings.update_one(
                        {"location_id": loc_id},
                        {"$set": {"next_pay_date": next_dt.strftime("%Y-%m-%d")}},
                    )
            except Exception as e:
                logger.warning(f"payday payslip gen for {loc_id}: {e}")
        if total:
            logger.info(f"Auto-generated {total} payslips on payday {today_iso} (period {period})")
    except Exception as e:
        logger.error(f"Payday payslip scheduler error: {e}")


async def _fire_overdue_payment_reminders():
    """Daily 08:00 UTC: tiered dunning ladder.
    Tier 1 (gentle) ≥ 14d, Tier 2 (firmer) ≥ 30d, Tier 3 (final) ≥ 60d.
    Skips customers with active "payment_promise" until the promised_date.
    Idempotent — won't repeat the same tier; advances to the next when threshold crossed."""
    try:
        now = datetime.now(timezone.utc)
        cutoff_14 = (now - timedelta(days=14)).isoformat()
        # Aggregate pending sales ≥ 14d old
        pending = await db.sales.find({
            "payment_status": "pending",
            "voided": {"$ne": True},
            "created_at": {"$lte": cutoff_14},
        }, {"_id": 0}).to_list(2000)
        if not pending:
            return
        by_customer = {}
        for s in pending:
            key = s.get("customer_id") or s.get("customer_name") or "unknown"
            if key == "unknown" or key.lower().startswith("walk-in"):
                continue
            by_customer.setdefault(key, []).append(s)
        sent_count = 0
        for cust_key, sales in by_customer.items():
            try:
                # Active payment_promise — skip until promised_date elapses
                promise = await db.payment_promises.find_one({
                    "customer_key": cust_key,
                    "status": "active",
                })
                if promise and promise.get("promised_date"):
                    try:
                        promised = datetime.fromisoformat(promise["promised_date"].replace("Z", "+00:00"))
                        if promised >= now:
                            continue
                    except Exception:
                        pass

                oldest_days = max(((now - datetime.fromisoformat(o["created_at"].replace("Z", "+00:00"))).days) for o in sales)
                # Pick the next tier
                if oldest_days >= 60:
                    next_tier = 3
                elif oldest_days >= 30:
                    next_tier = 2
                else:
                    next_tier = 1
                # Was this tier already sent?
                already = await db.payment_reminders.find_one({
                    "customer_key": cust_key,
                    "tier": next_tier,
                })
                if already:
                    continue

                from routers.statements import _render_statement_html, _html_to_pdf
                customer = await db.customer_accounts.find_one(
                    {"$or": [{"id": cust_key}, {"name": cust_key}]},
                    {"_id": 0}
                ) or {}
                to_email = customer.get("email") or (sales[0].get("customer_email") if sales else None)
                if not to_email:
                    continue
                period_from = (now - timedelta(days=90)).strftime("%Y-%m-%d")
                period_to = now.strftime("%Y-%m-%d")
                total_outstanding = sum(float(s.get("total") or 0) for s in sales)
                full_sales = await db.sales.find({
                    "$or": [{"customer_id": cust_key}, {"customer_name": customer.get("name") or cust_key}],
                    "voided": {"$ne": True},
                    "created_at": {"$gte": period_from + "T00:00:00", "$lte": period_to + "T23:59:59.999"},
                }, {"_id": 0}).sort("created_at", 1).to_list(2000)
                html = _render_statement_html(customer, full_sales, period_from, period_to)
                pdf = _html_to_pdf(html)
                import resend
                resend.api_key = os.environ.get("RESEND_API_KEY", "")
                sender = os.environ.get("SENDER_EMAIL", "no-reply@5812global.org")
                if not resend.api_key:
                    continue
                currency = sales[0].get("items", [{}])[0].get("currency") if sales[0].get("items") else "UGX"

                # Build tier-specific copy + subject
                if next_tier == 1:
                    subject = f"Friendly reminder: Outstanding balance — {currency} {total_outstanding:,.2f}"
                    intro = (f"<p>This is a friendly reminder of <strong>{len(sales)} outstanding payment(s)</strong> "
                             f"totalling <strong style='color:#b45309;'>{currency} {total_outstanding:,.2f}</strong>. "
                             f"The oldest is <strong>{oldest_days} days</strong> old.</p>"
                             f"<p>If you have already paid, please disregard. Otherwise, kindly settle at your earliest convenience.</p>")
                    cc = None
                elif next_tier == 2:
                    late_fee = total_outstanding * 0.05
                    subject = f"Second notice: please settle {currency} {total_outstanding:,.2f}"
                    intro = (f"<p>We have not yet received payment for <strong>{len(sales)} invoice(s)</strong> "
                             f"totalling <strong style='color:#b45309;'>{currency} {total_outstanding:,.2f}</strong>. "
                             f"The oldest is now <strong>{oldest_days} days</strong> overdue.</p>"
                             f"<p>To avoid a possible late fee of approximately <strong>{currency} {late_fee:,.2f}</strong> "
                             f"(≈5%), please arrange payment within the next 7 days. If you have already paid, please reply with confirmation.</p>")
                    cc = None
                else:  # tier 3 — final
                    subject = f"FINAL NOTICE: {currency} {total_outstanding:,.2f} overdue"
                    intro = (f"<p>This is our <strong>final reminder</strong> regarding <strong>{len(sales)} unpaid invoice(s)</strong> "
                             f"totalling <strong style='color:#b45309;'>{currency} {total_outstanding:,.2f}</strong>. "
                             f"The oldest is now <strong>{oldest_days} days</strong> overdue.</p>"
                             f"<p>If payment is not received within 7 days, the account may be referred to management. "
                             f"Please contact us immediately if there are any issues.</p>")
                    # CC manager — look up a director/manager in the customer's home location if available
                    cc = None
                    try:
                        loc_id = (sales[0] or {}).get("location_id")
                        if loc_id:
                            mgr = await db.users.find_one({
                                "location_id": loc_id,
                                "role": {"$in": ["Manager", "Director", "Executive Director"]},
                                "status": "active",
                                "email": {"$exists": True, "$ne": ""},
                            }, {"_id": 0, "email": 1})
                            if mgr and mgr.get("email"):
                                cc = [mgr["email"]]
                    except Exception:
                        cc = None

                body = (f"<div style='font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;'>"
                        f"<img src='https://i0.wp.com/5812-global.org/wp-content/uploads/2021/12/rgb_global_h.png?w=400&ssl=1' style='height: 40px; margin-bottom: 20px;' />"
                        f"<p>Hi {customer.get('name') or cust_key},</p>"
                        f"{intro}"
                        f"<p>A full statement is attached for your reference.</p>"
                        f"<p>Thank you,<br/>58:12 Global</p></div>")
                payload = {
                    "from": sender, "to": to_email,
                    "subject": subject,
                    "html": body,
                    "attachments": [{"filename": f"statement-{period_from}-{period_to}.pdf", "content": list(pdf)}],
                }
                if cc:
                    payload["cc"] = cc
                resend.Emails.send(payload)
                await db.payment_reminders.insert_one({
                    "id": f"rem_{uuid.uuid4().hex[:8]}",
                    "customer_key": cust_key,
                    "customer_name": customer.get("name") or cust_key,
                    "to_email": to_email,
                    "cc": cc or [],
                    "tier": next_tier,
                    "outstanding_total": total_outstanding,
                    "outstanding_count": len(sales),
                    "oldest_days": oldest_days,
                    "sent_at": now.isoformat(),
                    "auto_triggered": True,
                })
                sent_count += 1
            except Exception as e:
                logger.error(f"Auto payment-reminder for {cust_key}: {e}")
        if sent_count:
            logger.info(f"Auto-sent {sent_count} payment reminders (tiered)")
    except Exception as e:
        logger.error(f"Overdue payment reminders error: {e}")


async def _fire_birthday_anniversary_notifications():
    """Create in-app notifications for today's birthdays + work anniversaries across all members.
    Safe + idempotent per day (scheduler only calls once per day)."""
    try:
        today = date.today()
        mm_dd = f"-{today.month:02d}-{today.day:02d}"
        # Birthdays: match any date_of_birth ending with -MM-DD
        birthday_people = await db.members.find(
            {"date_of_birth": {"$regex": f"{mm_dd}$"}, "status": "active"},
            {"_id": 0, "id": 1, "name": 1, "location_id": 1, "date_of_birth": 1}
        ).to_list(500)
        # Work anniversaries: match join_date ending with -MM-DD
        anniversary_people = await db.members.find(
            {"join_date": {"$regex": f"{mm_dd}$"}, "status": "active"},
            {"_id": 0, "id": 1, "name": 1, "location_id": 1, "join_date": 1, "role": 1}
        ).to_list(500)

        fired = 0
        for m in birthday_people:
            try:
                years = today.year - int((m.get("date_of_birth") or "0000")[:4])
            except Exception:
                years = 0
            if years <= 0:
                continue
            # Idempotency: skip if a birthday notification for this member was already fired today
            existing = await db.notifications.find_one({
                "kind": "birthday",
                "ref_member_id": m.get("id"),
                "created_at": {"$gte": today.isoformat()},
            })
            if existing:
                continue
            msg = f"🎂 {m.get('name', 'Someone')} turns {years} today!"
            await db.notifications.insert_one({
                "id": f"notif_{uuid.uuid4().hex[:10]}",
                "title": "Birthday today",
                "message": msg,
                "type": "info",
                "target_role": None,
                "link": "/members",
                "read_by": [],
                "location_id": m.get("location_id"),
                "kind": "birthday",
                "ref_member_id": m.get("id"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            fired += 1

        for m in anniversary_people:
            try:
                years = today.year - int((m.get("join_date") or "0000")[:4])
            except Exception:
                years = 0
            if years <= 0:
                continue
            existing = await db.notifications.find_one({
                "kind": "anniversary",
                "ref_member_id": m.get("id"),
                "created_at": {"$gte": today.isoformat()},
            })
            if existing:
                continue
            title = "Work anniversary" if (m.get("role") or "").lower() in {"staff", "manager", "director", "leader", "coordinator", "admin", "hr"} else "Member anniversary"
            msg = f"🎉 {m.get('name', 'Someone')} — {years} year{'s' if years > 1 else ''} with us today!"
            await db.notifications.insert_one({
                "id": f"notif_{uuid.uuid4().hex[:10]}",
                "title": title,
                "message": msg,
                "type": "info",
                "target_role": None,
                "link": "/members",
                "read_by": [],
                "location_id": m.get("location_id"),
                "kind": "anniversary",
                "ref_member_id": m.get("id"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            fired += 1

        if fired:
            logger.info(f"Fired {fired} birthday/anniversary notifications ({len(birthday_people)} birthdays, {len(anniversary_people)} anniversaries)")
    except Exception as e:
        logger.error(f"Birthday/anniversary fire error: {e}")


async def _run_flight_status_refresh_loop_placeholder():
    """Retired — fare-alerts feature was wiped in iter 326."""
    return


async def _run_flight_status_refresh_loop():
    """Every 15 min, refresh AI flight status for shipments whose overall status
    is `shipped` (or which have at least one flight in `departed`/`in_air`).
    Best-effort — errors are logged and the loop continues."""
    await asyncio.sleep(60)  # let startup + seeding finish first
    while True:
        try:
            from routers.shipments_pkg.airport import _refresh_flight_status_for
            cursor = db.shipments.find({
                "mode": "airport",
                "$or": [
                    {"status": "shipped"},
                    {"flights.status": {"$in": ["departed", "in_air", "boarding"]}},
                ],
            }, {"_id": 0})
            total = 0
            async for s in cursor:
                try:
                    total += await _refresh_flight_status_for(s)
                except Exception as ex:
                    logger.warning(f"Flight refresh error for {s.get('id')}: {ex}")
            if total:
                logger.info(f"Flight status refresh cycle: updated {total} flights")
        except Exception as ex:
            logger.warning(f"Flight refresh loop error: {ex}")
        await asyncio.sleep(15 * 60)  # 15 minutes
