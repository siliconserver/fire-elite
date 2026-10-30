import io
import json
import os
from datetime import datetime

import pyotp
import qrcode
import qrcode.image.svg
from typing import List

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload
from starlette.middleware.sessions import SessionMiddleware

import auth
import backup
import crud
import csv_import
import models
import notifier
import scheduler
from crud import BERLIN
from database import Base, engine, get_db

app = FastAPI(title="Fire Elite")
app.add_middleware(
    SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", "change-me-please")
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/sw.js")
def service_worker():
    # aus dem Root-Pfad statt /static/sw.js ausgeliefert, damit der Scope
    # die ganze App abdeckt und nicht nur /static/
    with open("static/sw.js", encoding="utf-8") as f:
        js = f.read().replace("__APP_VERSION__", APP_VERSION)
    return Response(js, media_type="application/javascript", headers={"Cache-Control": "no-cache"})


MESSAGES = {
    "einsatz_created": "Einsatz wurde angelegt.",
    "einsatz_updated": "Einsatz wurde gespeichert.",
    "einsatz_deleted": "Einsatz wurde gelöscht.",
    "fahrzeug_created": "Einsatzmittel wurde angelegt.",
    "fahrzeug_deleted": "Einsatzmittel wurde gelöscht.",
    "schedule_ok": "Zeitplan gespeichert.",
    "email_ok": "E-Mail-Einstellungen gespeichert.",
    "weekly_ok": "Wochenreport wurde verschickt.",
    "user_created": "Benutzer wurde angelegt.",
    "user_exists": "Dieser Benutzername existiert bereits.",
    "user_deleted": "Benutzer wurde gelöscht.",
    "user_self": "Du kannst dich nicht selbst löschen.",
    "user_last_admin": "Der letzte Admin kann nicht gelöscht oder herabgestuft werden.",
    "user_role_updated": "Rolle wurde geändert.",
    "user_role_self": "Du kannst deine eigene Rolle nicht ändern.",
    "password_updated": "Passwort wurde geändert.",
    "password_wrong": "Aktuelles Passwort ist falsch.",
    "password_mismatch": "Die neuen Passwörter stimmen nicht überein.",
    "backup_ok": "Backup wurde erstellt.",
    "backup_error": "Backup fehlgeschlagen, siehe Server-Log.",
    "backup_deleted": "Backup wurde gelöscht.",
    "restore_ok": "Backup wurde eingespielt.",
    "restore_error": "Wiederherstellung fehlgeschlagen, siehe Server-Log.",
    "restore_not_confirmed": "Wiederherstellung abgebrochen: Bestätigung fehlt.",
    "totp_enabled": "Zwei-Faktor-Authentifizierung wurde aktiviert.",
    "totp_disabled": "Zwei-Faktor-Authentifizierung wurde deaktiviert.",
    "totp_invalid": "Code ungültig, bitte erneut versuchen.",
    "totp_disable_wrong_password": "Passwort falsch, 2FA wurde nicht deaktiviert.",
    "theme_updated": "Darstellung wurde gespeichert.",
    "notify_updated": "Benachrichtigungen wurden gespeichert.",
    "phone_invalid": "Handynummer ungültig, bitte im Format 0170 1234567 oder +49 170 1234567 eingeben.",
    "phone_updated": "Handynummer wurde gespeichert.",
    "telegram_connected": "Telegram ist verbunden.",
    "telegram_not_found": "Keine Start-Nachricht gefunden. Bitte zuerst den Link öffnen und im Bot auf „Start“ tippen.",
    "telegram_disconnected": "Telegram wurde getrennt.",
}

THEMES = {"system": "Wie Betriebssystem", "light": "Hell", "dark": "Dunkel"}
templates.env.globals["MESSAGES"] = MESSAGES

def load_changelog():
    """Liest CHANGELOG.md (Abschnitte "## <Version> (<Datum>)" mit "- " Punkten)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, "CHANGELOG.md"), os.path.join(here, "..", "CHANGELOG.md")):
        if os.path.exists(path):
            break
    else:
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("## "):
                head = line[3:].strip()
                version, _, date = head.partition(" ")
                entries.append({"version": version, "date": date.strip("()"), "items": []})
            elif line.startswith("- ") and entries:
                entries[-1]["items"].append(line[2:].strip())
    return entries


CHANGELOG = load_changelog()
APP_VERSION = CHANGELOG[0]["version"] if CHANGELOG else "unbekannt"
templates.env.globals["APP_VERSION"] = APP_VERSION
templates.env.globals["CHANGELOG"] = CHANGELOG


def current_user(request: Request, db: Session):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(models.User).filter(models.User.id == user_id).first()


def require_admin(user):
    if not user or user.role != models.Role.admin:
        raise HTTPException(403, "Nur für Admins")


def _parse_local_dt(value: str) -> datetime:
    """Interpretiert ein <input type=datetime-local> als Europe/Berlin-Zeit,
    damit die TIMESTAMPTZ-Spalte den korrekten Offset speichert (wichtig an
    Tagen der Uhrumstellung)."""
    return datetime.strptime(value, "%Y-%m-%dT%H:%M").replace(tzinfo=BERLIN)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    # create_all legt keine neuen Spalten in bestehenden Tabellen an
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS theme VARCHAR(8) NOT NULL DEFAULT 'system'"
        ))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20)"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR(32)"))
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_channels VARCHAR(255) NOT NULL DEFAULT ''"
        ))

    db = next(get_db())
    try:
        if db.query(models.User).count() == 0:
            admin_user = os.environ.get("ADMIN_USERNAME", "admin")
            admin_pw = os.environ.get("ADMIN_PASSWORD", "changeme")
            db.add(
                models.User(
                    username=admin_user,
                    password_hash=auth.hash_password(admin_pw),
                    role=models.Role.admin,
                )
            )
            db.commit()
            print(f"Admin-Benutzer '{admin_user}' angelegt.")

        crud.bereitstellung_einsatzmittel_id(db)
        db.commit()

        settings = crud.get_settings(db)
        if not settings.admin_email:
            env_admin_email = os.environ.get("ADMIN_EMAIL")
            if env_admin_email:
                settings.admin_email = env_admin_email
                db.commit()
    finally:
        db.close()

    app.state.scheduler = scheduler.start_scheduler()


# ---------------------------------------------------------------- Auth ----

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not auth.verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Benutzername oder Passwort falsch"},
            status_code=401,
        )

    if user.totp_enabled:
        request.session["pending_2fa_user_id"] = user.id
        return RedirectResponse("/login/2fa", status_code=303)

    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@app.get("/login/2fa", response_class=HTMLResponse)
def login_2fa_form(request: Request):
    if not request.session.get("pending_2fa_user_id"):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("login_2fa.html", {"request": request, "error": None})


@app.post("/login/2fa")
def login_2fa(request: Request, code: str = Form(...), db: Session = Depends(get_db)):
    user_id = request.session.get("pending_2fa_user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=303)

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.totp_enabled or not pyotp.TOTP(user.totp_secret).verify(code, valid_window=1):
        return templates.TemplateResponse(
            "login_2fa.html",
            {"request": request, "error": "Code ungültig"},
            status_code=401,
        )

    del request.session["pending_2fa_user_id"]
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/about", response_class=HTMLResponse)
def about_page(request: Request, db: Session = Depends(get_db)):
    # bewusst ohne Login-Zwang, erreichbar auch aus dem Footer der Login-Seite
    user = current_user(request, db)
    return templates.TemplateResponse("about.html", {"request": request, "user": user})


# -------------------------------------------------------------- Profil ----

def _totp_qr_svg(uri: str) -> str:
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")


def _telegram_link(user):
    telegram = notifier.CHANNELS["telegram"]
    if not telegram.is_configured() or user.telegram_chat_id:
        return None
    try:
        return telegram.link_url(user)
    except Exception as exc:
        print(f"[Telegram FEHLER] getMe: {exc}")
        return None


@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": user,
            "themes": THEMES,
            "channels": notifier.CHANNELS.values(),
            "user_channels": notifier.user_channels(user),
            "telegram_link": _telegram_link(user),
        },
    )


@app.post("/profile/theme")
def profile_theme(request: Request, theme: str = Form(...), db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if theme in THEMES:
        user.theme = theme
        db.commit()
    return RedirectResponse("/profile?msg=theme_updated", status_code=303)


@app.post("/profile/notifications")
def profile_notifications(
    request: Request,
    phone: str = Form(""),
    channels: List[str] = Form([]),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    normalized = notifier.normalize_phone(phone)
    if normalized is None:
        return RedirectResponse("/profile?msg=phone_invalid#benachrichtigungen", status_code=303)
    user.phone = normalized or None
    user.notify_channels = ",".join(c for c in channels if c in notifier.CHANNELS)
    db.commit()
    return RedirectResponse("/profile?msg=notify_updated#benachrichtigungen", status_code=303)


@app.post("/profile/telegram/connect")
def profile_telegram_connect(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    telegram = notifier.CHANNELS["telegram"]
    try:
        chat_id = telegram.find_chat_id(user)
    except Exception as exc:
        request.session["flash"] = f"Telegram: Fehler ({exc})."
        return RedirectResponse("/profile#benachrichtigungen", status_code=303)
    if not chat_id:
        return RedirectResponse("/profile?msg=telegram_not_found#benachrichtigungen", status_code=303)
    user.telegram_chat_id = chat_id
    if "telegram" not in notifier.user_channels(user):
        user.notify_channels = ",".join(notifier.user_channels(user) + ["telegram"])
    db.commit()
    return RedirectResponse("/profile?msg=telegram_connected#benachrichtigungen", status_code=303)


@app.post("/profile/telegram/disconnect")
def profile_telegram_disconnect(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    user.telegram_chat_id = None
    user.notify_channels = ",".join(c for c in notifier.user_channels(user) if c != "telegram")
    db.commit()
    return RedirectResponse("/profile?msg=telegram_disconnected#benachrichtigungen", status_code=303)


@app.post("/profile/notifications/test")
def profile_notifications_test(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    results = scheduler.run_weekly_report(only_user=user) or []
    if not results:
        flash = "Nichts verschickt: kein eingeschalteter und eingerichteter Kanal."
    else:
        flash = " ".join(
            f"{label}: verschickt." if err is None else f"{label}: Fehler ({err})."
            for label, err in results
        )
    request.session["flash"] = flash
    return RedirectResponse("/profile#benachrichtigungen", status_code=303)


@app.post("/profile/password")
def profile_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    new_password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    if not auth.verify_password(current_password, user.password_hash):
        return RedirectResponse("/profile?msg=password_wrong", status_code=303)
    if new_password != new_password_confirm:
        return RedirectResponse("/profile?msg=password_mismatch", status_code=303)

    user.password_hash = auth.hash_password(new_password)
    db.commit()
    return RedirectResponse("/profile?msg=password_updated", status_code=303)


@app.get("/profile/2fa/setup", response_class=HTMLResponse)
def profile_2fa_setup_form(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.totp_enabled:
        return RedirectResponse("/profile", status_code=303)

    secret = request.session.get("pending_totp_secret")
    if not secret:
        secret = pyotp.random_base32()
        request.session["pending_totp_secret"] = secret

    uri = pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name="Fire Elite")
    return templates.TemplateResponse(
        "profile_2fa_setup.html",
        {
            "request": request,
            "user": user,
            "secret": secret,
            "qr_svg": _totp_qr_svg(uri),
            "error": None,
        },
    )


@app.post("/profile/2fa/setup")
def profile_2fa_setup(request: Request, code: str = Form(...), db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    secret = request.session.get("pending_totp_secret")
    if not secret or not pyotp.TOTP(secret).verify(code, valid_window=1):
        return RedirectResponse("/profile/2fa/setup?msg=totp_invalid", status_code=303)

    user.totp_secret = secret
    user.totp_enabled = True
    db.commit()
    del request.session["pending_totp_secret"]
    return RedirectResponse("/profile?msg=totp_enabled", status_code=303)


@app.post("/profile/2fa/disable")
def profile_2fa_disable(
    request: Request, current_password: str = Form(...), db: Session = Depends(get_db)
):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    if not auth.verify_password(current_password, user.password_hash):
        return RedirectResponse("/profile?msg=totp_disable_wrong_password", status_code=303)

    user.totp_secret = None
    user.totp_enabled = False
    db.commit()
    return RedirectResponse("/profile?msg=totp_disabled", status_code=303)


# ---------------------------------------------------------- Dashboard ----

@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    preset: str = "all",
    from_date: str = Query(None, alias="from"),
    to_date: str = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    start, end = crud.resolve_range(preset, from_date, to_date)
    stats = crud.get_dashboard_stats(db, start, end)
    # </script> im JSON würde sonst das eingebettete <script>-Tag vorzeitig
    # beenden, falls Freitext (z.B. Bemerkungen/Ort) das enthält.
    stats_json = json.dumps(stats).replace("</", "<\\/")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            "stats_json": stats_json,
            "preset": preset,
            "from_date": from_date or "",
            "to_date": to_date or "",
            "range_presets": crud.RANGE_PRESETS,
        },
    )


# ------------------------------------------------------------ Einsätze ----

def _einsatz_form_context(request: Request, user, db: Session, einsatz=None):
    return {
        "request": request,
        "user": user,
        "einsatz": einsatz,
        "next_nummer": einsatz.nummer if einsatz else crud.next_nummer(db),
        "einsatzmittel_list": crud.list_einsatzmittel(db),
        "bereitstellung_name": models.BEREITSTELLUNG_EINSATZMITTEL,
        "alarmierungen": crud.distinct_alarmierungen(db),
        "art_options": list(models.Art),
        "funktion_options": list(models.Funktion),
        "agt_options": list(models.AgtGeraet),
    }


@app.get("/einsaetze", response_class=HTMLResponse)
def einsaetze_list(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    einsaetze = (
        db.query(models.Einsatz)
        .options(joinedload(models.Einsatz.einsatzmittel))
        .order_by(models.Einsatz.nummer.desc())
        .all()
    )
    return templates.TemplateResponse(
        "einsaetze_list.html", {"request": request, "user": user, "einsaetze": einsaetze}
    )


@app.get("/einsaetze/import", response_class=HTMLResponse)
def einsaetze_import_form(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)
    return templates.TemplateResponse(
        "einsaetze_import.html", {"request": request, "user": user, "error": None}
    )


@app.post("/einsaetze/import")
async def einsaetze_import(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)

    content = await file.read()
    try:
        result = csv_import.import_csv(db, content)
    except csv_import.CsvImportError as exc:
        return templates.TemplateResponse(
            "einsaetze_import.html",
            {"request": request, "user": user, "error": str(exc)},
            status_code=400,
        )

    msg = f"{result['imported']} Einsätze importiert."
    if result["created_einsatzmittel"]:
        msg += f" Neue Einsatzmittel angelegt: {', '.join(result['created_einsatzmittel'])}."
    request.session["flash"] = msg
    return RedirectResponse("/einsaetze", status_code=303)


@app.get("/einsaetze/new", response_class=HTMLResponse)
def einsatz_new_form(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)
    return templates.TemplateResponse("einsatz_form.html", _einsatz_form_context(request, user, db))


@app.post("/einsaetze/new")
def einsatz_new(
    request: Request,
    nummer: int = Form(...),
    start: str = Form(...),
    ende: str = Form(...),
    ort: str = Form(...),
    art: str = Form(...),
    funktion: str = Form(...),
    eingesetzt: str = Form(None),
    alarmierung: str = Form(...),
    bemerkungen: str = Form(""),
    einsatzmittel_id: str = Form(""),
    angeschnauft: str = Form(None),
    agt: str = Form(""),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)

    crud.create_einsatz(
        db,
        nummer=nummer,
        start=_parse_local_dt(start),
        ende=_parse_local_dt(ende),
        ort=ort.strip(),
        art=models.Art(art),
        funktion=models.Funktion(funktion),
        eingesetzt=bool(eingesetzt),
        alarmierung=alarmierung.strip(),
        bemerkungen=bemerkungen,
        einsatzmittel_id=int(einsatzmittel_id) if einsatzmittel_id else None,
        angeschnauft=bool(angeschnauft),
        agt=models.AgtGeraet(agt) if agt else None,
    )
    return RedirectResponse("/einsaetze?msg=einsatz_created", status_code=303)


@app.get("/einsaetze/{einsatz_id}", response_class=HTMLResponse)
def einsatz_detail(einsatz_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    einsatz = (
        db.query(models.Einsatz)
        .options(joinedload(models.Einsatz.einsatzmittel))
        .filter(models.Einsatz.id == einsatz_id)
        .first()
    )
    if not einsatz:
        raise HTTPException(404, "Nicht gefunden")
    return templates.TemplateResponse(
        "einsatz_detail.html", {"request": request, "user": user, "einsatz": einsatz}
    )


@app.get("/einsaetze/{einsatz_id}/edit", response_class=HTMLResponse)
def einsatz_edit_form(einsatz_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)
    einsatz = db.query(models.Einsatz).filter(models.Einsatz.id == einsatz_id).first()
    if not einsatz:
        raise HTTPException(404, "Nicht gefunden")
    return templates.TemplateResponse(
        "einsatz_form.html", _einsatz_form_context(request, user, db, einsatz)
    )


@app.post("/einsaetze/{einsatz_id}/edit")
def einsatz_edit(
    einsatz_id: int,
    request: Request,
    nummer: int = Form(...),
    start: str = Form(...),
    ende: str = Form(...),
    ort: str = Form(...),
    art: str = Form(...),
    funktion: str = Form(...),
    eingesetzt: str = Form(None),
    alarmierung: str = Form(...),
    bemerkungen: str = Form(""),
    einsatzmittel_id: str = Form(""),
    angeschnauft: str = Form(None),
    agt: str = Form(""),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)

    einsatz = db.query(models.Einsatz).filter(models.Einsatz.id == einsatz_id).first()
    if not einsatz:
        raise HTTPException(404, "Nicht gefunden")

    crud.update_einsatz(
        db,
        einsatz,
        nummer=nummer,
        start=_parse_local_dt(start),
        ende=_parse_local_dt(ende),
        ort=ort.strip(),
        art=models.Art(art),
        funktion=models.Funktion(funktion),
        eingesetzt=bool(eingesetzt),
        alarmierung=alarmierung.strip(),
        bemerkungen=bemerkungen,
        einsatzmittel_id=int(einsatzmittel_id) if einsatzmittel_id else None,
        angeschnauft=bool(angeschnauft),
        agt=models.AgtGeraet(agt) if agt else None,
    )
    return RedirectResponse(f"/einsaetze/{einsatz.id}?msg=einsatz_updated", status_code=303)


@app.post("/einsaetze/{einsatz_id}/delete")
def einsatz_delete(einsatz_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)
    einsatz = db.query(models.Einsatz).filter(models.Einsatz.id == einsatz_id).first()
    if not einsatz:
        raise HTTPException(404, "Nicht gefunden")
    crud.delete_einsatz(db, einsatz)
    return RedirectResponse("/einsaetze?msg=einsatz_deleted", status_code=303)


# ----------------------------------------------------------- Fahrzeuge ----

@app.get("/fahrzeuge", response_class=HTMLResponse)
def fahrzeuge_list(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    fahrzeuge = crud.list_einsatzmittel(db)
    counts = crud.einsatzmittel_usage_counts(db)
    return templates.TemplateResponse(
        "fahrzeuge_list.html",
        {"request": request, "user": user, "fahrzeuge": fahrzeuge, "counts": counts},
    )


@app.post("/fahrzeuge/new")
def fahrzeug_new(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)
    try:
        crud.create_einsatzmittel(db, name)
    except ValueError as exc:
        request.session["flash"] = str(exc)
        return RedirectResponse("/fahrzeuge", status_code=303)
    return RedirectResponse("/fahrzeuge?msg=fahrzeug_created", status_code=303)


@app.post("/fahrzeuge/{einsatzmittel_id}/delete")
def fahrzeug_delete(einsatzmittel_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)
    try:
        crud.delete_einsatzmittel(db, einsatzmittel_id)
    except ValueError as exc:
        request.session["flash"] = str(exc)
        return RedirectResponse("/fahrzeuge", status_code=303)
    return RedirectResponse("/fahrzeuge?msg=fahrzeug_deleted", status_code=303)


# ----------------------------------------------------------- Settings ----

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)

    settings = crud.get_settings(db)
    users = db.query(models.User).order_by(models.User.username).all()
    backups = backup.list_backups()

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "users": users,
            "backups": backups,
            "weekdays": crud.WEEKDAYS,
            "channels": notifier.CHANNELS.values(),
        },
    )


@app.post("/settings/schedule")
def settings_schedule(
    request: Request,
    weekly_report_day: str = Form(...),
    weekly_report_time: str = Form(...),
    backup_time: str = Form(...),
    backup_retention: int = Form(...),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)

    settings = crud.get_settings(db)
    settings.weekly_report_day = weekly_report_day
    settings.weekly_report_time = weekly_report_time
    settings.backup_time = backup_time
    settings.backup_retention = max(1, backup_retention)
    db.commit()

    scheduler.reschedule(app.state.scheduler)
    return RedirectResponse("/settings?msg=schedule_ok#zeitplan", status_code=303)


@app.post("/settings/email-texts")
def settings_email_texts(
    request: Request,
    admin_email: str = Form(""),
    weekly_report_subject: str = Form(...),
    weekly_report_intro: str = Form(...),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)

    settings = crud.get_settings(db)
    settings.admin_email = admin_email or None
    settings.weekly_report_subject = weekly_report_subject
    settings.weekly_report_intro = weekly_report_intro
    db.commit()

    return RedirectResponse("/settings?msg=email_ok#email", status_code=303)


@app.post("/settings/send-weekly-report-now")
def settings_send_weekly_report_now(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)
    scheduler.run_weekly_report()
    return RedirectResponse("/settings?msg=weekly_ok#email", status_code=303)


# ------------------------------------------------------ Benutzerverwaltung

@app.post("/settings/users/new")
def settings_user_new(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    phone: str = Form(""),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)

    if db.query(models.User).filter(models.User.username == username).first():
        return RedirectResponse("/settings?msg=user_exists#benutzer", status_code=303)
    normalized_phone = notifier.normalize_phone(phone)
    if normalized_phone is None:
        return RedirectResponse("/settings?msg=phone_invalid#benutzer", status_code=303)

    role_enum = models.Role.admin if role == "admin" else models.Role.viewer
    new_user = models.User(
        username=username,
        password_hash=auth.hash_password(password),
        role=role_enum,
        phone=normalized_phone or None,
    )
    db.add(new_user)
    db.commit()
    return RedirectResponse("/settings?msg=user_created#benutzer", status_code=303)


@app.post("/settings/users/{user_id}/role")
def settings_user_role(
    user_id: int,
    request: Request,
    role: str = Form(...),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)

    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(404, "Nicht gefunden")
    if target.id == user.id:
        return RedirectResponse("/settings?msg=user_role_self#benutzer", status_code=303)

    role_enum = models.Role.admin if role == "admin" else models.Role.viewer
    if target.role == models.Role.admin and role_enum == models.Role.viewer:
        remaining_admins = (
            db.query(models.User)
            .filter(models.User.role == models.Role.admin, models.User.id != target.id)
            .count()
        )
        if remaining_admins == 0:
            return RedirectResponse("/settings?msg=user_last_admin#benutzer", status_code=303)

    target.role = role_enum
    db.commit()
    return RedirectResponse("/settings?msg=user_role_updated#benutzer", status_code=303)


@app.post("/settings/users/{user_id}/phone")
def settings_user_phone(
    user_id: int,
    request: Request,
    phone: str = Form(""),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)

    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(404, "Nicht gefunden")
    normalized = notifier.normalize_phone(phone)
    if normalized is None:
        return RedirectResponse("/settings?msg=phone_invalid#benutzer", status_code=303)
    target.phone = normalized or None
    db.commit()
    return RedirectResponse("/settings?msg=phone_updated#benutzer", status_code=303)


@app.post("/settings/users/{user_id}/delete")
def settings_user_delete(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)

    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(404, "Nicht gefunden")
    if target.id == user.id:
        return RedirectResponse("/settings?msg=user_self#benutzer", status_code=303)

    remaining_admins = (
        db.query(models.User)
        .filter(models.User.role == models.Role.admin, models.User.id != target.id)
        .count()
    )
    if target.role == models.Role.admin and remaining_admins == 0:
        return RedirectResponse("/settings?msg=user_last_admin#benutzer", status_code=303)

    db.delete(target)
    db.commit()
    return RedirectResponse("/settings?msg=user_deleted#benutzer", status_code=303)


@app.post("/settings/users/{user_id}/2fa/disable")
def settings_user_2fa_disable(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)

    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(404, "Nicht gefunden")

    target.totp_secret = None
    target.totp_enabled = False
    db.commit()
    return RedirectResponse("/settings?msg=totp_disabled#benutzer", status_code=303)


# ------------------------------------------------------------- Backups ----

@app.post("/settings/backups/run")
def settings_backup_run(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)

    settings = crud.get_settings(db)
    try:
        backup.run_backup(retention=settings.backup_retention)
        return RedirectResponse("/settings?msg=backup_ok#backups", status_code=303)
    except Exception:
        return RedirectResponse("/settings?msg=backup_error#backups", status_code=303)


@app.get("/settings/backups/{filename}/download")
def settings_backup_download(filename: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)

    try:
        path = backup.backup_path(filename)
    except FileNotFoundError:
        raise HTTPException(404, "Backup nicht gefunden")
    return FileResponse(path, filename=filename, media_type="application/gzip")


@app.post("/settings/backups/{filename}/restore")
def settings_backup_restore(
    filename: str,
    request: Request,
    confirm: str = Form(""),
    db: Session = Depends(get_db),
):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)

    if confirm != "JA":
        return RedirectResponse("/settings?msg=restore_not_confirmed#backups", status_code=303)

    try:
        backup.restore_backup(filename)
        return RedirectResponse("/settings?msg=restore_ok#backups", status_code=303)
    except Exception:
        return RedirectResponse("/settings?msg=restore_error#backups", status_code=303)


@app.post("/settings/backups/{filename}/delete")
def settings_backup_delete(filename: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    require_admin(user)

    backup.delete_backup(filename)
    return RedirectResponse("/settings?msg=backup_deleted#backups", status_code=303)
