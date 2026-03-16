# Deploy Macro Dashboard to AWS Lightsail

Deploy the Streamlit macroeconomic dashboard to an AWS Lightsail VPS. Agent subsystem excluded. Replaces macOS launchd with Linux cron.

---

## Step 1: Create Lightsail Instance

1. Go to AWS Lightsail console → Create instance
2. Pick **Linux/Unix → Ubuntu 22.04 LTS**
3. Plan: **$5/mo (1 GB RAM, 1 vCPU, 40 GB SSD)** — sufficient for this app
   - Upgrade to $10/mo (2 GB RAM) if you notice OOM during data fetches
4. Name it (e.g. `macro-dashboard`)
5. After creation, go to **Networking** tab:
   - Add rule: **Custom TCP → Port 443** (HTTPS)
   - Add rule: **Custom TCP → Port 80** (HTTP, for redirect)
   - Port 22 (SSH) is already open by default
6. Note the **public static IP** (attach one under Networking → Static IP if not already)

---

## Step 2: SSH In & System Setup

```bash
ssh -i ~/.ssh/LightsailDefaultKey-*.pem ubuntu@<YOUR_IP>

# System packages
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv python3-dev \
  libxml2-dev libxslt1-dev build-essential git curl nginx certbot python3-certbot-nginx
```

---

## Step 3: Clone & Install App

```bash
cd /home/ubuntu
git clone https://github.com/cdavocazh/macro_2.git
cd macro_2

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create data directories
mkdir -p data_cache historical_data data_export logs
```

---

## Step 4: Copy Existing Data From Local Machine

Run these **from your Mac** (not the VPS):

```bash
# Replace <YOUR_IP> with your Lightsail static IP
# Replace <KEY_PATH> with your Lightsail SSH key path

# Copy cache (for instant startup)
scp -i <KEY_PATH> -r ~/Github/macro_2/data_cache/ ubuntu@<YOUR_IP>:/home/ubuntu/macro_2/data_cache/

# Copy historical data (append-only archive)
scp -i <KEY_PATH> -r ~/Github/macro_2/historical_data/ ubuntu@<YOUR_IP>:/home/ubuntu/macro_2/historical_data/

# Copy latest exports
scp -i <KEY_PATH> -r ~/Github/macro_2/data_export/ ubuntu@<YOUR_IP>:/home/ubuntu/macro_2/data_export/
```

Total transfer: ~7 MB. The dashboard will load instantly from cache after this.

---

## Step 5: Access — Two Proposals

### Option A: Public URL with Nginx + SSL (Recommended if you have a domain)

**Requires:** A domain name pointed at your Lightsail IP (A record).

1. **Create Streamlit config** to disable CORS/XSRF for reverse proxy:

```bash
mkdir -p /home/ubuntu/macro_2/.streamlit
cat > /home/ubuntu/macro_2/.streamlit/config.toml << 'EOF'
[server]
headless = true
address = "127.0.0.1"
port = 8501
enableCORS = false
enableXsrfProtection = false

[browser]
gatherUsageStats = false
EOF
```

2. **Create nginx config:**

```bash
sudo tee /etc/nginx/sites-available/macro-dashboard << 'EOF'
server {
    listen 80;
    server_name YOUR_DOMAIN.com;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }

    # Streamlit static assets & websocket
    location /_stcore/stream {
        proxy_pass http://127.0.0.1:8501/_stcore/stream;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/macro-dashboard /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

3. **Add SSL with Let's Encrypt:**

```bash
sudo certbot --nginx -d YOUR_DOMAIN.com
# Follow prompts, select redirect HTTP→HTTPS
```

Auto-renews via systemd timer (certbot installs this automatically).

### Option B: Password-Protected (No Domain Needed)

Access via `http://<YOUR_IP>` with HTTP Basic Auth. No domain or SSL certificate required.

1. **Same Streamlit config** as Option A (create `.streamlit/config.toml`).

2. **Create password file:**

```bash
sudo apt install -y apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd kris
# Enter a password when prompted
```

3. **Create nginx config with auth:**

```bash
sudo tee /etc/nginx/sites-available/macro-dashboard << 'EOF'
server {
    listen 80;
    server_name _;

    auth_basic "Macro Dashboard";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }

    location /_stcore/stream {
        proxy_pass http://127.0.0.1:8501/_stcore/stream;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/macro-dashboard /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Access at `http://<YOUR_LIGHTSAIL_IP>` — browser prompts for username/password.

