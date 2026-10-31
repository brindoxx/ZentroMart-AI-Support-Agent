"""Serial evaluation pacing and an explicit per-run generation budget, not quota discovery."""
from time import monotonic, sleep
from collections import deque


class PacedModel:
    def __init__(self, model, *, interval_seconds=6, max_generations=104, input_tpm=None, clock=monotonic, wait=sleep):
        if type(interval_seconds) not in (int, float) or not 0 <= interval_seconds <= 60:
            raise ValueError("Evaluation interval must be from 0 to 60 seconds")
        if type(max_generations) is not int or not 1 <= max_generations <= 500:
            raise ValueError("Generation budget must be from 1 to 500")
        if input_tpm is not None and (type(input_tpm) is not int or input_tpm < 1024):
            raise ValueError("Input TPM must be at least 1024")
        self.model, self.interval, self.limit = model, interval_seconds, max_generations
        self.clock, self.wait, self.last_start, self.calls = clock, wait, None, 0
        self.input_tpm, self.reservations = input_tpm, deque()

    def _call(self, method, request):
        if self.calls >= self.limit:
            raise RuntimeError("Evaluation generation budget reached")
        if self.last_start is not None:
            self.wait(max(0, self.interval - (self.clock() - self.last_start)))
        if self.input_tpm is not None:
            # UTF-8 bytes plus generous framing overhead deliberately overestimate
            # input tokens. This is a local safeguard, not Google's tokenizer or
            # discovery of other clients' project-wide usage.
            reserved = len(request.instructions.encode('utf-8')) + len(request.message.encode('utf-8')) + 1024
            if reserved > self.input_tpm:
                raise ValueError("A request exceeds the conservative token-rate budget")
            while True:
                now = self.clock()
                while self.reservations and now - self.reservations[0][0] >= 60:
                    self.reservations.popleft()
                if sum(size for _, size in self.reservations) + reserved <= self.input_tpm:
                    self.reservations.append((now, reserved))
                    break
                self.wait(min(60, max(0, 60 - (now - self.reservations[0][0]))))
        self.last_start = self.clock()
        self.calls += 1
        return getattr(self.model, method)(request)

    def generate(self, request):
        return self._call("generate", request)

    def plan(self, request):
        return self._call("plan", request)

    def configuration(self):
        return {"interval_seconds": self.interval, "generation_limit": self.limit,
                "attempted_generations": self.calls, "input_tpm": self.input_tpm,
                "token_guard": "conservative_utf8_bytes_plus_framing", "quota_discovered": False}
