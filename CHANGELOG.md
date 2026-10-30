# Changelog

Alle relevanten Änderungen an Elite. Neueste Version oben.
Diese Datei wird auch auf der Seite „Über Elite“ angezeigt; die oberste Version ist die App-Version.

## 1.10 (2026-10-30)
- Wochenreport jetzt auch per Telegram und Signal, jede Person schaltet die Kanäle im Profil unter „Benachrichtigungen“ ein
- Handynummer für Benutzer: im eigenen Profil oder durch Admins in der Benutzerverwaltung
- Telegram wird über einen eigenen Bot verbunden, Signal über den optionalen signal-cli-Container (Einrichtung im README)
- Kanäle ohne Zugangsdaten in der .env bleiben ausgeschaltet
- Profil: „Wochenreport testweise an mich schicken“

## 1.9 (2026-10-23)
- „Über Elite“ verlinkt das Projekt auf GitHub: Quellcode, Issues und Changelog (Issue #19)

## 1.8 (2026-10-23)
- Fix: „Hell“ im Profil blieb dunkel, weil der Browser noch das alte Stylesheet aus dem Offline-Cache nutzte (Issue #18)
- Der Offline-Cache wird jetzt bei jeder neuen Version automatisch erneuert

## 1.7 (2026-10-23)
- Dark- und Light-Mode: im Profil unter „Darstellung“ wählbar (Wie Betriebssystem, Hell, Dunkel) (Issue #18)
- Standard ist „Wie Betriebssystem“: die App folgt automatisch der Hell/Dunkel-Einstellung des Geräts
- Diagramme im Dashboard passen ihre Schrift- und Gitterfarben an das Farbschema an

## 1.6 (2026-10-23)
- Fix: Einsatznummer nachträglich ändern führte zu „Internal Server Error“ (Issue #4)
- Beim Verschieben einer Einsatznummer rücken die Einsätze dazwischen in beide Richtungen nach, ohne Lücken oder doppelte Nummern
- Beim Löschen eines Einsatzes rücken die nachfolgenden Einsatznummern eins auf

## 1.5 (2026-10-23)
- README für neue Nutzer neu geschrieben: worum es geht, Funktionen und Start auf dem eigenen Server

## 1.4 (2026-10-23)
- „Über Elite“ zeigt jetzt den Changelog statt nur der Versionsnummer (Issue #9)
- Versionsnummer wird aus dieser Datei gelesen

## 1.3 (2026-10-23)
- Einsatz-Detailseite und Einsatzliste ohne seitliches Scrollen auf dem Handy (Issue #3)

## 1.2 (2026-10-23)
- Fix: „Eingesetzt = nein“ setzt das Fahrzeug auf „In Bereitstellung“ (Issue #2)

## 1.1 (2026-10-23)
- Fix: Zeiten wurden mit -1h/-2h Versatz angezeigt (Issue #5)

## 1.0 (2026-08-25)
- Initialer Release
