# systemd Unit Files — VPS Deployment

These unit files run on the Hostinger VPS (`$VPS_HOST`) at `/etc/systemd/system/`.
Kept here in the repo for code-review, diff tracking, and re-deployment.

The commands below expect the host in an environment variable:

```bash
export VPS_HOST=<your-vps-host>
```

## Installed Units

| Unit | Purpose | Schedule |
|------|---------|----------|
| `macro2-ibkr-stream.service` | IBKR real-time streaming daemon (17 instruments → `data_cache/ibkr_realtime.json`) | KeepAlive (always on) |
| `macro-cache-repair.timer` + service | Self-healing FRED cache error repair (runs `scripts/repair_cache_errors.py`) | Every 5 min |
| `macro-data-qa.timer` + service | Data QA agent (11 standard checks + Minimax LLM triage + Telegram CRITICAL alerts) | 00:00 and 12:00 UTC (08:00 / 20:00 GMT+8) |

The `macro-fast-extract.timer`, `macro-extract.timer`, `macro-hl-extract.timer`,
`macro-polymarket-extract.timer`, `macro-onchain-extract.timer`, `ibkr-dashboard.service`,
and `ib-health-monitor.timer` pre-date this work and are not maintained here.

## Drop-ins

| Drop-in | Overrides | Purpose |
|---------|-----------|---------|
| `macro-extract.service.d/openbb-venv.conf` | `macro-extract.service` | Runs the daily full extraction under `/root/macro_2/venv-openbb` (OpenBB + cboe/ecb providers) and caps it at `MemoryMax=2G` |

**Why a separate venv:** `openbb-core` hard-pins `uvicorn<0.41`. Installing OpenBB into the
shared `/root/macro_2/venv` would downgrade the uvicorn serving `macro-react.service`
(0.42.0 → 0.40.0). Everything except `macro-extract.service` keeps the shared venv and
never imports OpenBB — the import in `openbb_extractors.py` is lazy for exactly this reason.

```bash
# Deploy the drop-in
ssh root@"$VPS_HOST" "mkdir -p /etc/systemd/system/macro-extract.service.d"
scp deploy/systemd/macro-extract.service.d/openbb-venv.conf \
    root@"$VPS_HOST":/etc/systemd/system/macro-extract.service.d/
ssh root@"$VPS_HOST" "systemctl daemon-reload"

# Build the venv it points at
ssh root@"$VPS_HOST" "cd /root/macro_2 && python3 -m venv venv-openbb && \
  ./venv-openbb/bin/pip install -r requirements.txt -r requirements-openbb.txt && \
  ./venv-openbb/bin/pip install 'yfinance==1.2.0'"   # match the shared venv
```

## Deploy

```bash
# From repo root
for unit in deploy/systemd/*.{service,timer}; do
  scp "$unit" root@"$VPS_HOST":/etc/systemd/system/
done
ssh root@"$VPS_HOST" "systemctl daemon-reload"

# Enable timers and start services
ssh root@"$VPS_HOST" "systemctl enable --now macro2-ibkr-stream.service"
ssh root@"$VPS_HOST" "systemctl enable --now macro-cache-repair.timer"
ssh root@"$VPS_HOST" "systemctl enable --now macro-data-qa.timer"
```

## Verify

```bash
ssh root@"$VPS_HOST" "systemctl list-timers --no-pager | grep macro"
ssh root@"$VPS_HOST" "journalctl -u macro-data-qa --no-pager -n 30"
```

## Trigger a QA run manually

```bash
ssh root@"$VPS_HOST" "systemctl start macro-data-qa.service"
# or for a single check:
ssh root@"$VPS_HOST" "cd /root/macro_2 && /root/macro_2/venv/bin/python -m agent.openai_agents.qa_agent --check C3"
```
