"""Serial evaluation pacing and an explicit per-run generation budget, not quota discovery."""
from time import monotonic, sleep


class PacedModel:
    def __init__(self, model, *, interval_seconds=6, max_generations=104, clock=monotonic, wait=sleep):
        if type(interval_seconds) not in (int, float) or not 0 <= interval_seconds <= 60:
            raise ValueError("Evaluation interval must be from 0 to 60 seconds")
        if type(max_generations) is not int or not 1 <= max_generations <= 500:
            raise ValueError("Generation budget must be from 1 to 500")
        self.model, self.interval, self.limit = model, interval_seconds, max_generations
        self.clock, self.wait, self.last_start, self.calls = clock, wait, None, 0

    def _call(self, method, request):
        if self.calls >= self.limit:
            raise RuntimeError("Evaluation generation budget reached")
        if self.last_start is not None:
            self.wait(max(0, self.interval - (self.clock() - self.last_start)))
        self.last_start = self.clock()
        self.calls += 1
        return getattr(self.model, method)(request)

    def generate(self, request):
        return self._call("generate", request)

    def plan(self, request):
        return self._call("plan", request)

    def configuration(self):
        return {"interval_seconds": self.interval, "generation_limit": self.limit,
                "attempted_generations": self.calls, "quota_discovered": False}
