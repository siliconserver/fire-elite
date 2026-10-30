import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import backup
import crud
import emailer
import models
import notifier
from database import SessionLocal

logger = logging.getLogger("scheduler")
TZ = "Europe/Berlin"


def _parse_hhmm(value: str, default=(6, 0)):
    try:
        h, m = value.split(":")
        return int(h), int(m)
    except Exception:
        return default


def run_weekly_report(only_user=None):
    """Verschickt den wöchentlichen Einsatz-Report per Mail an den Administrator
    und über die eingeschalteten Kanäle (Telegram, Signal) an die Benutzer.

    Mit only_user geht der Report nur an diesen Benutzer (Test aus dem Profil),
    Rückgabe ist dann die Ergebnisliste von notifier.send_to_user.
    """
    db = SessionLocal()
    try:
        settings = crud.get_settings(db)
        data = crud.weekly_report_data(db)

        if only_user is not None:
            return notifier.send_to_user(only_user, weekly_report_notification(data))

        admin_email = settings.admin_email
        if admin_email:
            emailer.send_mail(admin_email, settings.weekly_report_subject, weekly_report_mail_body(settings, data))
        else:
            logger.warning("Kein admin_email in den Einstellungen gesetzt, überspringe Wochenreport per Mail")

        notification = weekly_report_notification(data)
        for user in db.query(models.User).filter(models.User.notify_channels != "").all():
            notifier.send_to_user(user, notification)
    except Exception:
        logger.exception("Fehler beim wöchentlichen Report")
    finally:
        db.close()


def weekly_report_mail_body(settings, data) -> str:
    lines = [settings.weekly_report_intro.rstrip(), ""]
    lines.append(f"Einsätze (letzte 7 Tage): {data['count']}")
    lines.append(f"Gesamtstunden: {data['total_hours']}")
    lines.append("")
    lines.append("Einzelne Einsätze:")
    if data["rows"]:
        for r in data["rows"]:
            lines.append(
                f"  - #{r.nummer} {r.start.strftime('%d.%m.%Y %H:%M')} "
                f"{r.ort} – {r.alarmierung} ({r.art.value})"
            )
    else:
        lines.append("  -")
    return "\n".join(lines)


def weekly_report_notification(data) -> notifier.Notification:
    """Kurzfassung für Messenger (Telegram, Signal)."""
    lines = [
        "Elite Wochenreport (letzte 7 Tage)",
        f"Einsätze: {data['count']}",
        f"Gesamtstunden: {data['total_hours']}",
    ]
    for r in data["rows"]:
        lines.append(f"#{r.nummer} {r.start.strftime('%d.%m. %H:%M')} {r.ort} – {r.alarmierung}")
    return notifier.Notification(
        kind="wochenreport",
        text="\n".join(lines),
    )


def run_backup_job():
    db = SessionLocal()
    try:
        settings = crud.get_settings(db)
        backup.run_backup(retention=settings.backup_retention)
    except Exception:
        logger.exception("Fehler beim automatischen Backup")
    finally:
        db.close()


def reschedule(scheduler: BackgroundScheduler):
    """Liest die aktuellen Einstellungen und setzt alle Cron-Jobs entsprechend neu."""
    db = SessionLocal()
    try:
        settings = crud.get_settings(db)
    finally:
        db.close()

    h, m = _parse_hhmm(settings.weekly_report_time, (7, 0))
    scheduler.add_job(
        run_weekly_report,
        CronTrigger(day_of_week=settings.weekly_report_day, hour=h, minute=m, timezone=TZ),
        id="weekly_report",
        replace_existing=True,
    )

    h, m = _parse_hhmm(settings.backup_time, (3, 0))
    scheduler.add_job(
        run_backup_job,
        CronTrigger(hour=h, minute=m, timezone=TZ),
        id="backup_job",
        replace_existing=True,
    )

    logger.info(
        "Zeitplan aktualisiert: Wochenreport=%s %s Backup=%s",
        settings.weekly_report_day,
        settings.weekly_report_time,
        settings.backup_time,
    )


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=TZ)
    scheduler.start()
    reschedule(scheduler)
    return scheduler
