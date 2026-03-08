"""Connection test functions for data source adapters.

Tests connectivity and authentication without importing data.
Returns a result dict with success status, message, and optional details.
"""

import logging

import httpx

logger = logging.getLogger(__name__)


def test_homeassistant(config: dict) -> dict:
    """Test Home Assistant connection by calling the /api/ endpoint."""
    base_url = (config.get("base_url") or "").rstrip("/")
    token = config.get("token") or ""

    if not base_url:
        return {"success": False, "message": "base_url fehlt in der Konfiguration."}
    if not token:
        return {"success": False, "message": "token fehlt in der Konfiguration."}

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{base_url}/api/",
                headers={"Authorization": f"Bearer {token}"},
            )

        if resp.status_code == 200:
            data = resp.json()
            ha_message = data.get("message", "")
            return {
                "success": True,
                "message": f'Verbindung erfolgreich! Home Assistant antwortet: "{ha_message}"',
            }
        elif resp.status_code == 401:
            return {"success": False, "message": "Authentifizierung fehlgeschlagen. Token ungueltig oder abgelaufen."}
        else:
            return {"success": False, "message": f"Unerwarteter Status: {resp.status_code}"}

    except httpx.ConnectError:
        return {"success": False, "message": f"Verbindung zu {base_url} fehlgeschlagen. Host nicht erreichbar."}
    except httpx.TimeoutException:
        return {"success": False, "message": f"Timeout bei Verbindung zu {base_url}. Host reagiert nicht."}
    except Exception as e:
        return {"success": False, "message": f"Verbindungsfehler: {e}"}


def test_awattar(config: dict) -> dict:
    """Test aWATTar API by fetching a small time range of prices."""
    from datetime import UTC, datetime, timedelta

    country = (config.get("country") or "de").lower()

    urls = {
        "de": "https://api.awattar.de/v1/marketdata",
        "at": "https://api.awattar.at/v1/marketdata",
    }
    base_url = urls.get(country)
    if not base_url:
        return {"success": False, "message": f"Unbekanntes Land: '{country}'. Verwende 'de' oder 'at'."}

    try:
        now = datetime.now(UTC)
        start_ms = int((now - timedelta(hours=2)).timestamp() * 1000)
        end_ms = int(now.timestamp() * 1000)

        with httpx.Client(timeout=10) as client:
            resp = client.get(base_url, params={"start": start_ms, "end": end_ms})
            resp.raise_for_status()

        data = resp.json()
        entries = data.get("data", [])

        if entries:
            latest = entries[-1]
            price_kwh = latest.get("marketprice", 0) / 1000
            return {
                "success": True,
                "message": (
                    f"aWATTar API erreichbar ({country.upper()})! "
                    f"{len(entries)} Preisdatenpunkte abgerufen. "
                    f"Aktueller Marktpreis: {price_kwh:.4f} EUR/kWh"
                ),
            }
        else:
            return {
                "success": True,
                "message": f"aWATTar API erreichbar ({country.upper()}), aber keine Preisdaten fuer den Testzeitraum.",
            }

    except httpx.HTTPStatusError as e:
        return {"success": False, "message": f"aWATTar API Fehler: HTTP {e.response.status_code}"}
    except httpx.ConnectError:
        return {"success": False, "message": "aWATTar API nicht erreichbar."}
    except Exception as e:
        return {"success": False, "message": f"Fehler: {e}"}


