import hashlib
import time
from collections import OrderedDict

from backend.app.schemas.messages import EditorEvent


class Proactive:
    def __init__(self, enabled: bool, cooldown: float = 120):
        self.enabled, self.cooldown = enabled, cooldown
        self.seen: OrderedDict[str, tuple[int, float]] = OrderedDict()
        self.last: dict[str, float] = {}

    def reset(self) -> None:
        self.seen.clear()
        self.last.clear()

    def observe(
        self, event: EditorEvent, mode: str = "tutor", now: float | None = None
    ) -> dict | None:
        if not self.enabled or mode == "silent":
            return None
        now = time.monotonic() if now is None else now
        for diagnostic in event.diagnostics:
            if diagnostic.severity != "error":
                continue
            key = hashlib.sha256(
                f"{event.project}:{event.path}:{diagnostic.line}:{diagnostic.message}".encode()
            ).hexdigest()
            count, previous = self.seen.get(key, (0, -1000))
            if now - previous < 2:
                continue
            count = count + 1 if now - previous < 600 else 1
            self.seen[key] = (count, now)
            self.seen.move_to_end(key)
            while len(self.seen) > 512:
                self.seen.popitem(last=False)
            if count >= 3 and now - self.last.get(event.project, -1000) >= self.cooldown:
                self.last[event.project] = now
                self.seen[key] = (0, now)
                return {
                    "type": "suggestion",
                    "path": event.path,
                    "line": diagnostic.line,
                    "message": "Este diagnóstico reapareceu três vezes. Quer analisá-lo?",
                    "evidence": diagnostic.message,
                }
        return None
