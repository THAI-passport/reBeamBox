# ui: Web Bluetooth harness

Dependency-free page for trying the nn20 path (service 0x01F0) from Chrome or Edge, with no Python and no app.

```
cd ui && python3 -m http.server 8000      # then open http://localhost:8000 (Web Bluetooth needs localhost or https)
```

Files: `index.html`, `app.js` (UI and BLE), `nn20.js` (framing, container, checksum; also loadable from Node). It connects to
0x01F0, subscribes to 0x01F2, crops the picked image to 360 or 368 (the size the badge reports) with a circular mask on black,
builds a one-frame type 5 container, chunks it by MTU (P = min(446, mtu - 12)) and writes to 0x01F1 with the same ACK-batch
logic as the Python client. A Content-Security-Policy blocks all network access; there are no ads or analytics.
`tests/test_ui_nn20_js.py` checks that `nn20.js` produces the same bytes as `rebeambox/nn20.py` (needs Node, skipped otherwise).
(`package.json` and `node_modules` are an unused leftover of icon experiments; the page does not use them.)