def test_vrm_imap(config: dict) -> dict:
    """Test VRM IMAP connection by logging into the mailbox."""
    import imaplib
    import ssl

    host = config.get("host") or ""
    port = int(config.get("port") or 993)
    username = config.get("username") or ""
    password = config.get("password") or ""
    use_tls = config.get("tls", True)

    if not host or not username or not password:
        return {"success": False, "message": "host, username und password sind erforderlich."}

    try:
        if use_tls:
            ctx = ssl.create_default_context()
            mail = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)
        else:
            mail = imaplib.IMAP4(host, port)

        mail.login(username, password)

        folder = config.get("folder") or "INBOX"
        status, data = mail.select(folder, readonly=True)
        msg_count = int(data[0]) if status == "OK" else 0
        mail.logout()

        return {
            "success": True,
            "message": f"IMAP-Verbindung erfolgreich! Ordner '{folder}' enthaelt {msg_count} Nachrichten.",
        }

    except imaplib.IMAP4.error as e:
        return {"success": False, "message": f"IMAP-Fehler: {e}"}
    except ConnectionRefusedError:
        return {"success": False, "message": f"Verbindung zu {host}:{port} abgelehnt."}
    except TimeoutError:
        return {"success": False, "message": f"Timeout bei Verbindung zu {host}:{port}."}
    except Exception as e:
        return {"success": False, "message": f"Verbindungsfehler: {e}"}


def test_shelly(config: dict) -> dict:
    """Test Shelly Pro 3EM connection by fetching device status."""
    device_ip = config.get("device_ip") or ""

    if not device_ip:
        return {"success": False, "message": "device_ip fehlt in der Konfiguration."}

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"http://{device_ip}/rpc/Shelly.GetStatus")

        if resp.status_code == 200:
            data = resp.json()
            # Try to extract useful info
            em_data = data.get("em:0", {})
            total_power = em_data.get("total_act_power", "?")
            return {
                "success": True,
                "message": f"Shelly Pro 3EM erreichbar! Aktuelle Leistung: {total_power} W",
            }
        else:
            return {"success": False, "message": f"Shelly antwortet mit Status {resp.status_code}"}

    except httpx.ConnectError:
        return {"success": False, "message": f"Geraet unter {device_ip} nicht erreichbar."}
    except httpx.TimeoutException:
        return {"success": False, "message": f"Timeout bei Verbindung zu {device_ip}."}
    except Exception as e:
        return {"success": False, "message": f"Verbindungsfehler: {e}"}


def test_vrm_api(config: dict) -> dict:
    """Test VRM API connection by fetching installation info."""
    access_token = config.get("access_token") or ""
    installation_id = config.get("installation_id") or ""

    if not access_token:
        return {"success": False, "message": "access_token fehlt in der Konfiguration."}
    if not installation_id:
        return {"success": False, "message": "installation_id fehlt in der Konfiguration."}

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"https://vrmapi.victronenergy.com/v2/installations/{installation_id}/system-overview",
                headers={"X-Authorization": f"Token {access_token}"},
            )

        if resp.status_code == 200:
            data = resp.json()
            records = data.get("records", {})
            name = records.get("name", str(installation_id))
            return {
                "success": True,
                "message": f"VRM API Verbindung erfolgreich! Installation: {name}",
            }
        elif resp.status_code == 401:
            return {"success": False, "message": "VRM API: Token ungueltig oder abgelaufen."}
        elif resp.status_code == 404:
            return {"success": False, "message": f"VRM API: Installation {installation_id} nicht gefunden."}
        else:
            return {"success": False, "message": f"VRM API Fehler: HTTP {resp.status_code}"}

    except httpx.ConnectError:
        return {"success": False, "message": "VRM API nicht erreichbar."}
    except httpx.TimeoutException:
        return {"success": False, "message": "Timeout bei Verbindung zur VRM API."}
    except Exception as e:
        return {"success": False, "message": f"Verbindungsfehler: {e}"}


def test_connection(source_type: str, config: dict) -> dict:
    """Dispatch connection test based on source type."""
    testers = {
        "homeassistant": test_homeassistant,
        "awattar": test_awattar,
        "vrm_imap": test_vrm_imap,
        "vrm_api": test_vrm_api,
        "shelly": test_shelly,
    }

    tester = testers.get(source_type)
    if not tester:
        return {"success": True, "message": f"Kein Verbindungstest fuer Typ '{source_type}' verfuegbar."}

    return tester(config)
