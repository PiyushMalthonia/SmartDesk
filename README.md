# SmartDesk AI

**SmartDesk AI** is an AI-Powered Enterprise Helpdesk Automation platform for ITSM, Incident Management, Smart Ticket Routing, Workflow Automation, analytics, and SLA tracking.

## Features

- Modern Bootstrap + Font Awesome sidebar dashboard
- User login, registration, ticket creation, and status tracking
- Admin enterprise dashboard inspired by ServiceNow, Jira, and Zendesk
- AI Automation for ticket category, severity, priority, and confidence score
- Smart Ticket Routing to IT Team, Network Team, or Security Team
- SLA countdown timers and SLA breach cards
- File uploads for screenshots, PDFs, TXT files, and logs
- Ticket timeline and Activity Feed
- Real-time search suggestions and autocomplete
- AI Chat Assistant with predefined IT support responses
- Animated Chart.js analytics page
- Dark mode
- Email notifications through SMTP environment variables
- Docker support

## Architecture

```text
Browser
  |
  | Bootstrap + Font Awesome + Chart.js
  v
Flask Routes
  |
  |-- ai_predictor.py: local AI-lite prediction and chat assistant
  |-- notifications.py: SMTP email notifications
  |-- database.py: SQLite schema and migrations
  v
SQLite Database
```

## Run Locally

```powershell
python run_lan.py
```

Then open:

```text
http://127.0.0.1:5000
```

## Use From Another Device

Connect the other device to the same Wi-Fi network, then open the Network URL printed by:

```powershell
python run_lan.py
```

Current LAN URL:

```text
http://192.168.1.9:5000
```

If another device cannot connect, allow Python or port `5000` through Windows Defender Firewall for Private networks.

## Default Admin

```text
Email: admin@smartdesk.local
Password: admin123
```

For deployment, set your own admin credentials before the first app start:

```text
ADMIN_NAME=SmartDesk Admin
ADMIN_EMAIL=your-admin@example.com
ADMIN_PASSWORD=your-secure-password
SECRET_KEY=your-long-random-secret
```

The first admin account is created only when the database has no admin user yet.

## Deploy

Use this start command on Render/Railway/Heroku-style platforms:

```text
gunicorn --bind 0.0.0.0:$PORT wsgi:app
```

Required environment variables:

```text
SECRET_KEY=your-long-random-secret
ADMIN_EMAIL=your-admin@example.com
ADMIN_PASSWORD=your-secure-password
```

## Email Notifications

Set these environment variables before running:

```powershell
$env:SMARTDESK_SMTP_HOST="smtp.gmail.com"
$env:SMARTDESK_SMTP_PORT="587"
$env:SMARTDESK_SMTP_USER="your-email@example.com"
$env:SMARTDESK_SMTP_PASSWORD="your-app-password"
$env:SMARTDESK_EMAIL_FROM="your-email@example.com"
python run_lan.py
```

If SMTP is not configured, SmartDesk AI logs notification events without failing.

## Docker

```powershell
docker build -t smartdesk-ai .
docker run -p 5000:5000 smartdesk-ai
```

## Future Scope

- OpenAI API-powered resolution recommendations
- Agent role and workload balancing
- SLA policies by department
- Exportable reports
- Cloud deployment with HTTPS
