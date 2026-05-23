# Plan — macOS Menu Bar BTC Price App

**Goal:** A native macOS app that shows the live BTC price in the menu bar (top pane of the screen), updating as fast as the Hyperliquid data harness allows — i.e. ~1 update per second via Hyperliquid's WebSocket `allMids` channel.

**Status:** Draft plan, not yet started.

---

## 1. Data source choice

The repo already has three Hyperliquid pathways. Picking the right one matters for cadence and operational independence.

| Source | Cadence | Pros | Cons | Pick? |
|---|---|---|---|---|
| `data_cache/all_indicators.json` (via `hl_extract.py` launchd job) | ~60s (45s freshness guard) | Zero new infra; just read a file | 60× slower than the user asked for; tied to the macro2 cron | ❌ |
| `/ws/hl` on `react_dashboard/backend/main.py` (proxied [hl_ws_service.py:60](react_dashboard/backend/hl_ws_service.py:60)) | ~1s | Reuses existing relay, contexts already enriched | Requires the React backend to be running; coupling the menu bar app to a 4-frontend dev server is wrong | ❌ |
| **Direct WebSocket to `wss://api.hyperliquid.xyz/ws` — subscribe `allMids`** | **~1s** | Same cadence as the existing WS relay; fully standalone; rate limits ample (10 WS/IP, 2k msg/min — we use 1/1) | We re-implement reconnect + ping logic, but it's small (~80 lines, model from [hl_ws_service.py:355](react_dashboard/backend/hl_ws_service.py:355)) | ✅ |

**Decision:** direct WebSocket. The menu bar app is its own process and should not depend on `react_dashboard` being up. Reconnect + heartbeat logic is straightforward (mirror the relay in [hl_ws_service.py](react_dashboard/backend/hl_ws_service.py)).

---

## 2. Tech stack

Two viable options; pick before starting.

### Option A — Swift + SwiftUI (recommended)
- `NSStatusItem` for the menu bar text, `URLSessionWebSocketTask` for the WS, launches on login via `SMAppService`.
- **Pros:** ~50 MB RAM idle, single notarised `.app` bundle, no Python runtime to ship, no `py2app` headaches, native dark/light mode, drag-into-Applications install.
- **Cons:** Swift code is new to this repo (everything else is Python). One small `.swift` file though — not a real maintenance burden.

### Option B — Python + `rumps` + `websockets`
- `rumps.App` for the menu bar item, `websockets` library for the WS, packaged with `py2app`.
- **Pros:** Reuses the harness language; can copy reconnect logic verbatim from [hl_ws_service.py](react_dashboard/backend/hl_ws_service.py).
- **Cons:** `py2app` bundles are 150–300 MB and brittle across macOS versions; cold start is slow; you'd be shipping a mambaforge-style runtime for a tiny app.

**Recommendation: Option A (Swift).** Lean, native, no runtime drama. Option B is the fallback if Swift toolchain is unavailable.

The rest of this plan assumes Swift. If Option B is chosen, the milestones below still apply — just swap `URLSessionWebSocketTask` for `websockets.connect()` and `NSStatusItem` for `rumps.App`.

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  BTCMenuBar.app (single process)                            │
│                                                             │
│   ┌───────────────┐    ┌──────────────────┐                 │
│   │ HLWSClient    │───▶│ PriceStore       │                 │
│   │ (URLSession   │    │ (@Published      │                 │
│   │  WebSocket)   │    │  Decimal price)  │                 │
│   └───────────────┘    └─────────┬────────┘                 │
│           ▲                       │                          │
│           │ reconnect + ping      ▼                          │
│           │                ┌──────────────┐                  │
│   wss://api.hyperliquid… ─┘│ StatusItem   │                  │
│   subscribe: {type:allMids}│ "BTC $69,420"│                  │
│                            └──────────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

Single source of truth: a `PriceStore` ObservableObject. The WS client mutates `price`; the menu bar title binds to it.

**Reconnect/heartbeat** (port from [hl_ws_service.py:355-389](react_dashboard/backend/hl_ws_service.py:355)):
- `ping_interval = 50s` (HL closes idle at 60s)
- Exponential backoff: 1s → 2s → 4s → … → cap at 60s
- Reset backoff to 1s on successful connect

**Message handling:** `allMids` payload shape is `{channel: "allMids", data: {mids: {"BTC": "69420.5", ...}}}`. Extract `mids["BTC"]`, parse as `Decimal`, push to store. Ignore other channels (`subscriptionResponse`, `pong`, `error` — log only).

---

## 4. Menu bar UX

**Title format:** `BTC $69,420` (no decimal places — saves width). Switch to `$69,420.50` if the user prefers; configurable later.

**Color cue (optional, v2):** green / red tint vs last tick — small, non-distracting. Defer to v2; v1 is plain text.

**Dropdown menu** (click the title to open):
- Latest price + last-update timestamp (relative: "2s ago")
- 24h change % (from `prevDayPx` via `metaAndAssetCtxs` REST call — separate 30s polling task; the WS only carries mids)
- Connection status: ● Live / ● Reconnecting / ● Disconnected
- "Open Hyperliquid" → `https://app.hyperliquid.xyz/trade/BTC`
- "Quit"

