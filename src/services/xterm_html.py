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
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/css/xterm.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0"></script>
  <script src="https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/lib/addon-fit.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/@xterm/addon-web-links@0.11.0/lib/addon-web-links.js"></script>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html, body, #term {{ height: 100%; width: 100%; background: #1a1a1a; }}
    #status {{ position: fixed; top: 0; left: 0; right: 0; padding: 6px 12px;
              font: 12px "JetBrains Mono", monospace; color: #bbb; 
              background: rgba(30, 30, 30, 0.85); backdrop-filter: blur(8px);
              z-index: 10; display: flex; justify-content: space-between;
              border-bottom: 1px solid rgba(255,255,255,0.05); }}
    #status.error {{ color: #ff5555; background: rgba(60, 20, 20, 0.85); }}
    #status.ok {{ color: #50fa7b; background: rgba(20, 50, 20, 0.85); }}
    #extra-keys {{ position: fixed; bottom: 0; left: 0; right: 0; height: 44px;
                  background: rgba(30, 30, 30, 0.95); backdrop-filter: blur(8px);
                  display: flex; flex-direction: row; align-items: center;
                  overflow-x: auto; white-space: nowrap; padding: 0 6px; z-index: 20; gap: 6px;
                  border-top: 1px solid rgba(255,255,255,0.05); }}
    #extra-keys::-webkit-scrollbar {{ display: none; }}
    #extra-keys button {{ flex: 0 0 auto; min-width: 40px; height: 32px; padding: 0 10px; font-size: 13px;
                          font-family: "JetBrains Mono", monospace; font-weight: bold; border-radius: 6px;
                          border: 1px solid rgba(255,255,255,0.1); background: rgba(60, 60, 60, 0.5); 
                          color: #e0e0e0; cursor: pointer; transition: all 0.1s; }}
    #extra-keys button:active {{ background: rgba(80, 80, 80, 0.8); transform: scale(0.95); }}
    #extra-keys button.active {{ background: #8be9fd; border-color: #8be9fd; color: #1e1e1e; }}
    #term {{ padding-top: 32px; padding-bottom: 44px; height: 100%; }}
    .xterm-viewport::-webkit-scrollbar {{ width: 8px; }}
    .xterm-viewport::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.2); border-radius: 4px; }}
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
      var term, ws, statusEl, fitAddon;
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
          fontFamily: '"JetBrains Mono", monospace',
          fontSize: 13,
          macOptionIsMeta: true,
          scrollback: 10000,
          theme: {{
            background: '#1a1a1a',
            selectionBackground: 'rgba(255, 255, 255, 0.2)'
          }}
        }});

        fitAddon = new FitAddon.FitAddon();
        term.loadAddon(fitAddon);

        var webLinksAddon = new WebLinksAddon.WebLinksAddon();
        term.loadAddon(webLinksAddon);

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
        fitAddon.fit();
        
        // Debounce resize events so mobile keyboard animations don't crash xterm
        var resizeTimeout;
        window.addEventListener('resize', function() {{
          clearTimeout(resizeTimeout);
          resizeTimeout = setTimeout(function() {{
            fitAddon.fit();
          }}, 100);
        }});

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
          // fit addon handles resize immediately, send size to server
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

      // Initialize after JetBrains Mono is likely loaded to ensure proper char measuring
      window.addEventListener('load', function() {{
        document.fonts.ready.then(init);
      }});
    }})();
  </script>
</body>
</html>"""
    # fmt: on
