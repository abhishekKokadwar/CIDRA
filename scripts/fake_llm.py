"""A stand-in LLM for end-to-end runs that need no API key.

Speaks just enough of the OpenAI chat-completions API for cidra.integrations.llm:
every request is answered with the forced `report` tool call, whose arguments
come from a JSON file of canned answers keyed by schema name:

    {"Analysis": {...}, "Patch": {...}}

Everything else in the run stays real: log fetch, sandbox, patch apply, verify,
publish. Only the model's judgement is scripted.

    python scripts/fake_llm.py eval/fixtures/F-02b/fake_llm.json --port 8765
    CIDRA_BASE_URL=http://127.0.0.1:8765/v1 CIDRA_API_KEY=fake cidra ...
"""

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def make_handler(answers: dict):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
            # llm.structured describes the tool as "Report the result as <Schema>."
            description = body.get("tools", [{}])[0].get("function", {}).get("description", "")
            match = re.search(r"as (\w+)\.", description)
            schema = match.group(1) if match else ""
            if schema not in answers:
                return self._send(404, {"error": {"message": f"no canned answer for {schema!r}"}})
            self._send(200, {
                "id": "fake", "object": "chat.completion", "created": 0,
                "model": body.get("model", "fake"),
                "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{"id": "call_0", "type": "function", "function": {
                        "name": "report", "arguments": json.dumps(answers[schema])}}],
                }}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            })

        def _send(self, status: int, payload: dict):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):  # keep the run's own log readable
            pass

    return Handler


def serve(answers_path: str, port: int = 8765) -> ThreadingHTTPServer:
    with open(answers_path, encoding="utf-8") as f:
        answers = json.load(f)
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(answers))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("answers", help="JSON file: schema name -> tool arguments")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = serve(args.answers, args.port)
    print(f"fake LLM on http://127.0.0.1:{args.port}/v1", flush=True)
    server.serve_forever()
