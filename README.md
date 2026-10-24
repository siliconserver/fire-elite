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
```

Für einen Umzug auf einen anderen Server kopierst du den ganzen Ordner
(inklusive `data/` und `.env`) und startest dort mit `docker compose up -d`.

## Automatisierte Installation

Terraform- und Ansible-Dateien für AlmaLinux und Debian liegen in
[deploy/](deploy/README.md). Ansible richtet neue und vorhandene VPS ein.
Terraform-Beispiele für das Anlegen neuer Server gibt es für Hetzner Cloud,
IONOS Cloud und Contabo.

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
