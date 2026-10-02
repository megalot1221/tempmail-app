# TempMail App

Self-hosted temporary email application built with Python, FastAPI, PostgreSQL, Docker, and a web frontend.

## Features

- Guest temporary email addresses
- Guest mailboxes expire after 20 minutes
- Registered user accounts
- Permanent user mailboxes
- Random and designated email addresses
- Email inbox and message viewing
- Inbox search
- Mark messages as read
- Copy email addresses
- Mailbox management
- Admin dashboard
- User and guest activity monitoring
- Email generation and received-email analytics
- Country tracking
- Admin domain management
- Domain verification
- Domain enable/disable lifecycle
- Admin mailbox creation

## Requirements

- Ubuntu 24.04 or newer
- Docker
- Docker Compose
- Git
- Domain name and DNS access
- SMTP port 25
- Nginx
- SSL/TLS certificate

This application works with the separate TempMail backend:

https://github.com/megalot1221/tempmail-server

## Installation

### Clone

```bash
cd /opt
git clone https://github.com/megalot1221/tempmail-app.git tempmail-app
cd /opt/tempmail-app
```

### Configure environment

```bash
cp .env.example .env
nano .env
```

Example:

```env
DATABASE_URL=postgresql+psycopg://tempmail_app:YOUR_DATABASE_PASSWORD@tempmail_db:5432/tempmail_app
TEMPMAIL_API=http://tempmail_api:8000
JWT_SECRET=CHANGE_THIS_TO_A_LONG_RANDOM_SECRET
IP2LOCATION_API_KEY=YOUR_IP2LOCATION_API_KEY
```

Never commit `.env` or real secrets to GitHub.

### Start

```bash
docker compose up -d --build
```

Check:

```bash
docker compose ps
```

Logs:

```bash
docker compose logs -f app
```

## Testing

```bash
curl http://127.0.0.1:8080/
```

Expected:

```json
{"name":"TempMail App","status":"online"}
```

Health check:

```bash
curl http://127.0.0.1:8080/health
```

Expected:

```json
{"status":"ok"}
```

## Database Migrations

```bash
docker compose run --rm app alembic upgrade head
```

Or:

```bash
docker exec -it tempmail_app alembic upgrade head
```

## Docker Network

The application expects the Docker network used by the TempMail backend.

Check:

```bash
docker network ls
```

Normally:

```text
tempmail-server_tempmail_network
```

## DNS

Example mail DNS:

```text
A
mail.example.com -> YOUR_SERVER_IP
```

MX:

```text
MX
example.com -> mail.example.com
Priority: 10
```

## SMTP

The TempMail backend receives email through SMTP on port 25.

Test:

```bash
nc -vz 127.0.0.1 25
```

## Nginx

Example:

```nginx
server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://127.0.0.1:8080;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Test:

```bash
nginx -t
```

Reload:

```bash
systemctl reload nginx
```

Use HTTPS with a trusted TLS certificate in production.

## Project Structure

```text
tempmail-app/
├── app/
│   ├── config.py
│   ├── database.py
│   ├── main.py
│   └── models/
├── alembic/
│   └── versions/
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── alembic.ini
├── install.py
├── .env.example
├── .gitignore
└── README.md
```

## Useful Commands

Start:

```bash
docker compose up -d
```

Rebuild:

```bash
docker compose up -d --build
```

Stop:

```bash
docker compose down
```

Restart:

```bash
docker compose restart app
```

Logs:

```bash
docker compose logs -f app
```

Status:

```bash
docker compose ps
```

## Updating

```bash
cd /opt/tempmail-app
git pull
docker compose up -d --build
```

## Moving to a New VPS

```bash
cd /opt
git clone https://github.com/megalot1221/tempmail-app.git tempmail-app
cd /opt/tempmail-app
cp .env.example .env
nano .env
docker compose up -d --build
```

Restore the required database and TempMail backend configuration before production use.

## Security

Never commit:

- `.env`
- Database passwords
- JWT secrets
- API keys
- Private TLS keys
- Private certificates
- Local backups
- Other sensitive credentials

Use strong production secrets and secure backups.

## License

Add your preferred license here.

## Disclaimer

This project is intended for legitimate self-hosted temporary email and email testing use. Ensure your deployment complies with applicable laws, regulations, and third-party terms of service.
