# Changelog

Alle wesentlichen Aenderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
und das Projekt folgt [Semantic Versioning](https://semver.org/lang/de/spec/v2.0.0.html).

## [0.1.0] - 2026-03-07

### Hinzugefuegt

- Erster MVP-Release
- Admin-Authentifizierung mit bcrypt-Passwort-Hashing
- Verwaltung von Standorten, Einheiten und Mietern
- Wiederkehrende Kostenpositionen mit flaechenbasierter Umlage
- Wasser-Aufteilungsregeln (konfigurierbar, Standard 50/50)
- Home-Assistant-API-Integration mit Entity-Mapping
- Shelly Pro 3EM CSV-Import
- VRM-IMAP-E-Mail-Abruf mit Download-Link-Extraktion
- Manueller VRM-CSV-Upload als Fallback
- aWATTar dynamischer Stundenpreis-Import
- Monatliche Berechnungsengine
- Abrechnungsvorschau in der Web-UI
- Deutschsprachige PDF-Abrechnungserzeugung (WeasyPrint)
- Audit-Logging fuer alle administrativen Aenderungen
- Versionierte Konfiguration und Berechnungslaeufe
- Docker- und docker-compose-Setup
- GitHub-Actions-CI/CD-Pipelines
- Dependabot-Sicherheitsscanning
