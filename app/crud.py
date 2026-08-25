import calendar
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

import models

BERLIN = ZoneInfo("Europe/Berlin")

WEEKDAYS = [
    ("mon", "Montag"),
    ("tue", "Dienstag"),
    ("wed", "Mittwoch"),
    ("thu", "Donnerstag"),
    ("fri", "Freitag"),
    ("sat", "Samstag"),
    ("sun", "Sonntag"),
]

RANGE_PRESETS = [
    ("all", "Alle Daten"),
    ("today", "Heute"),
    ("yesterday", "Gestern"),
    ("last7", "Letzte 7 Tage"),
    ("last14", "Letzte 14 Tage"),
    ("last30", "Letzte 30 Tage"),
    ("last90", "Letzte 90 Tage"),
    ("last6m", "Letzte 6 Monate"),
    ("last12m", "Letzte 12 Monate"),
    ("ytd", "Dieses Jahr bis jetzt"),
    ("mtd", "Dieser Monat bis jetzt"),
    ("wtd", "Diese Woche bis jetzt"),
    ("custom", "Benutzerdefiniert"),
]


# --------------------------------------------------------------- Settings

def get_settings(db: Session) -> "models.Settings":
    """Holt die (einzige) Settings-Zeile, legt sie mit Defaults an falls nötig."""
    settings = db.query(models.Settings).filter(models.Settings.id == 1).first()
    if not settings:
        settings = models.Settings(id=1)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


# ---------------------------------------------------------- Einsatzmittel

def list_einsatzmittel(db: Session):
    return db.query(models.Einsatzmittel).order_by(models.Einsatzmittel.name).all()


def create_einsatzmittel(db: Session, name: str) -> "models.Einsatzmittel":
    name = (name or "").strip()
    if not name:
        raise ValueError("Name darf nicht leer sein.")
    existing = db.query(models.Einsatzmittel).filter(models.Einsatzmittel.name == name).first()
    if existing:
        raise ValueError(f"Einsatzmittel „{name}“ existiert bereits.")
    em = models.Einsatzmittel(name=name)
    db.add(em)
    db.commit()
    db.refresh(em)
    return em


def get_or_create_einsatzmittel(db: Session, name: str):
    """Für den CSV-Import: legt ein fehlendes Einsatzmittel automatisch an."""
    name = (name or "").strip()
    if not name:
        return None
    em = db.query(models.Einsatzmittel).filter(models.Einsatzmittel.name == name).first()
    if em:
        return em
    em = models.Einsatzmittel(name=name)
    db.add(em)
    db.flush()
    return em


def einsatzmittel_usage_counts(db: Session) -> dict:
    rows = (
        db.query(models.Einsatz.einsatzmittel_id, func.count(models.Einsatz.id))
        .group_by(models.Einsatz.einsatzmittel_id)
        .all()
    )
    return {k: v for k, v in rows if k is not None}


def delete_einsatzmittel(db: Session, einsatzmittel_id: int):
    em = db.query(models.Einsatzmittel).filter(models.Einsatzmittel.id == einsatzmittel_id).first()
    if not em:
        raise ValueError("Einsatzmittel nicht gefunden.")
    in_use = db.query(models.Einsatz).filter(models.Einsatz.einsatzmittel_id == em.id).count()
    if in_use:
        raise ValueError(
            f"Einsatzmittel „{em.name}“ wird noch in {in_use} Einsatz/Einsätzen "
            "verwendet und kann nicht gelöscht werden."
        )
    db.delete(em)
    db.commit()


# --------------------------------------------------------------- Einsätze

def next_nummer(db: Session) -> int:
    max_n = db.query(func.max(models.Einsatz.nummer)).scalar()
    return (max_n or 0) + 1


def make_room_for_nummer(db: Session, nummer: int, exclude_id: int = None):
    """Zählt alle Einsätze mit nummer >= dem Zielwert eins hoch, damit die
    Zielnummer frei wird. Höchste Nummer zuerst, damit unter dem unique
    constraint nie zwei Zeilen kurzzeitig dieselbe Nummer tragen."""
    q = db.query(models.Einsatz).filter(models.Einsatz.nummer >= nummer)
    if exclude_id is not None:
        q = q.filter(models.Einsatz.id != exclude_id)
    for row in q.order_by(models.Einsatz.nummer.desc()).all():
        row.nummer += 1
        db.flush()


