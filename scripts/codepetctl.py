"""Human-only local administration. Never register this CLI as an LLM tool."""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx

from backend.app.core.config import Settings

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "action",
    choices=[
        "list",
        "export",
        "remember",
        "edit",
        "delete",
        "clear",
        "pause",
        "resume",
        "approve",
        "deny",
    ],
)
parser.add_argument("--project", default="default")
parser.add_argument("--id")
parser.add_argument("--kind", choices=["preference", "difficulty", "topic"], default="preference")
parser.add_argument("--content")
args = parser.parse_args()
settings = Settings()
project = quote(args.project, safe="")
method, route, body = "GET", "/v1/memory/" + project, None
if args.action in {"pause", "resume"}:
    method, route, body = "POST", "/v1/observation", {"paused": args.action == "pause"}
elif args.action in {"approve", "deny"}:
    if not args.id:
        parser.error("--id required")
    method, route, body = (
        "POST",
        "/v1/approvals/" + quote(args.id, safe=""),
        {"approved": args.action == "approve"},
    )
elif args.action in {"remember", "edit"}:
    if not args.content or (args.action == "edit" and not args.id):
        parser.error("--content required; edit also requires --id")
    method = "POST" if args.action == "remember" else "PUT"
    route += "/" + quote(args.id, safe="") if args.action == "edit" else ""
    body = {"kind": args.kind, "content": args.content}
elif args.action in {"delete", "clear"}:
    if args.action == "delete" and not args.id:
        parser.error("--id required")
    if args.action == "clear" and input("Delete all project memory? Type DELETE: ") != "DELETE":
        raise SystemExit("Not deleted")
    method = "DELETE"
    route += "/" + quote(args.id, safe="") if args.action == "delete" else ""
elif args.action == "export":
    route += "/export"
with httpx.Client(
    base_url="http://127.0.0.1:8765",
    trust_env=False,
    timeout=10,
    headers={"Authorization": "Bearer " + settings.token.get_secret_value()},
) as client:
    if args.action == "approve":
        proposal = client.get(route)
        proposal.raise_for_status()
        print(json.dumps(proposal.json(), ensure_ascii=False, indent=2))
        if (
            input(
                "Execute these tests with your user filesystem/network permissions? Type APPROVE: "
            )
            != "APPROVE"
        ):
            raise SystemExit("Not approved")
    response = client.request(method, route, json=body)
    response.raise_for_status()
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))
