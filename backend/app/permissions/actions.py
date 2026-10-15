import hashlib
import json
import time
from dataclasses import dataclass
from uuid import uuid4

from backend.app.schemas.messages import ToolInput


@dataclass
class Approval:
    digest: str
    expires: float
    project: str
    approved: bool = False


class Permissions:
    def __init__(self):
        self.pending: dict[str, Approval] = {}

    @staticmethod
    def digest(request: ToolInput) -> str:
        payload = request.model_dump(mode="json", exclude={"approval_id"})
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def prune(self) -> None:
        now = time.monotonic()
        self.pending = {key: item for key, item in self.pending.items() if item.expires > now}

    def request(self, request: ToolInput) -> str:
        self.prune()
        if len(self.pending) >= 32:
            raise ValueError("Too many pending approvals")
        identity = str(uuid4())
        self.pending[identity] = Approval(
            self.digest(request), time.monotonic() + 120, request.project
        )
        return identity

    def decide(self, identity: str, approved: bool) -> bool:
        self.prune()
        if identity not in self.pending:
            return False
        if approved:
            self.pending[identity].approved = True
        else:
            del self.pending[identity]
        return True

    def consume(self, request: ToolInput) -> bool:
        self.prune()
        entry = self.pending.get(str(request.approval_id))
        if not entry or not entry.approved or entry.digest != self.digest(request):
            return False
        del self.pending[str(request.approval_id)]
        return True
