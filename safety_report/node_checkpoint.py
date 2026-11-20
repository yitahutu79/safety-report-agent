"""Local, project-scoped checkpoints for completed chapter graph nodes."""
import hashlib
import json
import os
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


class NodeCheckpoint:
    VERSION = 1

    def __init__(self, path, scope):
        self.path = Path(path)
        self.scope = digest({'version': self.VERSION, 'scope': scope})
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            data = {}
        self.entries = data.get('entries', {}) if data.get('scope') == self.scope and isinstance(data.get('entries'), dict) else {}

    def key(self, name, state):
        # Functions, cancellation objects and credentials are never serialized.
        keys = ('system', 'payload', 'evidence', 'source_review', 'queries', 'draft', 'issues', 'previous_issues', 'attempt', 'events', 'units', 'unit_issues')
        return digest({'node': name, 'state': {k: state[k] for k in keys if k in state}})

    def get(self, key):
        return self.entries.get(key)

    def put(self, key, value):
        self.entries[key] = value
        while len(self.entries) > 256:
            self.entries.pop(next(iter(self.entries)))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + '.tmp')
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump({'scope': self.scope, 'entries': self.entries}, out, ensure_ascii=False)
        os.chmod(temp, 0o600)
        os.replace(temp, self.path)

    def clear(self):
        self.path.unlink(missing_ok=True)
        self.entries = {}