**Stale data handling:** if no message received for > 10s, dim the title and show "● Reconnecting" in the menu. This matches the existing `hl_ws_service.py` failure modes.

---

## 5. Implementation milestones

Each milestone is independently testable. Stop after any one if priorities shift.

1. **Skeleton menu bar app** — Xcode project (or hand-written `project.pbxproj` / SwiftPM `Package.swift`), `NSStatusItem` with static text "BTC —". Confirm it shows up in the menu bar, quits cleanly.
2. **WebSocket connect + subscribe** — Open `wss://api.hyperliquid.xyz/ws`, send `{method:"subscribe",subscription:{type:"allMids"}}`, log every `allMids` payload to console.
3. **Wire price to menu bar title** — Parse `mids["BTC"]`, update `NSStatusItem.button.title` on main thread. Title updates ~1× per second.
4. **Reconnect + ping loop** — Port the logic from [hl_ws_service.py:355-389](react_dashboard/backend/hl_ws_service.py:355). Test by toggling Wi-Fi off/on and watching the app self-heal.
5. **Dropdown menu** — Last update timestamp, connection status, Quit.
6. **24h change via REST** — Poll `https://api.hyperliquid.xyz/info` with `{type:"metaAndAssetCtxs"}` every 30s, extract `prevDayPx` for BTC, compute `(price - prev)/prev * 100`, show in dropdown.
7. **Launch-at-login + Applications install** — `SMAppService.mainApp.register()` + drag-to-Applications instructions in README.
8. **Package + notarise (optional)** — Archive → Developer ID → notarytool. Only needed if shipping to other machines; for personal use, `xcodebuild -scheme BTCMenuBar -configuration Release` is enough.

**Time estimate (Claude Code execution):** ~30–60 minutes end-to-end for milestones 1–7. The Swift code itself is ~300 lines across 4 files — that's a few minutes of generation. The real wall-clock cost is:
- Xcode project scaffolding (avoidable by using SwiftPM + a hand-written `Info.plist`, which I can do without GUI)
- User-side verification on the actual menu bar (you need to launch it, watch the price tick, toggle Wi-Fi to test reconnect — maybe 5–10 min of back-and-forth)
- `xcodebuild` cycles (~30–60s each)

Milestone 8 (notarisation) adds 5–15 min if needed — mostly waiting on Apple's notary service.

---

## 6. File layout

New top-level directory; no changes to existing macro2 code.

```
macro_2/
└── menubar_app/                    ← new
    ├── README.md                   ← how to build, install, run
    ├── BTCMenuBar.xcodeproj/       ← Xcode project
    └── BTCMenuBar/
        ├── BTCMenuBarApp.swift     ← @main, AppDelegate, NSStatusItem
        ├── HLWSClient.swift        ← WebSocket + reconnect + ping
        ├── PriceStore.swift        ← @Published price, change_24h, status
        ├── MenuBuilder.swift       ← dropdown menu construction
        └── Info.plist              ← LSUIElement=YES (no Dock icon)
```

Critical `Info.plist` keys:
- `LSUIElement = YES` — menu-bar-only, no Dock icon
- `CFBundleIdentifier = com.kriszhang.btcmenubar`
- `LSMinimumSystemVersion = 13.0` — `SMAppService` requires Ventura+

---

## 7. Open questions (decide before milestone 1)

- **Decimal places in the menu bar title?** `$69,420` or `$69,420.50` — affects width. Default: no decimals.
- **Show change % alongside price in the title, or only in the dropdown?** Default: dropdown only — keeps the title compact.
- **Auto-launch at login?** Default: yes, via `SMAppService.mainApp.register()` on first launch with a one-time consent dialog.
- **Other coins?** v1 is BTC-only. The WS payload contains all of `HL_PERPS` ([hyperliquid_extractor.py:22-40](data_extractors/hyperliquid_extractor.py:22)) — adding ETH/SOL/HYPE later is trivial (a coin picker in the dropdown).

---

## 8. Out of scope (explicitly not in v1)

- Charts / sparklines in the dropdown (use the React dashboard for that).
- Notifications (price alerts) — separate feature, separate plan.
- Multi-instrument tickers scrolling in the menu bar.
- Touching `data_aggregator.py`, `hl_extract.py`, the launchd plists, or any of the 4 dashboards. The menu bar app is purely additive and lives in its own subfolder.
- Selling/buying — strictly a read-only display app, no signed actions.

---

## 9. References

- WS relay to mirror: [react_dashboard/backend/hl_ws_service.py](react_dashboard/backend/hl_ws_service.py)
- REST extractor for `prevDayPx`: [data_extractors/hyperliquid_extractor.py:82](data_extractors/hyperliquid_extractor.py:82)
- Hyperliquid WS docs: `https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket`
- Hyperliquid rate limits: 10 WS connections / IP, 1,000 subscriptions / IP, 2,000 messages/min — we use 1/1/~60 well within limits.
