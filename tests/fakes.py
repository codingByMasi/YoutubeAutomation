"""Fake googleapiclient services that record calls and return canned responses."""

from __future__ import annotations


class Req:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class Resource:
    def __init__(self, svc, name):
        self.svc, self.name = svc, name

    def __getattr__(self, method):
        def call(**kw):
            self.svc.calls.append((f"{self.name}.{method}", kw))
            handler = self.svc.handlers.get(f"{self.name}.{method}")
            return Req(lambda: handler(**kw) if handler else {})
        return call


class FakeService:
    """`svc.videos().insert(...).execute()` style fake. Set handlers['videos.insert'] = fn(**kw) -> dict."""

    def __init__(self, handlers=None):
        self.calls: list[tuple[str, dict]] = []
        self.handlers = handlers or {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda: Resource(self, name)

    def names(self):
        return [c[0] for c in self.calls]
