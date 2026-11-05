# Fire Elite (Feuerwehr Einsatz- Logbuch für Individuelle Tätigkeits- und Erfassung)

Fire Elite ist ein persönliches Einsatzbuch für Feuerwehrleute. Du trägst deine
Einsätze im Browser ein (am PC oder auf dem Handy) und bekommst eine Übersicht,
wie oft, wie lange und in welcher Funktion du im Einsatz warst. Alles läuft auf
deinem eigenen Server, die Daten bleiben bei dir.

## Funktionen

- **Einsätze erfassen**: Nummer, Beginn und Ende, Ort, Einsatzart (TH, Brand,
  Dienstleistung, Gefahrstoffe), Funktion (TM, AGT, MA, FEZ, GF, EL), Fahrzeug,
  Alarmierungsstichwort, Atemschutz (angeschnauft, PA/Filter/CSA) und Bemerkungen.
  Wer nicht eingesetzt war, wird automatisch als „In Bereitstellung“ geführt.
- **Einsätze nachtragen**: Wird eine schon vergebene Einsatznummer eingetragen,
  rücken alle folgenden Nummern automatisch eins weiter.
- **Dashboard**: Einsatzzeit gesamt und im Schnitt, Anzahl Einsätze, Diagramme zu
  Einsatzarten, Funktionen, Fahrzeugen, Orten, Stichworten, Atemschutz und
  Einsätzen pro Monat. Der Zeitraum ist frei wählbar (heute, letzte 30 Tage,
  dieses Jahr, eigener Von/Bis-Zeitraum …).
- **Eigene Fahrzeuge**: Die Liste der Einsatzmittel passt du an deine Wache an.
- **CSV-Import**: Bestehende Einsätze aus einer Tabelle übernehmen (Format siehe unten).
- **Wochenreport per E-Mail**: Einmal pro Woche eine Zusammenfassung der letzten
  sieben Tage. Tag, Uhrzeit, Empfänger und Text stellst du selbst ein.
- **Wochenreport per Telegram oder Signal**: Jede Person kann sich den Report
  zusätzlich aufs Handy schicken lassen (kostenlos, Einrichtung siehe unten).
- **Backups**: Tägliche Sicherung der Datenbank, dazu manuelle Sicherung,
  Download und Wiederherstellung direkt in der Weboberfläche.
- **Benutzer und Rollen**: Admins dürfen alles, Viewer nur lesen. Optional
  Zwei-Faktor-Anmeldung mit einer Authenticator-App (Google Authenticator, Authy …).
- **App fürs Handy**: Im Browser „Zum Home-Bildschirm hinzufügen“, dann startet
  Fire Elite wie eine eigene App im Vollbild.

## Auf dem eigenen Server starten

