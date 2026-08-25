# Fire Elite (Feuerwehr Einsatz- Logbuch für Individuelle Tätigkeits- und Erfassung)

Web-Tool zum Erfassen und Auswerten von Feuerwehreinsätzen. Läuft komplett per
`docker compose` (Postgres + FastAPI-App), alle Daten liegen dauerhaft im
Projektordner unter `./data`.

## Setup

1. `.env` aus der Vorlage erstellen und Werte anpassen:
   ```bash
   cp .env.example .env
   ```
   Mindestens `POSTGRES_PASSWORD`, `SECRET_KEY`, `ADMIN_PASSWORD` und (falls
   der Wochenreport genutzt werden soll) die `SMTP_*`-Variablen mit echten
   Zugangsdaten füllen. `ADMIN_EMAIL` ist nur die Erstbefüllung für den
   Wochenreport-Empfänger – danach in der Weboberfläche unter
   **Einstellungen → E-Mail-Texte** änderbar.

2. Starten:
   ```bash
   docker compose up -d --build
   ```

3. Aufrufen unter `http://<server>:8086`. Login mit `ADMIN_USERNAME` /
   `ADMIN_PASSWORD` aus der `.env` (wird beim ersten Start automatisch angelegt).

## Persistenz

Alle Daten liegen im Projektordner, nicht in benannten Docker-Volumes:

```
fire-elite/
  data/
    postgres/   # komplette Postgres-Datenbank
    backups/    # tägliche + manuelle Backups (.sql.gz)
```

Ein Umzug auf einen anderen Server = Ordner `fire-elite/` (inkl. `data/`)
kopieren und `docker compose up -d --build` erneut ausführen.

## Funktionen

### Progressive Web App
Auf dem Smartphone über den Browser "Zum Home-Bildschirm hinzufügen"
installierbar (eigenes App-Icon, startet im Vollbild ohne Browser-Leiste).
Basiert auf einem Web-App-Manifest, Apple-Touch-Icons und einem schlanken
Service Worker, der nur statische Assets (CSS, Chart.js, Icons) fürs
App-Shell-Caching vorhält – alle Einsatzdaten kommen immer live vom Server,
nie aus dem Cache.

### Grundfunktionen
- **Login mit Rollen**: `admin` (voller Zugriff) und `viewer` (nur lesen).
- **Zwei-Faktor-Authentifizierung (2FA)**: optional, pro Benutzer über das
  Profil-Menü mit einer Authenticator-App (Google Authenticator, Authy, …)
  einrichtbar – QR-Code + manueller Schlüssel, Bestätigung per Code. Dort
  auch das eigene Passwort änderbar. Verliert jemand sein Gerät, kann ein
  Admin dessen 2FA in der Benutzerverwaltung fremd deaktivieren.

### Einsätze (`/einsaetze`)
- Anlegen, bearbeiten, löschen (nur Admin).
- Felder: Nummer, Start/Ende (Zeitstempel inkl. Zeitzone, wichtig z. B. an
  Tagen der Uhrumstellung), Ort, Art (TH/Brand/Dienstleistung/Gefahrstoffe),
  Funktion (TM/AGT/MA/FEZ/GF/EL), Eingesetzt, Alarmierung (mit
  Autovervollständigung aus bisherigen Einträgen), Bemerkungen, Einsatzmittel
  (Fahrzeug, konfigurierbar unter `/fahrzeuge`), Angeschnauft und
  AGT-Gerät (PA/Filter/CSA).
- Ist "Eingesetzt" nicht gesetzt, wird die Funktion automatisch auf
  "In Bereitstellung" gesetzt (Feld ausgegraut). "Angeschnauft" ist nur bei
  Funktion AGT verfügbar, das AGT-Gerät nur wenn "Angeschnauft" aktiv ist –
  jeweils serverseitig zusätzlich zur UI erzwungen.
- **Nachträglich einfügen**: Wird beim Anlegen oder Bearbeiten eine bereits
  vergebene Einsatznummer eingetragen, rücken diese Zeile und alle
  nachfolgenden Nummern automatisch eins auf.

