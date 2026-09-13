import hashlib
import math
import re

from .models import CandidatePath, Experience


def embed(text: str, dimensions: int = 256) -> list[float]:
    """Offline lexical feature hashing, not a pretrained semantic model."""
    vector = [0.0] * dimensions
    words = re.findall(r"[a-z0-9_]{2,}", text.lower())
    for word in words + [a + " " + b for a, b in zip(words, words[1:])]:
        digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
        vector[int.from_bytes(digest[:4], "little") % dimensions] += 1 if digest[4] % 2 else -1
    norm = math.sqrt(sum(v * v for v in vector)) or 1
    return [v / norm for v in vector]


def similarity(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def classify(description: str) -> str:
    words = set(re.findall(r"[a-z]+", description.lower()))
    for name, terms in [("debug", {"fix", "bug", "failure", "error", "broken"}),
                        ("refactor", {"refactor", "migrate", "migration"}),
                        ("test", {"test", "tests", "coverage"})]:
        if words & terms:
            return name
    return "build"


def utility(success: float, seconds: float, calls: float, tokens: float, risk: float = 0,
            uncertainty: float = 0, reversibility: float = 1) -> float:
    return (0.55 * success - 0.12 * min(seconds / 900, 1) - 0.10 * min(calls / 40, 1)
            - 0.08 * min(tokens / 16000, 1) - 0.08 * risk - 0.04 * uncertainty
            + 0.03 * reversibility)


def candidates(task_id: str, task_class: str, experiences: list[Experience]) -> list[CandidatePath]:
    templates = [
        ("inspect-first", ["Locate the relevant implementation with targeted search", "Inspect nearby conventions", "Make a small change and verify it"], .78, 420, 14, 5000, .15, .9),
        ("test-first", ["Reproduce the issue with a focused check", "Change the smallest failing behavior", "Run focused tests and relevant regression checks"], .85, 540, 18, 6000, .10, .95),
        ("incremental", ["Identify interfaces and a reversible first slice", "Implement and validate one slice at a time", "Check integration behavior"], .82, 660, 22, 8000, .12, .95),
    ]
    result = []
    for strategy, steps, prior, seconds, calls, tokens, risk, reversible in templates:
        if task_class == "debug" and strategy == "test-first":
            prior += .08
        if task_class == "refactor" and strategy == "incremental":
            prior += .08
        evidence = [e for e in experiences if e.strategy == strategy and e.status != "unknown"]
        n = len(evidence)
        probability = (prior * 4 + sum(e.status == "success" for e in evidence)) / (4 + n)
        if n:
            seconds = (seconds * 4 + sum(e.elapsed_seconds for e in evidence)) / (4 + n)
            calls = (calls * 4 + sum(e.tool_calls for e in evidence)) / (4 + n)
            tokens = (tokens * 4 + sum(e.output_tokens_estimate for e in evidence)) / (4 + n)
        uncertainty = 1 / math.sqrt(1 + n)
        path = CandidatePath(task_id=task_id, strategy=strategy, steps=steps,
                             success_probability=probability, time_seconds=seconds, tool_calls=calls,
                             context_tokens=tokens, risk=risk, uncertainty=uncertainty,
                             reversibility=reversible, evidence_count=n)
        path.score = round(utility(probability, seconds, calls, tokens, risk, uncertainty, reversible), 5)
        result.append(path)
    return sorted(result, key=lambda p: (-p.score, p.strategy))
