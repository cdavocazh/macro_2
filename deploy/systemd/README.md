# systemd Unit Files — VPS Deployment

These unit files run on the Hostinger VPS (`187.77.136.160`) at `/etc/systemd/system/`.
Kept here in the repo for code-review, diff tracking, and re-deployment.

## Installed Units

| Unit | Purpose | Schedule |
|------|---------|----------|
| `macro2-ibkr-stream.service` | IBKR real-time streaming daemon (17 instruments → `data_cache/ibkr_realtime.json`) | KeepAlive (always on) |
| `macro-cache-repair.timer` + service | Self-healing FRED cache error repair (runs `scripts/repair_cache_errors.py`) | Every 5 min |
| `macro-data-qa.timer` + service | Data QA agent (11 standard checks + Minimax LLM triage + Telegram CRITICAL alerts) | 00:00 and 12:00 UTC (08:00 / 20:00 GMT+8) |

The `macro-fast-extract.timer`, `macro-extract.timer`, `macro-hl-extract.timer`,
`macro-polymarket-extract.timer`, `macro-onchain-extract.timer`, `ibkr-dashboard.service`,
and `ib-health-monitor.timer` pre-date this work and are not maintained here.

## Deploy

```bash
# From repo root
for unit in deploy/systemd/*.{service,timer}; do
  scp "$unit" root@187.77.136.160:/etc/systemd/system/
done
ssh root@187.77.136.160 "systemctl daemon-reload"

# Enable timers and start services
ssh root@187.77.136.160 "systemctl enable --now macro2-ibkr-stream.service"
ssh root@187.77.136.160 "systemctl enable --now macro-cache-repair.timer"
ssh root@187.77.136.160 "systemctl enable --now macro-data-qa.timer"
```

## Verify

```bash
ssh root@187.77.136.160 "systemctl list-timers --no-pager | grep macro"
ssh root@187.77.136.160 "journalctl -u macro-data-qa --no-pager -n 30"
```

## Trigger a QA run manually

```bash
ssh root@187.77.136.160 "systemctl start macro-data-qa.service"
# or for a single check:
ssh root@187.77.136.160 "cd /root/macro_2 && /root/macro_2/venv/bin/python -m agent.openai_agents.qa_agent --check C3"
```