> **You can combine both:** Domain + SSL + Basic Auth for authenticated HTTPS access.

---

## Step 6: Systemd Service (Keep Streamlit Running)

```bash
sudo tee /etc/systemd/system/macro-dashboard.service << 'EOF'
[Unit]
Description=Macro Indicators Streamlit Dashboard
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/macro_2
Environment="PATH=/home/ubuntu/macro_2/venv/bin:/usr/bin:/bin"
Environment="FRED_API_KEY=REDACTED_FRED_API_KEY"
ExecStart=/home/ubuntu/macro_2/venv/bin/streamlit run app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable macro-dashboard
sudo systemctl start macro-dashboard

# Verify
sudo systemctl status macro-dashboard
```

---

## Step 7: Cron Scheduling (Replaces macOS launchd)

The existing `scheduled_extract.py` has a freshness guard (skips if cache < 1h old) and a `--cron` quiet mode. Set up cron to match the current schedule:

```bash
crontab -e
```

Add these lines (times in UTC — current schedule is GMT+8):

```cron
# Macro dashboard data extraction (Mon-Sat)
# Original GMT+8 schedule converted to UTC:
# 1:00 AM GMT+8 = 17:00 UTC (prev day)
# 8:30 AM GMT+8 = 00:30 UTC
# 1:00 PM GMT+8 = 05:00 UTC
# 5:00 PM GMT+8 = 09:00 UTC
# 10:00 PM GMT+8 = 14:00 UTC

0 17 * * 0-4 cd /home/ubuntu/macro_2 && /home/ubuntu/macro_2/venv/bin/python scheduled_extract.py --cron >> logs/cron_extract.log 2>&1
30 0 * * 1-5 cd /home/ubuntu/macro_2 && /home/ubuntu/macro_2/venv/bin/python scheduled_extract.py --cron >> logs/cron_extract.log 2>&1
0 5 * * 1-5 cd /home/ubuntu/macro_2 && /home/ubuntu/macro_2/venv/bin/python scheduled_extract.py --cron >> logs/cron_extract.log 2>&1
0 9 * * 1-5 cd /home/ubuntu/macro_2 && /home/ubuntu/macro_2/venv/bin/python scheduled_extract.py --cron >> logs/cron_extract.log 2>&1
0 14 * * 1-6 cd /home/ubuntu/macro_2 && /home/ubuntu/macro_2/venv/bin/python scheduled_extract.py --cron >> logs/cron_extract.log 2>&1
```

**Set up log rotation** so logs don't grow unbounded:

```bash
sudo tee /etc/logrotate.d/macro-dashboard << 'EOF'
/home/ubuntu/macro_2/logs/*.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
}
EOF
```

**Key difference from launchd:** cron does NOT catch up missed runs after sleep/reboot. If the VPS reboots mid-schedule, that run is skipped. The freshness guard and 5x daily schedule make this a non-issue — the next run picks up.

---

## Step 8: Verify Everything Works

```bash
# Check Streamlit is running
sudo systemctl status macro-dashboard

# Check nginx is proxying
curl -I http://localhost

# Test a manual extraction
cd /home/ubuntu/macro_2
source venv/bin/activate
python scheduled_extract.py --force

# Check cron is registered
crontab -l

# Tail logs
tail -f logs/cron_extract.log
```

Visit `https://YOUR_DOMAIN.com` (Option A) or `http://YOUR_IP` (Option B) in a browser.

---

## Updating the App

To deploy code updates:

```bash
ssh ubuntu@<YOUR_IP>
cd /home/ubuntu/macro_2
git pull
sudo systemctl restart macro-dashboard
```

---

## Summary

| Component | macOS (current) | Lightsail (new) |
|-----------|----------------|-----------------|
| OS | macOS | Ubuntu 22.04 |
| Python | mambaforge | venv |
| Scheduler | launchd plist | cron |
| Process manager | manual | systemd |
| Reverse proxy | none | nginx |
| SSL | none | Let's Encrypt (certbot) |
| Auth | none | Basic Auth (nginx) and/or domain-only access |

**Estimated Lightsail cost:** $5/mo (1 GB) or $10/mo (2 GB for comfort).
