"""Shared xterm.js HTML page and URL builder for the real Colab PTY terminal WebSocket."""

from __future__ import annotations

import logging
from urllib.parse import urlparse
import requests

logger = logging.getLogger(__name__)


def create_terminal_ws_url(raw_url: str, token: str) -> str:
    """Create a new PTY terminal via POST /api/terminals on the Colab server
    and return the corresponding WebSocket URL (`wss://.../terminals/websocket/{name}`).
    """
    base_url = raw_url.rstrip("/")
    post_url = f"{base_url}/api/terminals?colab-runtime-proxy-token={token}"
    headers = {
        "X-Colab-Runtime-Proxy-Token": token,
    }

    logger.info("Creating PTY terminal via POST %s", post_url)
    resp = requests.post(post_url, headers=headers, timeout=10)
    resp.raise_for_status()

    term_info = resp.json()
    term_name = term_info["name"]
    logger.info("Created Colab terminal '%s'", term_name)

    parsed = urlparse(base_url)
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_url = (
        f"{ws_scheme}://{parsed.netloc}/terminals/websocket/{term_name}"
        f"?colab-runtime-proxy-token={token}"
    )
    return ws_url


def xterm_page(ws_url: str) -> str:
    """Return a complete HTML page with xterm.js connected to *ws_url* using the
    standard Jupyter terminal WebSocket array protocol (`["stdin", data]`, etc.).
    """
    # fmt: off
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,interactive-widget=resizes-content">
  <title>Colab Terminal</title>
  <link href="https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/css/xterm.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0"></script>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html, body, #term {{ height: 100%; width: 100%; background: #1e1e1e; }}
    #status {{ position: fixed; top: 0; left: 0; right: 0; padding: 4px 12px;
              font: 12px monospace; color: #aaa; background: #2d2d2d;
              z-index: 10; display: flex; justify-content: space-between; }}
    #status.error {{ color: #f44; background: #3d2020; }}
    #status.ok {{ color: #4a4; background: #203d20; }}
    #extra-keys {{ position: fixed; bottom: 0; left: 0; right: 0; height: 40px;
                  background: #2d2d2d; display: flex; flex-direction: row;
                  overflow-x: auto; white-space: nowrap; padding: 4px; z-index: 20; gap: 4px; }}
    #extra-keys::-webkit-scrollbar {{ display: none; }}
    #extra-keys button {{ flex: 0 0 auto; min-width: 36px; padding: 0 8px; font-size: 13px;
                          font-family: monospace; font-weight: bold; border-radius: 4px;
                          border: 1px solid #444; background: #3d3d3d; color: #eee; cursor: pointer; }}
    #extra-keys button:active {{ background: #555; }}
    #extra-keys button.active {{ background: #1e90ff; border-color: #1c86ee; color: #fff; }}
    #term {{ padding-top: 24px; padding-bottom: 40px; height: 100%; }}
  </style>
</head>
<body>
  <div id="status">Connecting…</div>
  <div id="term"></div>
  <div id="extra-keys">
    <button onclick="window.sendKey('\\x1b')">ESC</button>
    <button onclick="window.sendKey('\\x09')">TAB</button>
    <button id="btn-ctrl" onclick="window.toggleCtrl()">CTRL</button>
    <button id="btn-alt" onclick="window.toggleAlt()">ALT</button>
    <button onclick="window.sendKey('\\x1b[A')">▲</button>
    <button onclick="window.sendKey('\\x1b[B')">▼</button>
    <button onclick="window.sendKey('\\x1b[D')">◀</button>
    <button onclick="window.sendKey('\\x1b[C')">▶</button>
    <button onclick="window.sendKey('-')">-</button>
    <button onclick="window.sendKey('/')">/</button>
    <button onclick="window.sendKey('|')">|</button>
  </div>
  <script>
    (function() {{
      var term, ws, statusEl;
      var ctrlActive = false;
      var altActive = false;

      window.toggleCtrl = function() {{
        ctrlActive = !ctrlActive;
        document.getElementById('btn-ctrl').className = ctrlActive ? 'active' : '';
        if(term) term.focus();
      }};
      
      window.toggleAlt = function() {{
        altActive = !altActive;
        document.getElementById('btn-alt').className = altActive ? 'active' : '';
        if(term) term.focus();
      }};

      window.sendKey = function(key) {{
        if (ws && ws.readyState === WebSocket.OPEN) {{
          ws.send(JSON.stringify(["stdin", key]));
        }}
        if(term) term.focus();
      }};

      function init() {{
        statusEl = document.getElementById('status');

        term = new Terminal({{
          cursorBlink: true,
          cursorStyle: 'block',
          fontFamily: 'monospace',
          fontSize: 13,
          macOptionIsMeta: true,
        }});

        term.onData(function(data) {{
          if (ws && ws.readyState === WebSocket.OPEN) {{
            if (ctrlActive && data.length === 1) {{
              var code = data.charCodeAt(0);
              if (code >= 97 && code <= 122) {{ // a-z
                data = String.fromCharCode(code - 96);
              }} else if (code >= 65 && code <= 90) {{ // A-Z
                data = String.fromCharCode(code - 64);
              }}
              window.toggleCtrl();
            }}
            if (altActive) {{
              data = '\\x1b' + data;
              window.toggleAlt();
            }}
            ws.send(JSON.stringify(["stdin", data]));
          }}
        }});

        term.onResize(function({{cols, rows}}) {{
          if (ws && ws.readyState === WebSocket.OPEN) {{
            console.log('[Colab TTY] Resizing terminal to cols:', cols, 'rows:', rows);
            ws.send(JSON.stringify(["set_size", rows, cols]));
          }}
        }});

        term.open(document.getElementById('term'));
        term.focus();
        connect();
      }}

      function connect() {{
        statusEl.textContent = 'Connecting to Colab terminal…';
        statusEl.className = '';
        console.log('[Colab TTY] Connecting WebSocket:', "{ws_url}");
        ws = new WebSocket("{ws_url}");
        ws.onopen = function() {{
          console.log('[Colab TTY] WebSocket opened successfully.');
          statusEl.textContent = 'Connected';
          statusEl.className = 'ok';
          ws.send(JSON.stringify(["set_size", term.rows, term.cols]));
        }};
        ws.onmessage = function(ev) {{
          try {{
            var m = JSON.parse(ev.data);
            if (Array.isArray(m)) {{
              if (m[0] === 'stdout') {{
                term.write(m[1]);
              }} else if (m[0] === 'setup') {{
                console.log('[Colab TTY] Terminal setup complete');
              }} else if (m[0] === 'disconnect') {{
                console.warn('[Colab TTY] Terminal disconnected by server');
              }}
            }} else if (m && m.data) {{
              term.write(m.data);
            }}
          }} catch(e) {{
            console.error('[Colab TTY] Error parsing message:', ev.data, e);
          }}
        }};
        ws.onerror = function(err) {{
          statusEl.textContent = 'WebSocket error (see logs/console)';
          statusEl.className = 'error';
          console.error('[Colab TTY] WebSocket error:', err);
        }};
        ws.onclose = function(e) {{
          statusEl.textContent = 'Disconnected (' + (e.code || '') + ') — reconnecting in 5s…';
          statusEl.className = 'error';
          console.warn('[Colab TTY] WebSocket closed. Code:', e.code, 'Reason:', e.reason);
          ws = null;
        }};
      }}

      // Auto-reconnect every 5 seconds
      setInterval(function() {{
        if (!ws || ws.readyState > 1) connect();
      }}, 5000);

      init();
    }})();
  </script>
</body>
</html>"""
    # fmt: on
