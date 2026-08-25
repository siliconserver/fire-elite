import csv
import io
from datetime import datetime

from sqlalchemy.exc import IntegrityError

import crud
import models

EXPECTED_HEADER = [
    "nummer", "start", "ende", "ort", "art", "funktion", "eingesetzt",
    "alarmierung", "bemerkungen", "einsatzmittel", "angeschnauft", "agt",
]


class CsvImportError(ValueError):
    pass


def _parse_bool(value, field, row_num):
    value = (value or "").strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise CsvImportError(f'Zeile {row_num}: Feld "{field}" muss "true" oder "false" sein, nicht "{value}".')


def _parse_optional_bool(value, field, row_num):
    value = (value or "").strip()
    if value == "":
        return None
    return _parse_bool(value, field, row_num)


def _parse_enum(value, enum_cls, field, row_num):
    value = (value or "").strip()
    try:
        return enum_cls(value)
    except ValueError:
        allowed = ", ".join(e.value for e in enum_cls)
        raise CsvImportError(
            f'Zeile {row_num}: Feld "{field}" hat ungültigen Wert "{value}" (erlaubt: {allowed}).'
        )


def _parse_optional_enum(value, enum_cls, field, row_num):
    value = (value or "").strip()
    if value == "":
        return None
    return _parse_enum(value, enum_cls, field, row_num)


def _parse_datetime(value, field, row_num):
    value = (value or "").strip()
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise CsvImportError(f'Zeile {row_num}: Feld "{field}" ist kein gültiger Zeitstempel: "{value}".')
    if dt.tzinfo is None:
        raise CsvImportError(f'Zeile {row_num}: Feld "{field}" hat keine Zeitzone: "{value}".')
    return dt


def _parse_int(value, field, row_num):
    value = (value or "").strip()
    try:
        return int(value)
    except ValueError:
        raise CsvImportError(f'Zeile {row_num}: Feld "{field}" ist keine gültige Zahl: "{value}".')


def import_csv(db, raw_bytes: bytes) -> dict:
    """Importiert Einsätze aus einer hochgeladenen CSV-Datei. Läuft in einer
    Transaktion: jeder Fehler bricht den gesamten Import ab (kein Teil-Import)."""
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CsvImportError("Datei konnte nicht als UTF-8 gelesen werden.")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or list(reader.fieldnames) != EXPECTED_HEADER:
        raise CsvImportError(
            "Spaltenüberschriften stimmen nicht mit dem erwarteten Schema überein. "
            f"Erwartet: {', '.join(EXPECTED_HEADER)}"
        )

    existing_names = {em.name for em in db.query(models.Einsatzmittel.name).all()}
    created_vehicle_names = set()
    seen_nummern = set()
    imported = 0

    try:
        for i, row in enumerate(reader, start=2):  # Zeile 1 ist der Header
            nummer = _parse_int(row["nummer"], "nummer", i)
            if nummer in seen_nummern:
                raise CsvImportError(f"Zeile {i}: Einsatznummer {nummer} kommt mehrfach in der Datei vor.")
            if db.query(models.Einsatz).filter(models.Einsatz.nummer == nummer).first():
                raise CsvImportError(f"Zeile {i}: Einsatznummer {nummer} existiert bereits in der Datenbank.")
            seen_nummern.add(nummer)

            start = _parse_datetime(row["start"], "start", i)
            ende = _parse_datetime(row["ende"], "ende", i)
            if ende < start:
                raise CsvImportError(f"Zeile {i}: „ende“ liegt vor „start“.")

            ort = (row["ort"] or "").strip()
            if not ort:
                raise CsvImportError(f'Zeile {i}: Feld "ort" darf nicht leer sein.')

            art = _parse_enum(row["art"], models.Art, "art", i)
            eingesetzt = _parse_bool(row["eingesetzt"], "eingesetzt", i)
            funktion = _parse_enum(row["funktion"], models.Funktion, "funktion", i)

            alarmierung = (row["alarmierung"] or "").strip()
            if not alarmierung:
                raise CsvImportError(f'Zeile {i}: Feld "alarmierung" darf nicht leer sein.')

            bemerkungen = (row["bemerkungen"] or "").strip() or None
            angeschnauft = _parse_optional_bool(row["angeschnauft"], "angeschnauft", i)
            agt = _parse_optional_enum(row["agt"], models.AgtGeraet, "agt", i)

            einsatzmittel_name = (row["einsatzmittel"] or "").strip()
            if einsatzmittel_name and einsatzmittel_name not in existing_names:
                created_vehicle_names.add(einsatzmittel_name)
                existing_names.add(einsatzmittel_name)
            einsatzmittel = crud.get_or_create_einsatzmittel(db, einsatzmittel_name)

            funktion, angeschnauft, agt = crud.normalize_einsatz_fields(
                funktion, eingesetzt, angeschnauft, agt
            )

            db.add(
                models.Einsatz(
                    nummer=nummer,
                    start=start,
                    ende=ende,
                    ort=ort,
                    art=art,
                    funktion=funktion,
                    eingesetzt=eingesetzt,
                    alarmierung=alarmierung,
                    bemerkungen=bemerkungen,
                    einsatzmittel_id=einsatzmittel.id if einsatzmittel else None,
                    angeschnauft=angeschnauft,
                    agt=agt,
                )
            )
            db.flush()
            imported += 1
    except (CsvImportError, IntegrityError):
        db.rollback()
        raise

    db.commit()
    return {"imported": imported, "created_einsatzmittel": sorted(created_vehicle_names)}
