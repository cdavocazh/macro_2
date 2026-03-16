# Deploying Macro Dashboard to AWS Lightsail

Step-by-step guide to deploy the Plotly Dash macro indicators dashboard on an AWS Lightsail Ubuntu VPS.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│  AWS Lightsail VPS (Ubuntu 22.04/24.04)                         │
│                                                                  │
│  ┌─────────┐      ┌──────────┐      ┌──────────────────────┐   │
│  │  Nginx   │─────▶│ Gunicorn │─────▶│  Dash app (app.py)   │   │
│  │  :80/:443│      │  :8050   │      │  + data_loader.py    │   │
│  └─────────┘      └──────────┘      └──────────┬───────────┘   │
│       ▲                                          │               │
│       │                              ┌───────────▼────────────┐ │
│   Internet                           │  data_cache/            │ │
│                                      │  all_indicators.json    │ │
│                                      └───────────▲────────────┘ │
│                                                  │               │
│  ┌──────────────────────────┐   ┌────────────────┴────────┐    │
│  │ macro-fast-extract.timer │   │ macro-extract.timer      │    │
│  │ (every 5 min — yfinance) │   │ (5x/day — FRED+SEC+all) │    │
│  └──────────────────────────┘   └─────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

**How it works:**
1. **Nginx** handles HTTP/HTTPS, static assets, rate limiting, and reverse proxies to Gunicorn
2. **Gunicorn** runs the Dash app with 2 workers (WSGI server)
3. **Dash app** reads from the shared JSON cache file — no live API calls on page load
4. **systemd timers** run `fast_extract.py` (every 5 min) and `scheduled_extract.py` (5x/day) to keep the cache fresh
5. The Dash app auto-detects cache file changes via mtime and reloads data

---

## Prerequisites

| Requirement | Details |
|---|---|
| **Lightsail plan** | $5/mo (1 GB RAM, 1 vCPU) works, $10/mo (2 GB) recommended |
| **OS** | Ubuntu 22.04 LTS or 24.04 LTS |
| **Firewall** | Ports 22 (SSH), 80 (HTTP), 443 (HTTPS) open |
| **Domain** (optional) | For HTTPS via Let's Encrypt |
| **FRED API key** (optional) | Free from https://fred.stlouisfed.org/docs/api/api_key.html |

---

## Step 1: Create a Lightsail Instance

