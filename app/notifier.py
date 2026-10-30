"""Benachrichtigungskanäle für Personen (zusätzlich zur Admin-Mail).

Jeder Kanal hat einen Schlüssel, der in users.notify_channels gespeichert wird.
Ein neuer Kanal ist eine weitere Klasse mit key/label/is_configured/
recipient/send, eingetragen in CHANNELS.

Ein Kanal ohne Zugangsdaten in der Umgebung gilt als deaktiviert: Er wird im
Profil nur ausgegraut angezeigt und beim Versand übersprungen.
"""
import hashlib
import hmac
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class Notification:
    kind: str
    text: str


# ------------------------------------------------------------ Telefonnummer

PHONE_RE = re.compile(r"^\+[1-9]\d{6,14}$")


def normalize_phone(value: str):
    """Bringt eine eingegebene Nummer ins internationale Format (+491701234567).

    Gibt "" für leere Eingaben und None für ungültige Nummern zurück.
    Nationale Nummern (führende 0) bekommen die Ländervorwahl aus
    DEFAULT_COUNTRY_CODE (Standard 49).
    """
    value = re.sub(r"[\s/().-]", "", value or "")
    if not value:
        return ""
    if value.startswith("00"):
        value = "+" + value[2:]
    elif value.startswith("0"):
        cc = os.environ.get("DEFAULT_COUNTRY_CODE", "49").lstrip("+")
        value = f"+{cc}{value[1:]}"
    return value if PHONE_RE.match(value) else None


# --------------------------------------------------------------- HTTP-Helfer

def _request(url: str, payload: dict = None, timeout: int = 20) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"nicht erreichbar: {exc.reason}") from exc
    return json.loads(body) if body.strip() else {}


# ------------------------------------------------------------------ Telegram

class TelegramChannel:
    """Telegram-Bot (kostenlos, Token von @BotFather in TELEGRAM_BOT_TOKEN).

    Ein Bot kann niemanden über die Handynummer anschreiben. Die Person öffnet
    deshalb einmal den Link aus dem Profil (t.me/<bot>?start=<code>) und
    drückt „Start“; „Telegram verbinden“ sucht dann diese Nachricht über
    getUpdates und speichert die Chat-ID.
    """

    key = "telegram"
    label = "Telegram"
    _bot_username = None

    def _token(self):
        return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

    def _api(self, method: str, payload: dict = None) -> dict:
        result = _request(f"https://api.telegram.org/bot{self._token()}/{method}", payload)
        if not result.get("ok"):
            raise RuntimeError(result.get("description", "unbekannter Fehler"))
        return result["result"]

    def is_configured(self) -> bool:
        return bool(self._token())

    def recipient(self, user):
        return user.telegram_chat_id

    missing_recipient = "Telegram ist noch nicht verbunden"

    def send(self, user, notification: Notification) -> None:
        self._api("sendMessage", {"chat_id": user.telegram_chat_id, "text": notification.text})

    # -- Verbinden

    def bot_username(self):
        if TelegramChannel._bot_username is None:
            TelegramChannel._bot_username = self._api("getMe")["username"]
        return TelegramChannel._bot_username

    def link_code(self, user) -> str:
        secret = os.environ.get("SECRET_KEY", "change-me-please").encode()
        digest = hmac.new(secret, f"telegram:{user.id}".encode(), hashlib.sha256).hexdigest()
        return f"u{user.id}-{digest[:16]}"

    def link_url(self, user) -> str:
        return f"https://t.me/{self.bot_username()}?start={self.link_code(user)}"

    def find_chat_id(self, user):
        """Sucht in den noch nicht abgeholten Nachrichten an den Bot nach
        „/start <code>“ der Person und gibt deren Chat-ID zurück."""
        expected = f"/start {self.link_code(user)}"
        for update in reversed(self._api("getUpdates")):
            message = update.get("message") or {}
            if (message.get("text") or "").strip() == expected:
                return str(message["chat"]["id"])
        return None


# -------------------------------------------------------------------- Signal

class SignalChannel:
    """Signal über signal-cli-rest-api (kostenlos, eigener Docker-Container).

    SIGNAL_API_URL zeigt auf den Container, SIGNAL_NUMBER ist die dort
    registrierte oder verknüpfte Absender-Nummer. Empfänger ist die
    Handynummer der Person.
    """

    key = "signal"
    label = "Signal"

    def is_configured(self) -> bool:
        return bool(os.environ.get("SIGNAL_API_URL") and os.environ.get("SIGNAL_NUMBER"))

    def recipient(self, user):
        return user.phone

    missing_recipient = "keine Handynummer hinterlegt"

    def send(self, user, notification: Notification) -> None:
        _request(
            os.environ["SIGNAL_API_URL"].rstrip("/") + "/v2/send",
            {
                "message": notification.text,
                "number": os.environ["SIGNAL_NUMBER"],
                "recipients": [user.phone],
            },
        )


CHANNELS = {c.key: c for c in (TelegramChannel(), SignalChannel())}


# --------------------------------------------------------------------- API

def user_channels(user) -> list:
    """Die Kanäle, die die Person im Profil eingeschaltet hat."""
    return [k for k in (user.notify_channels or "").split(",") if k in CHANNELS]


def send_to_user(user, notification: Notification) -> list:
    """Schickt die Nachricht über alle eingeschalteten und konfigurierten Kanäle.

    Gibt eine Liste von (Kanal-Label, Fehlertext oder None) zurück.
    """
    results = []
    for key in user_channels(user):
        channel = CHANNELS[key]
        if not channel.is_configured():
            continue
        if not channel.recipient(user):
            results.append((channel.label, channel.missing_recipient))
            continue
        try:
            channel.send(user, notification)
            print(f"[{channel.label} GESENDET] user={user.username} kind={notification.kind}")
            results.append((channel.label, None))
        except Exception as exc:
            print(f"[{channel.label} FEHLER] user={user.username} kind={notification.kind}: {exc}")
            results.append((channel.label, str(exc)))
    return results
