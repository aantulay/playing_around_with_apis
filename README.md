# Global Country & Demographic Explorer

A full-stack Flask web application for exploring global country demographics, regional statistics, flags, and saved favorites, backed by the REST Countries v5 API and deployed in a load-balanced multi-node Ubuntu environment using Gunicorn and Nginx.

---

## Table of Contents
1. [Features](#features)
2. [Architecture Overview](#architecture-overview)
3. [Tech Stack & Libraries](#tech-stack--libraries)
4. [API Documentation & Attribution](#api-documentation--attribution)
5. [Local Installation & Setup](#local-installation--setup)
6. [Multi-Node Deployment Guide](#multi-node-deployment-guide)
7. [Security & Credentials Note](#security--credentials-note)
8. [Challenges & Solutions](#challenges--solutions)

---

## Features
- **Authenticated Access:** Session-based login protecting the explorer dashboard and user favorites.
- **Interactive Country Search & Filtering:** Search countries by name, filter by geographic region, sort by population or area, and toggle **Favorites only** to view saved countries across paginated results.
- **Pagination & Detailed Country Views:** Clean paginated country browsing with flag rendering and demographic details (capital, region, subregion, population, area, languages, and currencies).
- **Persistent Favorites:** Save and remove favorite countries per session with server-side filtering support.
- **In-Memory API Caching:** Configurable TTL caching (`CACHE_TTL_SECONDS`) to minimize upstream API latency and rate-limit pressure.
- **Health & Load-Balancer Observability:** `/health` endpoint and `X-Served-By` response headers identifying which backend node handled each request.

---

## Architecture Overview

```text
                        ┌─────────────────────────┐
                        │   Client / Browser      │
                        └────────────┬────────────┘
                                     │ HTTP (Port 80)
                                     ▼
                        ┌─────────────────────────┐
                        │  7242-lb-01 (Nginx LB)  │
                        │     35.176.43.231       │
                        └──────┬───────────┬──────┘
                               │           │
              ┌────────────────┘           └────────────────┐
              ▼                                             ▼
┌───────────────────────────┐                 ┌───────────────────────────┐
│  7242-web-01 (52.56.93.14)│                 │ 7242-web-02 (13.40.173.255)│
│  Nginx (:80) -> Gunicorn  │                 │  Nginx (:80) -> Gunicorn  │
│  Flask App (:5000)        │                 │  Flask App (:5000)        │
└─────────────┬─────────────┘                 └─────────────┬─────────────┘
              │                                             │
              └──────────────────────┬──────────────────────┘
                                     │ HTTPS (Bearer Auth)
                                     ▼
                        ┌─────────────────────────┐
                        │  REST Countries v5 API  │
                        └─────────────────────────┘
```

---

## Tech Stack & Libraries
- **Backend:** [Python 3.12](https://www.python.org/), [Flask](https://flask.palletsprojects.com/)
- **HTTP Client:** [Requests](https://docs.python-requests.org/)
- **WSGI Production Server:** [Gunicorn](https://gunicorn.org/)
- **Reverse Proxy & Load Balancer:** [Nginx](https://nginx.org/)
- **Frontend:** HTML5, CSS3, Vanilla JavaScript (Fetch API)
- **Containerization (Optional Local Testing):** Docker (`Dockerfile` & `docker-compose.yml`)

---

## API Documentation & Attribution
- **Primary External API:** [REST Countries API (v5)](https://restcountries.com/) — Used to retrieve country metadata, demographic figures, regional classifications, and flag assets.
- **Attribution:** Country datasets and flag resources are provided by the REST Countries project and its contributors. All framework and library credits belong to the Pallets Projects (Flask), Gunicorn maintainers, Python Software Foundation, and Nginx, Inc.

---

## Local Installation & Setup

### Prerequisites
- Python 3.10+ and `pip`
- Git
- A valid `COUNTRIES_API_KEY` for the REST Countries v5 endpoint

### 1. Clone the Repository
```bash
git clone https://github.com/aantulay/playing_around_with_apis.git
cd playing_around_with_apis
```

### 2. Create & Activate a Virtual Environment
**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a local `.env` file (or export variables in your shell). **Never commit `.env` or API keys to Git.**

```env
SERVER_ID=local-dev
SECRET_KEY=replace-with-a-strong-random-secret
DEMO_USER_PASSWORD=replace-with-demo-password
COUNTRIES_API_URL=https://api.restcountries.com/countries/v5
COUNTRIES_API_KEY=your_api_key_here
CACHE_TTL_SECONDS=300
PORT=5000
```

### 5. Run the Application Locally
```bash
python app.py
```
Open `http://127.0.0.1:5000` in your browser and sign in using the configured demo credentials.

---

## Multi-Node Deployment Guide

### 1. Backend Web Nodes (`7242-web-01` and `7242-web-02`)
Execute the following steps on **`7242-web-01` (`52.56.93.14`)** and repeat on **`7242-web-02` (`13.40.173.255`)** (updating `SERVER_ID` accordingly):

```bash
# Install system dependencies
sudo apt update && sudo apt install -y python3-venv python3-pip nginx

# Clone application repository
sudo mkdir -p /opt/playing_around_with_apis
sudo chown -R "$USER":"$USER" /opt/playing_around_with_apis
git clone https://github.com/aantulay/playing_around_with_apis.git /opt/playing_around_with_apis
cd /opt/playing_around_with_apis

# Install Python dependencies inside a virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# Configure restricted environment file (set SERVER_ID=7242-web-02 on web-02)
sudo tee /etc/country-explorer.env > /dev/null <<'EOF'
SERVER_ID=7242-web-01
SECRET_KEY=replace-with-a-strong-random-secret
DEMO_USER_PASSWORD=replace-with-demo-password
COUNTRIES_API_URL=https://api.restcountries.com/countries/v5
COUNTRIES_API_KEY=your_api_key_here
CACHE_TTL_SECONDS=300
PORT=5000
EOF
sudo chmod 600 /etc/country-explorer.env

# Create systemd unit for Gunicorn
sudo tee /etc/systemd/system/api-explorer.service > /dev/null <<'EOF'
[Unit]
Description=API Explorer Gunicorn Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/playing_around_with_apis
EnvironmentFile=/etc/country-explorer.env
ExecStart=/opt/playing_around_with_apis/.venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo chown -R www-data:www-data /opt/playing_around_with_apis

# Configure Nginx reverse proxy on port 80
sudo tee /etc/nginx/sites-available/api-explorer > /dev/null <<'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        include /etc/nginx/proxy_params;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/api-explorer /etc/nginx/sites-enabled/api-explorer
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

# Start and verify Gunicorn service
sudo systemctl daemon-reload
sudo systemctl enable --now api-explorer
curl -i http://127.0.0.1/health
```

### 2. Load Balancer Node (`7242-lb-01` at `35.176.43.231`)
```bash
sudo apt update && sudo apt install -y nginx

sudo tee /etc/nginx/sites-available/api-explorer-lb > /dev/null <<'EOF'
upstream web_backends {
    server 52.56.93.14:80 max_fails=3 fail_timeout=30s;
    server 13.40.173.255:80 max_fails=3 fail_timeout=30s;
}

server {
    listen 80 default_server;
    server_name _;

    location / {
        proxy_pass http://web_backends;
        include /etc/nginx/proxy_params;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/api-explorer-lb /etc/nginx/sites-enabled/api-explorer-lb
sudo nginx -t && sudo systemctl restart nginx
```

### 3. Verify Load Balancing
```bash
for i in {1..6}; do
    curl -s -i http://35.176.43.231/health | grep -E "HTTP/|X-Served-By|status"
done
```
Confirm alternating `X-Served-By: 7242-web-01` and `X-Served-By: 7242-web-02` headers across requests.

---

## Security & Credentials Note
- `.gitignore` excludes `.env`, virtual environments (`.venv/`), and `__pycache__/` so no secrets or API keys are stored in version control.
- Production secrets are stored in `/etc/country-explorer.env` with `chmod 600` permissions.
- Demo login credentials and API keys required for evaluation are provided separately in the submission comments.

---

## Challenges & Solutions
1. **Upstream Pagination & Response Structure:** The REST Countries v5 endpoint required careful handling of paginated response envelopes and Bearer token authentication. I normalized the API response parsing on the Flask backend and added TTL caching so pagination, sorting, and filtering remain fast and consistent.
2. **Favorites Persistence Across Paginated Views:** Initially, filtering by "Favorites only" on the client side only inspected the currently loaded page. Moving the favorites filter logic to the backend ensured saved countries are accurately aggregated across the entire dataset before pagination is applied.
3. **Flag Asset Rendering Consistency:** Different country records exposed flag URLs and emoji representations inconsistently. Standardizing fallback flag rendering in the backend payload and frontend UI prevented broken images across all regions.
4. **Multi-Node Service Isolation & Port Routing:** Separating application processes (Gunicorn bound to `127.0.0.1:5000`) from public HTTP ingress (Nginx listening on port `80` on both backend nodes and `7242-lb-01`) eliminated port conflicts and allowed clean health checks and round-robin load balancing.

## Demo Video
https://drive.google.com/file/d/1Zpo3fxL7dHf6M7Gm0RgeQNeH0VJXU7iL/view?usp=sharing