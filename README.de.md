# CostHarbor

Konfigurierbare Webanwendung zur Nebenkosten- und Verbrauchsabrechnung fuer Liegenschaften mit Solar-, Batterie- und Smart-Metering-Systemen.

## Funktionen

- **Mehrobjekt-Verwaltung** mit Einheiten und Mietern
- **Datenimport** aus Home Assistant, Shelly Pro 3EM und Victron VRM
- **Dynamische Strompreise** ueber aWATTar-Marktdaten
- **Automatisierte Abrechnung** mit konfigurierbaren Regeln fuer Strom, Wasser und Fixkosten
- **Deutschsprachige PDF-Abrechnungen**
- **Audit-Trail** und versionierte Berechnungslaeufe

## Schnellstart

### Voraussetzungen

- Docker und Docker Compose

### Einrichtung

```bash
# Repository klonen
git clone https://github.com/your-org/costharbor.git
cd costharbor

# Umgebung konfigurieren
cp .env.example .env
# .env bearbeiten (SECRET_KEY, ENCRYPTION_KEY, Admin-Zugangsdaten)

# Verschluesselungsschluessel erzeugen
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Anwendung starten
docker-compose up -d

# Zugriff unter http://localhost:8000
```

## Datenquellen

### Home Assistant

1. **Datenquellen** > **Verbindung hinzufuegen** > **Home Assistant**
2. Base-URL eingeben (z.B. `http://192.168.1.100:8123`)
3. Long-Lived Access Token eingeben (erzeugen in HA-Profilseite)
4. Entities auf Messtypen mappen (Netzbezug, PV-Erzeugung, Wasser, etc.)

### Shelly Pro 3EM

1. CSV vom Geraet herunterladen: `http://GERAETE_IP/emdata/0/data.csv?ts=START&end_ts=ENDE`
2. **Importe** > **Shelly CSV hochladen**
3. Das System parst die Phasendaten und aggregiert auf Stundenwerte

### Victron VRM

**IMAP-Methode (empfohlen):**
1. IMAP-Einstellungen unter **Datenquellen** > **VRM Mailbox** konfigurieren
2. Datenexport im VRM-Portal anfordern
3. CostHarbor ruft die E-Mail ab, extrahiert den Download-Link und importiert die CSV

**Manueller Upload:**
1. CSV aus der VRM-Export-E-Mail herunterladen
2. Hochladen ueber **Importe** > **VRM CSV hochladen**

### Dynamische Preise (aWATTar)

1. aWATTar-Verbindung unter **Datenquellen** hinzufuegen
2. Land waehlen (Deutschland/Oesterreich)
3. Preise fuer einen Monat importieren

## Abrechnungsablauf

1. Messdaten fuer den Abrechnungsmonat importieren
2. Stundenpreise sicherstellen (bei dynamischer Preisgestaltung)
3. **Abrechnung** > **Neue Berechnung**
4. Standort, Einheit, Mieter und Monat waehlen
5. Berechnungsvorschau pruefen
6. Finalisieren und PDF erzeugen

## Lizenz

MIT-Lizenz - siehe [LICENSE](LICENSE)
