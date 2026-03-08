# CostHarbor

[![CI](https://github.com/itsh-neumeier/CostHarbor/actions/workflows/ci.yml/badge.svg)](https://github.com/itsh-neumeier/CostHarbor/actions/workflows/ci.yml)

Configurable utility billing and cost allocation web application for properties with solar, battery, and smart metering systems.

## Features

- **Multi-property management** with units and tenants
- **Data import** from Home Assistant, Shelly Pro 3EM, and Victron VRM
- **Dynamic electricity pricing** via aWATTar market data
- **Automated billing** with configurable rules for electricity, water, and fixed costs
- **German-language PDF invoices**
- **Audit trail** and versioned calculation runs

## Quick Start

### Prerequisites

- Docker and Docker Compose

### Setup

```bash
# Clone the repository
git clone https://github.com/itsh-neumeier/CostHarbor.git
cd CostHarbor

# Configure environment
cp .env.example .env
# Edit .env with your settings (SECRET_KEY, ENCRYPTION_KEY, admin credentials)

# Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Start the application
docker-compose up -d

# Access at http://localhost:8000
```

### Portainer / Docker Deployment

The pre-built Docker image is available on GitHub Container Registry:

```
ghcr.io/itsh-neumeier/costharbor:latest
```

**Deploy as Portainer Stack:**

1. In Portainer, go to **Stacks** > **Add stack**
2. Upload or paste the contents of `docker-compose.portainer.yml`
3. Set the following environment variables:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Random string, min 32 characters |
| `ENCRYPTION_KEY` | Fernet key (see generation command above) |
| `ADMIN_PASSWORD` | Password for the initial admin account |
| `DB_PASSWORD` | PostgreSQL database password |

4. Click **Deploy the stack**
5. Access the application at `http://<your-host>:8000`

### Development Setup

```bash
# Start database only
docker-compose up -d db

# Install dependencies
pip install -e ".[dev]"

# Run migrations
alembic upgrade head

# Start dev server
uvicorn app.main:app --reload
```

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://costharbor:costharbor@db:5432/costharbor` |
| `SECRET_KEY` | Session signing key (min 32 chars) | *required* |
| `ENCRYPTION_KEY` | Fernet key for encrypting sensitive config | *required* |
| `ADMIN_USERNAME` | Initial admin username | `admin` |
| `ADMIN_PASSWORD` | Initial admin password | *required* |
| `ADMIN_EMAIL` | Initial admin email | `admin@example.com` |
| `APP_PORT` | Application port | `8000` |
| `APP_ENV` | Environment (production/development) | `production` |
| `MAX_UPLOAD_SIZE_MB` | Maximum file upload size | `50` |

## Data Sources

### Home Assistant

1. Go to **Data Sources** > **Add Connection** > **Home Assistant**
2. Enter your Home Assistant base URL (e.g., `http://192.168.1.100:8123`)
3. Enter a Long-Lived Access Token (generate in HA Profile settings)
4. Map entities to measurement types (grid consumption, PV production, water, etc.)

### Shelly Pro 3EM

1. Download CSV from the device: `http://DEVICE_IP/emdata/0/data.csv?ts=START&end_ts=END`
2. Go to **Imports** > **Upload Shelly CSV**
3. The system parses phase data and aggregates to hourly values

### Victron VRM

**IMAP method (recommended):**
1. Configure IMAP settings under **Data Sources** > **VRM Mailbox**
2. Request a data export in the VRM portal
3. CostHarbor fetches the email, extracts the download link, and imports the CSV

**Manual upload:**
1. Download the CSV from the VRM export email
2. Upload via **Imports** > **Upload VRM CSV**

### Dynamic Prices (aWATTar)

1. Add an aWATTar connection under **Data Sources**
2. Select country (Germany/Austria)
3. Import prices for a specific month

## Billing Workflow

1. Ensure measurement data is imported for the billing month
2. Ensure hourly prices are available (if using dynamic pricing)
3. Go to **Billing** > **New Calculation**
4. Select site, unit, tenant, and month
5. Review the calculation preview
6. Finalize and generate PDF

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic
- **Frontend**: Jinja2 + Bootstrap 5 (server-side rendered)
- **Database**: PostgreSQL 16
- **PDF**: WeasyPrint
- **Infrastructure**: Docker, docker-compose

## License

MIT License - see [LICENSE](LICENSE)
