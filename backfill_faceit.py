#!/usr/bin/env python3
"""One-time (repeatable) backfill of FACEIT per-match ELO history.

Why this is not just a requests.get()
-------------------------------------
FACEIT's per-match endpoint --

    https://api.faceit.com/stats/v1/stats/time/users/{guid}/games/cs2?page=N&size=100

-- is the only place per-match `elo` and `elo_delta` exist, and it sits behind
Cloudflare. curl, requests, and every other non-browser client get a challenge
page (HTTP 403) regardless of headers; it is a TLS-fingerprint check, not
something a User-Agent string can talk its way past. A real browser passes.

So the browser does the fetching and hands the result back to this script over
localhost. Run this, follow the printed instructions, and the CSV lands in
data/raw/faceit/.

This is a backfill, not a daily job. FACEIT history is immutable and always
re-fetchable, so it does not need the daily-snapshot treatment that Leetify's
rolling 100-match window does. capture.py handles the ongoing FACEIT signal
(current elo + skill level) via an endpoint that is not Cloudflare-protected.

Usage:
    python3 backfill_faceit.py
"""

import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import config

PORT = 8765
OUT = config.RAW_FACEIT / "faceit_cs2_history.csv"

SNIPPET = """
(async function(){
  const G="%s";
  const out=[]; let page=0;
  while(page<40){
    const r=await fetch(`https://api.faceit.com/stats/v1/stats/time/users/${G}/games/cs2?page=${page}&size=100`);
    if(!r.ok) return "HTTP "+r.status+" on page "+page;
    const a=await r.json();
    if(!a.length) break;
    out.push(...a); page++;
  }
  const rows=out.map(x=>[
    new Date(x.date).toISOString(), x.matchId, x.elo||"", x.elo_delta||"",
    x.i1||"", x.i6||"", x.i7||"", x.i8||"", x.i13||"", x.c2||"", x.c3||"", x.c4||"",
    (x.i18||"").replace(/,/g,";"), x.gameMode||""
  ].join(",")).reverse();
  const csv="finished_at,match_id,elo,elo_delta,map_name,kills,assists,deaths,"
    +"headshots,kd,kr,hs_pct,score,game_mode\\n"+rows.join("\\n");
  await fetch("http://127.0.0.1:%d/", {method:"POST", headers:{"Content-Type":"text/plain"}, body:csv});
  return "sent "+rows.length+" rows to the local receiver";
})()
""".strip()


class Receiver(BaseHTTPRequestHandler):
    received = None

    def do_OPTIONS(self):  # noqa: N802 - BaseHTTPRequestHandler naming
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        Receiver.received = body
        self.send_response(200)
        self._cors()
        self.end_headers()
        self.wfile.write(b"ok")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, *args):
        pass  # keep the console clean


def main() -> int:
    config.RAW_FACEIT.mkdir(parents=True, exist_ok=True)
    server = HTTPServer(("127.0.0.1", PORT), Receiver)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print("Listening on http://127.0.0.1:%d\n" % PORT)
    print("1. Open a browser tab at https://api.faceit.com/users/v1/users"
          "?game=cs2&game_id=%s" % config.STEAM64)
    print("   (the fetch must run from the api.faceit.com origin)")
    print("2. Open the devtools console and paste:\n")
    print(SNIPPET % (config.FACEIT_GUID, PORT))
    print("\n3. Waiting for the POST... (Ctrl-C to abort)\n")

    try:
        while Receiver.received is None:
            threading.Event().wait(0.5)
    except KeyboardInterrupt:
        print("aborted")
        return 1

    with open(OUT, "w", encoding="utf-8") as handle:
        handle.write(Receiver.received)

    rows = Receiver.received.count("\n")
    print("wrote %s (%d rows)" % (OUT, rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