def normalize_einsatz_fields(funktion, eingesetzt, angeschnauft, agt):
    """Erzwingt serverseitig dieselbe Feld-Logik wie im Formular-JS, damit
    manipulierte Requests keine inkonsistenten Zustände erzeugen können."""
    if not eingesetzt:
        funktion = models.Funktion.in_bereitstellung

    if funktion != models.Funktion.agt:
        angeschnauft = None
        agt = None
    else:
        angeschnauft = bool(angeschnauft)
        if not angeschnauft:
            agt = None

    return funktion, angeschnauft, agt


def create_einsatz(db: Session, *, nummer, start, ende, ort, art, funktion, eingesetzt,
                    alarmierung, bemerkungen, einsatzmittel_id, angeschnauft, agt) -> "models.Einsatz":
    funktion, angeschnauft, agt = normalize_einsatz_fields(funktion, eingesetzt, angeschnauft, agt)

    if db.query(models.Einsatz).filter(models.Einsatz.nummer == nummer).first():
        make_room_for_nummer(db, nummer)

    einsatz = models.Einsatz(
        nummer=nummer,
        start=start,
        ende=ende,
        ort=ort,
        art=art,
        funktion=funktion,
        eingesetzt=eingesetzt,
        alarmierung=alarmierung,
        bemerkungen=bemerkungen or None,
        einsatzmittel_id=einsatzmittel_id,
        angeschnauft=angeschnauft,
        agt=agt,
    )
    db.add(einsatz)
    db.commit()
    db.refresh(einsatz)
    return einsatz


def update_einsatz(db: Session, einsatz: "models.Einsatz", *, nummer, start, ende, ort, art,
                    funktion, eingesetzt, alarmierung, bemerkungen, einsatzmittel_id,
                    angeschnauft, agt) -> "models.Einsatz":
    funktion, angeschnauft, agt = normalize_einsatz_fields(funktion, eingesetzt, angeschnauft, agt)

    if nummer != einsatz.nummer:
        conflict = (
            db.query(models.Einsatz)
            .filter(models.Einsatz.nummer == nummer, models.Einsatz.id != einsatz.id)
            .first()
        )
        if conflict:
            make_room_for_nummer(db, nummer, exclude_id=einsatz.id)

    einsatz.nummer = nummer
    einsatz.start = start
    einsatz.ende = ende
    einsatz.ort = ort
    einsatz.art = art
    einsatz.funktion = funktion
    einsatz.eingesetzt = eingesetzt
    einsatz.alarmierung = alarmierung
    einsatz.bemerkungen = bemerkungen or None
    einsatz.einsatzmittel_id = einsatzmittel_id
    einsatz.angeschnauft = angeschnauft
    einsatz.agt = agt
    db.commit()
    db.refresh(einsatz)
    return einsatz


def delete_einsatz(db: Session, einsatz: "models.Einsatz"):
    db.delete(einsatz)
    db.commit()


def distinct_alarmierungen(db: Session):
    """Für die Autovervollständigung im Formular, häufigste zuerst."""
    rows = (
        db.query(models.Einsatz.alarmierung, func.count(models.Einsatz.id))
        .group_by(models.Einsatz.alarmierung)
        .order_by(func.count(models.Einsatz.id).desc())
        .all()
    )
    return [r[0] for r in rows]


# ------------------------------------------------------------- Zeitraum

