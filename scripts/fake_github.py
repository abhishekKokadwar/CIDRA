"""A stand-in for the GitHub REST API, for running `cidra action` without GitHub.

Serves one failed run: its jobs (none marked, so every log is read), its log
archive (the given log file as the whole-job log), no open pull request, and
commit / pull-request comments, which it keeps. Every comment CIDRA posts is
written to `--out` as JSON, for the caller to check.

    python scripts/fake_github.py eval/fixtures/F-02/raw.log --out comments.json --port 8766
    CIDRA_GITHUB_API=http://127.0.0.1:8766 CIDRA_GITHUB_TOKEN=fake cidra action
"""

import argparse
import io
import json
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def serve(log_path: str, out_path: str, port: int = 8766) -> ThreadingHTTPServer:
    with open(log_path, "rb") as f:
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("0_test.txt", f.read())
    comments: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: int, payload, content_type: str = "application/json") -> None:
            data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path.endswith("/logs"):
                return self._reply(200, archive.getvalue(), "application/zip")
            if path.endswith("/jobs"):
                return self._reply(200, {"jobs": []})
            if path.endswith("/comments") or path.endswith("/pulls"):
                return self._reply(200, [c for c in comments if c["path"] == path])
            return self._reply(404, {"message": "Not Found"})

        def _write(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))["body"]
            comments.append({"method": self.command, "path": self.path.split("?")[0], "body": body, "id": len(comments) + 1})
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(comments, f, indent=1)
            self._reply(201, {"id": len(comments), "html_url": f"http://127.0.0.1:{port}/comment/{len(comments)}"})

        do_POST = do_PATCH = _write

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("log")
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=8766)
    args = ap.parse_args()
    serve(args.log, args.out, args.port).serve_forever()