### CSV-Import (`/einsaetze/import`)
Importiert Einsätze aus einer hochgeladenen CSV-Datei. Erwartetes Schema
(Kopfzeile exakt so):

```
nummer,start,ende,ort,art,funktion,eingesetzt,alarmierung,bemerkungen,einsatzmittel,angeschnauft,agt
```

- `start`/`ende`: Zeitstempel inkl. Zeitzonen-Offset, z. B. `2021-05-22 13:05:00+02`.
- `eingesetzt`/`angeschnauft`: `true`/`false` (`angeschnauft` darf leer sein).
- `einsatzmittel`, das noch nicht existiert, wird automatisch angelegt.
- Der Import läuft in einer Transaktion: jeder Fehler (mit Zeilennummer und
  Grund) bricht den gesamten Import ab, es gibt keinen Teil-Import. Bereits
  in der Datenbank vorhandene Einsatznummern führen ebenfalls zum Abbruch.

### Fahrzeuge / Einsatzmittel (`/fahrzeuge`)
Eigene Einsatzmittel anlegen und löschen (nur Admin). Ein Einsatzmittel, das
noch in Einsätzen verwendet wird, kann nicht gelöscht werden.

### Dashboard (`/`)
Ersetzt eine separate Grafana-Instanz. Auswählbarer Zeitraum (Default: alle
Daten) – Heute, Gestern, letzte 7/14/30/90 Tage, letzte 6/12 Monate, dieses
Jahr/dieser Monat/diese Woche bis jetzt, oder ein benutzerdefinierter
Von/Bis-Zeitraum. Zeigt für den gewählten Zeitraum:

- Zeit gesamt und durchschnittliche Einsatzzeit (Stunden), Anzahl Einsätze
- Tortendiagramme (Anzahl + Prozent): Eingesetzt, PA-Typen, PA-Einsätze
  (Angeschnauft), Einsatzarten, Funktionen, Einsatzmittel, Einsatzort,
  Einsatzstichwort
- Balkendiagramm: Einsätze pro Monat

Diagramme laufen mit lokal eingebundenem Chart.js (kein CDN zur Laufzeit
nötig).

### E-Mail & Backups (unter `/settings`, nur Admin)
- **Wöchentlicher Report per Mail**: Anzahl Einsätze und Gesamtstunden der
  letzten 7 Tage plus Liste der einzelnen Einsätze, an eine konfigurierbare
  Adresse. Zeitpunkt (Wochentag + Uhrzeit) sowie Betreff/Einleitungstext frei
  einstellbar, manueller Testversand jederzeit möglich.
- **Backups**: täglicher `pg_dump` (komprimiert) zur eingestellten Uhrzeit,
  konfigurierbare Aufbewahrungsanzahl. In der Weboberfläche: Liste aller
  Backups mit Download, manuellem "Jetzt sichern", Wiederherstellen (mit
  Sicherheitsabfrage – überschreibt alle aktuellen Daten!) und Löschen. Die
  `.sql.gz`-Dateien liegen zusätzlich direkt unter `./data/backups`.
- **Benutzerverwaltung**: neue Admin-/Viewer-Benutzer anlegen, löschen, Rolle
  ändern (der letzte Admin sowie der eigene Account können nicht gelöscht
  oder herabgestuft werden), fremde 2FA im Bedarfsfall deaktivieren.

## Projektstruktur

```
docker-compose.yml
Dockerfile
requirements.txt
.env.example
data/                # persistente Daten (DB + Backups), per .gitignore ausgeschlossen
app/
  main.py            # Routen / Webserver
  models.py          # Datenbankmodelle (User, Einsatz, Einsatzmittel, Settings)
  database.py        # DB-Verbindung
  auth.py            # Passwort-Hashing
  crud.py            # Business-Logik: Nummern-Reindex, Dashboard-Statistiken, Settings
  csv_import.py       # CSV-Validierung + Import
  emailer.py           # SMTP-Versand
  scheduler.py          # Konfigurierbare Cron-Jobs (Wochenreport, Backup)
  backup.py              # pg_dump/psql Backup & Restore
  templates/               # HTML-Seiten
  static/                   # CSS, PWA-Assets, vendored Chart.js
```