def _months_ago(dt: datetime, n: int) -> datetime:
    month = dt.month - n
    year = dt.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def resolve_range(preset: str, from_str: str = None, to_str: str = None):
    """Liefert (start, end) als tz-aware Grenzen (Europe/Berlin). end=None
    bedeutet 'bis jetzt/unbegrenzt'. (None, None) bedeutet 'alle Daten'."""
    now = datetime.now(BERLIN)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if preset == "today":
        return today_start, None
    if preset == "yesterday":
        y_start = today_start - timedelta(days=1)
        return y_start, today_start
    if preset == "last7":
        return now - timedelta(days=7), None
    if preset == "last14":
        return now - timedelta(days=14), None
    if preset == "last30":
        return now - timedelta(days=30), None
    if preset == "last90":
        return now - timedelta(days=90), None
    if preset == "last6m":
        return _months_ago(now, 6), None
    if preset == "last12m":
        return _months_ago(now, 12), None
    if preset == "ytd":
        return today_start.replace(month=1, day=1), None
    if preset == "mtd":
        return today_start.replace(day=1), None
    if preset == "wtd":
        monday = today_start - timedelta(days=today_start.weekday())
        return monday, None
    if preset == "custom" and from_str:
        start = datetime.strptime(from_str, "%Y-%m-%d").replace(tzinfo=BERLIN)
        end = None
        if to_str:
            end_date = datetime.strptime(to_str, "%Y-%m-%d").replace(tzinfo=BERLIN)
            end = end_date + timedelta(days=1)
        return start, end
    return None, None  # "all" oder unbekannter Preset


def get_dashboard_stats(db: Session, start, end) -> dict:
    """Lädt Einsätze im Zeitraum und aggregiert alle Dashboard-Kennzahlen in
    Python (Counter). Bei der Datenmenge eines Feuerwehr-Einsatzlogs (Größen-
    ordnung Hunderte/Tausende Zeilen) ist das einfacher und DB-portabler als
    datenbankspezifische SQL-Aggregation, ohne spürbaren Performance-Nachteil."""
    q = db.query(models.Einsatz).options(joinedload(models.Einsatz.einsatzmittel))
    if start:
        q = q.filter(models.Einsatz.start >= start)
    if end:
        q = q.filter(models.Einsatz.start < end)
    rows = q.all()

    count = len(rows)
    total_seconds = sum((r.ende - r.start).total_seconds() for r in rows)
    total_hours = round(total_seconds / 3600, 1)
    avg_hours = round(total_hours / count, 2) if count else 0.0

    def dist(items, key_func):
        counter = Counter(key_func(r) for r in items)
        denom = len(items)
        result = []
        for label, cnt in counter.most_common():
            pct = round(cnt / denom * 100, 1) if denom else 0.0
            result.append({"label": label, "count": cnt, "pct": pct})
        return result

    agt_rows = [r for r in rows if r.funktion == models.Funktion.agt]
    angeschnauft_rows = [r for r in rows if r.angeschnauft]

    month_counter = Counter()
    for r in rows:
        local = r.start.astimezone(BERLIN)
        month_counter[(local.year, local.month)] += 1
    monthly = [
        {"label": f"{y}-{m:02d}", "count": c}
        for (y, m), c in sorted(month_counter.items())
    ]

    return {
        "count": count,
        "total_hours": total_hours,
        "avg_hours": avg_hours,
        "eingesetzt": dist(rows, lambda r: "Ja" if r.eingesetzt else "Nein"),
        "art": dist(rows, lambda r: r.art.value),
        "funktion": dist(rows, lambda r: r.funktion.value),
        "einsatzmittel": dist(rows, lambda r: r.einsatzmittel.name if r.einsatzmittel else "—"),
        "ort": dist(rows, lambda r: r.ort),
        "alarmierung": dist(rows, lambda r: r.alarmierung),
        "pa_einsaetze": dist(agt_rows, lambda r: "Ja" if r.angeschnauft else "Nein"),
        "pa_typen": dist(angeschnauft_rows, lambda r: r.agt.value if r.agt else "—"),
        "monthly": monthly,
    }


def weekly_report_data(db: Session) -> dict:
    """Kennzahlen der letzten 7 Tage für den wöchentlichen E-Mail-Report."""
    start = datetime.now(BERLIN) - timedelta(days=7)
    rows = (
        db.query(models.Einsatz)
        .filter(models.Einsatz.start >= start)
        .order_by(models.Einsatz.start)
        .all()
    )
    total_seconds = sum((r.ende - r.start).total_seconds() for r in rows)
    return {
        "count": len(rows),
        "total_hours": round(total_seconds / 3600, 1),
        "rows": rows,
    }
