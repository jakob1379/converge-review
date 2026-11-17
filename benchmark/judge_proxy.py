#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("JUDGE_PORT", 8787))
SLOTS = threading.Semaphore(int(os.environ.get("JUDGE_SLOTS", 20)))
CWD = tempfile.mkdtemp(prefix="judge-")
ISOLATE = ["--setting-sources", "", "--tools", "", "--strict-mcp-config", "--no-session-persistence",
           "--settings", '{"alwaysThinkingEnabled": false}', "--output-format", "json"]


def complete(req):
    if not req["model"].startswith("anthropic/"):
        raise ValueError(f"{req['model']}: only anthropic/* judges run through the local claude CLI")
    model = req["model"].removeprefix("anthropic/")
    system = "\n".join(m["content"] for m in req["messages"] if m["role"] == "system")
    user = "\n".join(m["content"] for m in req["messages"] if m["role"] == "user")
    with SLOTS:
        r = subprocess.run(["claude", "-p", "--model", model, "--system-prompt", system, *ISOLATE],
                           input=user, capture_output=True, text=True, cwd=CWD, timeout=120)
    out = json.loads(r.stdout)
    if out.get("is_error"):
        raise RuntimeError(out.get("result"))
    print(f"{model} cost={out.get('total_cost_usd', 0):.5f}", file=sys.stderr, flush=True)
    return {"id": out["session_id"], "object": "chat.completion", "created": 0, "model": req["model"],
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": out["result"]}}]}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            body, code = complete(json.loads(self.rfile.read(int(self.headers["Content-Length"])))), 200
        except Exception as e:
            body, code = {"error": {"message": f"{type(e).__name__}: {e}"}}, 500
            print(f"error {body['error']['message'][:300]}", file=sys.stderr, flush=True)
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