Du brauchst einen Server (oder Raspberry Pi, NAS …) mit
[Docker](https://docs.docker.com/engine/install/) und Docker Compose.

1. **Herunterladen**: Die aktuelle Version unter
   [Releases](https://github.com/siliconserver/fire-elite/releases/latest) als ZIP
   oder tar.gz laden und auf dem Server entpacken. Gebraucht werden daraus nur
   `docker-compose.yml` und `.env.example`.

2. **Einstellungen anlegen**:
   ```bash
   cp .env.example .env
   ```
   In der `.env` mindestens diese Werte ändern:
   - `POSTGRES_PASSWORD` (und dasselbe Passwort in `DATABASE_URL`)
   - `SECRET_KEY`: ein langer Zufallswert, z. B. aus `openssl rand -hex 32`
   - `ADMIN_USERNAME` / `ADMIN_PASSWORD`: dein Login
   - `SMTP_*` und `ADMIN_EMAIL`, falls du den Wochenreport per Mail willst
   - `TELEGRAM_BOT_TOKEN` bzw. `SIGNAL_*`, falls du den Report per Messenger willst
     (siehe [Benachrichtigungen per Telegram und Signal](#benachrichtigungen-per-telegram-und-signal))

3. **Starten**:
   ```bash
   docker compose pull
   docker compose up -d
   ```

4. **Öffnen**: Im Browser `http://<server>:8086` aufrufen und mit dem Admin-Login
   aus der `.env` anmelden. Der Admin wird beim ersten Start automatisch angelegt.

### Aktualisieren

Im Ordner mit der `docker-compose.yml`:

```bash
docker compose pull && docker compose up -d
```

Standardmäßig läuft immer die neueste Version. Wer bei einer festen Version
bleiben will, trägt sie in der `.env` bei `ELITE_TAG` ein (z. B. `ELITE_TAG=1.4`).
Was sich in einer Version geändert hat, steht im [Changelog](CHANGELOG.md) und in
der App unter „Über Elite“.

### Wo liegen meine Daten?

Alles liegt im Ordner `data/` neben der `docker-compose.yml`:

```
data/
  postgres/   # die Datenbank
  backups/    # tägliche und manuelle Backups (.sql.gz)
  signal/     # nur bei Signal: das verknüpfte Signal-Konto
```

Für einen Umzug auf einen anderen Server kopierst du den ganzen Ordner
(inklusive `data/` und `.env`) und startest dort mit `docker compose up -d`.

## Benachrichtigungen per Telegram und Signal

Zusätzlich zur E-Mail an den Admin kann jede Person den Wochenreport per
Telegram oder Signal bekommen. Beide sind kostenlos. Ein Kanal, für den in der
`.env` nichts eingetragen ist, ist ausgeschaltet und erscheint im Profil
ausgegraut. Nach jeder Änderung an der `.env`: `docker compose up -d`.

Jede Person schaltet die Kanäle selbst im **Profil** unter „Benachrichtigungen“
ein und kann dort mit „Wochenreport testweise an mich schicken“ prüfen, ob es
klappt. Die Handynummer kann auch ein Admin unter **Einstellungen →
Benutzerverwaltung** eintragen. Nummern dürfen mit `0` (Deutschland, andere
Länder über `DEFAULT_COUNTRY_CODE`), `0049` oder `+49` eingegeben werden.

### Telegram

1. In Telegram den [@BotFather](https://t.me/BotFather) öffnen, `/newbot`
   schicken und Namen und Benutzernamen für den Bot vergeben (z. B. `MeineWacheEliteBot`).
2. Den Token, den der BotFather schickt, in die `.env` eintragen:
   ```
   TELEGRAM_BOT_TOKEN=123456789:ABC...
   ```
3. Jede Person öffnet im Profil den Link „Bot in Telegram öffnen“, tippt dort
   auf „Start“ und klickt danach in Elite auf „Telegram verbinden“.
   Ein Bot kann niemanden über die Handynummer anschreiben, deshalb ist dieser
   Schritt nötig. Die „Start“-Nachricht muss innerhalb von 24 Stunden verbunden werden.

### Signal

Signal hat keine offizielle Schnittstelle. Elite nutzt dafür den Container
[signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api), der in
der `docker-compose.yml` schon vorbereitet ist und nur bei Bedarf startet.

1. Signal-Container starten:
   ```bash
   docker compose --profile signal up -d
   ```
2. Ein Signal-Konto als Absender verknüpfen: Auf dem Server
   `http://localhost:8087/v1/qrcodelink?device_name=fire-elite` im Browser öffnen
   (oder per SSH-Tunnel, der Port ist nur lokal erreichbar) und den QR-Code in
   der Signal-App unter **Einstellungen → Verknüpfte Geräte** scannen.
   Die Nachrichten kommen dann von dieser Nummer. Wer dafür nicht seine eigene
   Nummer nehmen will, verknüpft ein Zweithandy oder eine eigene Signal-Nummer.
   An die eigene Nummer geschickte Reports landen in Signal unter „Notiz an mich“.
3. In der `.env` eintragen und neu starten:
   ```
   SIGNAL_API_URL=http://signal:8080
   SIGNAL_NUMBER=+491701234567
   ```
   ```bash
   docker compose --profile signal up -d
   ```
   Das `--profile signal` muss ab jetzt auch beim Aktualisieren mit angegeben werden.
4. Jede Person trägt im Profil ihre Handynummer ein und hakt „Wochenreport per Signal“ an.

Weitere Kanäle lassen sich im Code in `app/notifier.py` ergänzen (eine Klasse je Kanal).

## CSV-Import

Über den Menüpunkt **CSV-Import** lädst du eine CSV-Datei hoch. Die erste Zeile muss
genau so lauten:

```
nummer,start,ende,ort,art,funktion,eingesetzt,alarmierung,bemerkungen,einsatzmittel,angeschnauft,agt
```

- `start` / `ende` mit Zeitzone, z. B. `2021-05-22 13:05:00+02`
- `eingesetzt` / `angeschnauft`: `true` oder `false` (`angeschnauft` darf leer sein)
- Fahrzeuge, die es noch nicht gibt, werden automatisch angelegt.
- Bei einem Fehler wird nichts importiert, und du siehst, in welcher Zeile das
  Problem liegt. Auch schon vorhandene Einsatznummern brechen den Import ab.

## Lizenz

MIT-Lizenz, siehe [LICENSE](LICENSE).
