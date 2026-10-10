"""Log JSONL por tarea. Todo pasa por el redactor de secretos antes de tocar el disco."""

from __future__ import annotations

import json
import os
import time

from agent.redact import redact_text


class TaskLog:
    def __init__(self, task_id: str, base_dir: str, secrets=()):
        self.task_id = task_id
        self.secrets = list(secrets)
        self.dir = os.path.join(base_dir, "tasks")
        self.path = os.path.join(self.dir, f"{task_id}.jsonl")
        self._t0 = time.monotonic()
        try:
            os.makedirs(self.dir, exist_ok=True)
        except OSError:
            self.path = ""

    def write(self, event: str, **data) -> None:
        if not self.path:
            return
        rec = {"t": round(time.monotonic() - self._t0, 2), "task": self.task_id, "event": event, **data}
        line = redact_text(json.dumps(rec, ensure_ascii=False, default=repr), self.secrets)
        try:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass
