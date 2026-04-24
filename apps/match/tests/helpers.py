from typing import Any


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.raise_error: bool = False

    def set(self, key, value):
        if self.raise_error:
            raise RuntimeError("redis down")
        self.store[key] = value
        return True

    def get(self, key):
        if self.raise_error:
            raise RuntimeError("redis down")
        return self.store.get(key)