1. Go to [AWS Lightsail Console](https://lightsail.aws.amazon.com/)
2. Click **Create instance**
3. Choose:
   - **Region**: Closest to you
   - **Platform**: Linux/Unix
   - **Blueprint**: OS Only → **Ubuntu 22.04 LTS** (or 24.04)
   - **Plan**: **$10/mo** (2 GB RAM, 1 vCPU, 60 GB SSD) — recommended
     - $5/mo (1 GB) will work but may be tight during data extraction
4. Name it (e.g., `macro-dashboard`) and click **Create instance**
5. Wait ~60 seconds for it to boot

### Open the Firewall

1. Click your instance → **Networking** tab
2. Under **IPv4 Firewall**, click **+ Add rule**:
   - **HTTP** (port 80)
   - **HTTPS** (port 443) — if you plan to use a domain
3. Save

### SSH Into Your Instance

```bash
# Option A: Lightsail browser-based SSH (click the terminal icon)

# Option B: Download SSH key from Account > SSH keys, then:
ssh -i ~/LightsailDefaultKey.pem ubuntu@<YOUR_PUBLIC_IP>
```

---

## Step 2: Clone the Repository

```bash
# Clone to /opt/macro_2
sudo git clone https://github.com/cdavocazh/macro_2.git /opt/macro_2
sudo chown -R ubuntu:ubuntu /opt/macro_2
cd /opt/macro_2
```

If the repo is private, use a GitHub personal access token:
```bash
sudo git clone https://<TOKEN>@github.com/cdavocazh/macro_2.git /opt/macro_2
```

---

## Step 3: Run the Automated Deploy Script

The deploy script handles everything — packages, venv, services, Nginx:

```bash
sudo bash dash_dashboard/deploy/deploy.sh
```

This takes about 2-3 minutes. It will:
1. Install Python 3, Nginx, certbot
2. Create a virtual environment at `/opt/macro_2/venv`
3. Install all pip dependencies
4. Create data directories
5. Copy `.env.example` to `.env`
6. Run initial data extraction (~40 seconds)
7. Install and start 3 systemd services
8. Configure and reload Nginx

**When complete, you'll see:**
```
════════════════════════════════════════════════════════
  ✅ Deployment complete!
════════════════════════════════════════════════════════

  Dashboard URL:   http://3.12.34.56
```

---

## Step 4: Configure Environment Variables

```bash
sudo nano /opt/macro_2/.env
```

Set your FRED API key (optional but recommended for full data):
```ini
FRED_API_KEY=your_actual_key_here
```

Then restart the extraction service to pick up the key:
```bash
sudo systemctl restart macro-dash
sudo systemctl start macro-extract
```

---

## Step 5: Verify Everything is Running

### Check the Web Server
```bash
sudo systemctl status macro-dash
# Should show: Active: active (running)

curl -s http://localhost:8050 | head -20
# Should return HTML
```

### Check Extraction Timers
```bash
systemctl list-timers macro-*
# Should show:
#   macro-fast-extract.timer    — every 5 min
#   macro-extract.timer         — 5x/day
```

### Check Logs
```bash
# Web server logs
sudo journalctl -u macro-dash -f

# Extraction logs
sudo journalctl -u macro-extract --since "1 hour ago"
sudo journalctl -u macro-fast-extract --since "10 min ago"

# Nginx access logs
sudo tail -f /var/log/nginx/macro-dash.access.log
```

### Open in Browser
Navigate to `http://<YOUR_LIGHTSAIL_PUBLIC_IP>` — you should see the dashboard.

---

## Step 6: (Optional) Set Up HTTPS with a Custom Domain

### Point Your Domain
1. In your DNS provider, create an **A record**:
   - `macro.yourdomain.com` → `<YOUR_LIGHTSAIL_PUBLIC_IP>`
2. (Optional) Allocate a **Static IP** in Lightsail to prevent IP changes on restart

### Update Nginx Config
```bash
sudo nano /etc/nginx/sites-available/macro-dash
```
Change `server_name _;` to:
```nginx
server_name macro.yourdomain.com;
```
```bash
sudo nginx -t && sudo systemctl reload nginx
```

### Install SSL Certificate
```bash
sudo certbot --nginx -d macro.yourdomain.com
```
Certbot will:
- Obtain a free Let's Encrypt certificate
- Auto-configure Nginx for HTTPS
- Set up auto-renewal (via systemd timer)

Verify auto-renewal:
```bash
sudo certbot renew --dry-run
```

---

## Manual Deployment (Without the Script)

If you prefer to do each step manually or need to customize:

### Install System Packages
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip python3-dev \
    nginx certbot python3-certbot-nginx build-essential curl git
```

### Create Virtual Environment
```bash
cd /opt/macro_2
python3 -m venv venv
source venv/bin/activate
pip install -r dash_dashboard/deploy/requirements-server.txt
```

### Create Directories
```bash
mkdir -p data_cache historical_data data_export logs
sudo mkdir -p /var/log/macro-dash
sudo chown ubuntu:ubuntu /var/log/macro-dash
```

### Set Up Environment
```bash
cp dash_dashboard/deploy/.env.example .env
nano .env   # add your FRED_API_KEY
chmod 600 .env
```

### Seed Initial Data
```bash
source venv/bin/activate
python scheduled_extract.py --force
```

### Test Gunicorn Manually
```bash
cd dash_dashboard
../venv/bin/gunicorn wsgi:server -b 0.0.0.0:8050 -w 2 --timeout 120
# Visit http://<IP>:8050 — Ctrl+C to stop
```

### Install systemd Services
```bash
sudo cp dash_dashboard/deploy/macro-dash.service /etc/systemd/system/
sudo cp dash_dashboard/deploy/macro-extract.service /etc/systemd/system/
sudo cp dash_dashboard/deploy/macro-extract.timer /etc/systemd/system/
sudo cp dash_dashboard/deploy/macro-fast-extract.service /etc/systemd/system/
sudo cp dash_dashboard/deploy/macro-fast-extract.timer /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now macro-dash
sudo systemctl enable --now macro-extract.timer
sudo systemctl enable --now macro-fast-extract.timer
```

### Configure Nginx
```bash
sudo cp dash_dashboard/deploy/nginx-macro-dash.conf /etc/nginx/sites-available/macro-dash
sudo ln -sf /etc/nginx/sites-available/macro-dash /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

---

## Updating the Dashboard

When you push changes to the repo:

```bash
cd /opt/macro_2
git pull origin main
source venv/bin/activate
pip install -r dash_dashboard/deploy/requirements-server.txt   # if deps changed
sudo systemctl restart macro-dash
```

For zero-downtime restarts:
```bash
sudo systemctl reload macro-dash   # Gunicorn graceful reload
```

---

## Operations Reference

### Service Management

| Command | Description |
|---|---|
| `sudo systemctl status macro-dash` | Check web server status |
| `sudo systemctl restart macro-dash` | Restart web server |
| `sudo systemctl stop macro-dash` | Stop web server |
| `sudo journalctl -u macro-dash -f` | Stream web server logs |
| `sudo journalctl -u macro-extract -f` | Stream extraction logs |
| `systemctl list-timers macro-*` | Check all timer schedules |
| `sudo systemctl start macro-extract` | Trigger manual extraction now |

### Log Locations

| Log | Path |
|---|---|
| Gunicorn access | `/var/log/macro-dash/access.log` |
| Gunicorn errors | `/var/log/macro-dash/error.log` |
| Nginx access | `/var/log/nginx/macro-dash.access.log` |
| Nginx errors | `/var/log/nginx/macro-dash.error.log` |
| All services | `sudo journalctl -u macro-*` |

### Data Directories

| Directory | Purpose |
|---|---|
| `/opt/macro_2/data_cache/` | JSON cache (read by dashboard) |
| `/opt/macro_2/historical_data/` | Append-only CSV archive |
| `/opt/macro_2/data_export/` | Latest snapshot CSVs |

### Troubleshooting

**Dashboard shows "No data"**
```bash
# Check if cache exists
ls -la /opt/macro_2/data_cache/all_indicators.json

# Run extraction manually
cd /opt/macro_2 && source venv/bin/activate
python scheduled_extract.py --force

# Then restart dash
sudo systemctl restart macro-dash
```

**502 Bad Gateway**
```bash
# Gunicorn isn't running
sudo systemctl status macro-dash
sudo journalctl -u macro-dash --since "5 min ago"

# Common fix: restart
sudo systemctl restart macro-dash
```

**Port 8050 already in use**
```bash
sudo lsof -i :8050
sudo kill <PID>
sudo systemctl restart macro-dash
```

**Out of memory on $5 plan**
```bash
# Add 1 GB swap
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Reduce Gunicorn workers to 1
sudo nano /etc/systemd/system/macro-dash.service
# Change --workers 2 to --workers 1
sudo systemctl daemon-reload && sudo systemctl restart macro-dash
```

**Extraction timers not firing**
```bash
systemctl list-timers macro-*
# If timers show n/a for next trigger:
sudo systemctl enable --now macro-extract.timer
sudo systemctl enable --now macro-fast-extract.timer
```

---

## File Inventory

```
dash_dashboard/deploy/
├── DEPLOY.md                    ← This guide
├── deploy.sh                    ← Automated deployment script
├── requirements-server.txt      ← Combined pip dependencies
├── .env.example                 ← Environment variable template
├── macro-dash.service           ← Gunicorn systemd service
├── macro-extract.service        ← Full extraction oneshot
├── macro-extract.timer          ← Full extraction schedule (5x/day)
├── macro-fast-extract.service   ← Fast extraction oneshot
├── macro-fast-extract.timer     ← Fast extraction schedule (every 5 min)
└── nginx-macro-dash.conf        ← Nginx reverse proxy config

dash_dashboard/
├── wsgi.py                      ← Gunicorn WSGI entrypoint
├── app.py                       ← Dash application
├── data_loader.py               ← Cache reader
└── assets/style.css             ← Dashboard CSS
```

---

## Cost Estimate

| Resource | Monthly Cost |
|---|---|
| Lightsail $10 plan (2 GB RAM, 1 vCPU, 60 GB SSD) | $10 |
| Static IP (free while attached) | $0 |
| Data transfer (first 3 TB free) | $0 |
| Domain (optional, via Route 53 or external) | ~$1/mo |
| SSL certificate (Let's Encrypt) | $0 |
| **Total** | **$10-11/mo** |

The $5/mo plan (1 GB RAM) works if you add swap and use 1 Gunicorn worker. The extraction scripts are the main memory consumers (~400 MB peak during full extraction).
