# M-Pesa OpenAPI Tester — Django App

A local developer tool for testing the Vodacom M-Pesa OpenAPI (`openapiportal.m-pesa.com`) — covering session auth, B2B/B2C/C2B payments, reversals, and status queries, with a full transaction log.

## Supported Markets
- **LSO** — Lesotho (LSL)
- **TZN** — Tanzania (TZS)
- **GHA** — Ghana (GHS)
- **DRC** — DR Congo (CDF)

## Setup

```bash
# 0. Create local environment config
cp .env.example .env

# 1. Install dependencies
pip install django requests pycryptodome

# 2. Run migrations
python manage.py migrate

# 3. Start server
python manage.py runserver

# 4. Open browser
# http://127.0.0.1:8000
```

## Environment Variables

The Django project reads its core settings from environment variables. The defaults are safe for local development, but you should override them before deployment.

| Variable | Purpose | Default |
|----------|---------|---------|
| `DJANGO_SECRET_KEY` | Django secret key | bundled dev key |
| `DJANGO_DEBUG` | Turns Django debug mode on or off | `True` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hosts | `*` |
| `DJANGO_DB_NAME` | SQLite database path | `db.sqlite3` |

For a local setup, keep the values in `.env.example` and adjust them as needed.

## Usage

### Step 1 — Get Session
1. Open the app → **Get Session** tab
2. Paste your **API Key** from `openapiportal.m-pesa.com` → Application Details
3. Paste your **Public Key** from Account Profile
4. Select **Market** (Lesotho = LSO) and **Environment** (sandbox for testing)
5. Click **Get Session Key** — your session is stored for all subsequent calls

### Step 2 — Test Payment APIs
Navigate to any payment type. In sandbox mode use:
- **Service Provider Code / Party Codes**: `000000`
- **Customer MSISDN**: `000000000001`
- Any **Reference**: `T12345` (alphanumeric)

### API Response Codes
| Code | Meaning |
|------|---------|
| `INS-0` | Success |
| `INS-1` | Internal error |
| `INS-6` | Transaction failed |
| `INS-2006` | Unauthorized / bad session |
| `INS-2051` | Invalid MSISDN |
| `INS-2057` | Invalid amount |

## Project Structure
```
mpesa_tester/
├── api_tester/
│   ├── mpesa_client.py   # M-Pesa API client (encryption + requests)
│   ├── models.py         # MpesaSession + TransactionLog models
│   ├── views.py          # Django views for each endpoint
│   └── migrations/
├── templates/
│   └── api_tester/
│       └── index.html    # Full UI
└── mpesa_tester/
    ├── settings.py
    └── urls.py
```

## Notes
- Session lifetime defaults to **1 hour** (configurable on the portal)
- The app stores the last active session in SQLite — one session at a time
- All API calls are logged in the right-hand panel with HTTP status and M-Pesa response codes
- Never deploy this with real production keys exposed — this is a dev tool
