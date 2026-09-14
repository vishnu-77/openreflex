"""Versioned execution-policy loading.

Policy values live in TOML rather than Python so routing, scoring, visibility and
budget behaviour can evolve without scattering magic numbers through the engine.
"""

from __future__ import annotations

import copy
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .project import home


class PolicyError(ValueError):
    pass


def _read(path: Path) -> dict[str, Any]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise PolicyError(f"Could not read OpenReflex policy {path}: {error}") from error
    if not isinstance(data, dict):
        raise PolicyError(f"OpenReflex policy {path} must be a TOML table")
    return data


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


@dataclass(frozen=True)
class Policy:
    data: dict[str, Any]
    sources: tuple[str, ...]

    @property
    def version(self) -> str:
        return str(self.value("meta.version"))

    def value(self, path: str) -> Any:
        current: Any = self.data
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                raise PolicyError(f"Missing OpenReflex policy value: {path}")
            current = current[part]
        return current

    def number(self, path: str) -> float:
        value = self.value(path)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PolicyError(f"OpenReflex policy value {path} must be numeric")
        return float(value)

    def integer(self, path: str) -> int:
        value = self.value(path)
        if isinstance(value, bool) or not isinstance(value, int):
            raise PolicyError(f"OpenReflex policy value {path} must be an integer")
        return value

    def boolean(self, path: str) -> bool:
        value = self.value(path)
        if not isinstance(value, bool):
            raise PolicyError(f"OpenReflex policy value {path} must be boolean")
        return value

    def strings(self, path: str) -> tuple[str, ...]:
        value = self.value(path)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise PolicyError(f"OpenReflex policy value {path} must be a list of strings")
        return tuple(value)

    def table(self, path: str) -> dict[str, Any]:
        value = self.value(path)
        if not isinstance(value, dict):
            raise PolicyError(f"OpenReflex policy value {path} must be a table")
        return value

    def tables(self, path: str) -> tuple[dict[str, Any], ...]:
        value = self.value(path)
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise PolicyError(f"OpenReflex policy value {path} must be an array of tables")
        return tuple(value)


def load_policy(project: Path | None = None) -> Policy:
    packaged = Path(__file__).with_name("policies") / "default.toml"
    candidates = [packaged, home() / "config.toml"]
    if project is not None:
        candidates.append(project / ".openreflex.toml")

    data: dict[str, Any] = {}
    used: list[str] = []
    for path in candidates:
        override = _read(path)
        if override:
            data = _merge(data, override)
            used.append(str(path))

    if not data:
        raise PolicyError("No OpenReflex execution policy could be loaded")
    policy = Policy(data=data, sources=tuple(used))
    _validate(policy)
    return policy


def _validate(policy: Policy) -> None:
    if not policy.version:
        raise PolicyError("meta.version must not be empty")

    weights = policy.table("score.weights")
    if not weights or any(not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0
                          for value in weights.values()):
        raise PolicyError("score.weights must contain non-negative numeric values")
    if sum(float(value) for value in weights.values()) <= 0:
        raise PolicyError("score.weights must have a positive total")

    strategies = policy.tables("routing.strategies")
    names = [str(item.get("name", "")) for item in strategies]
    if not names or any(not name for name in names) or len(names) != len(set(names)):
        raise PolicyError("routing.strategies must have unique non-empty names")

    for path in (
        "retrieval.threshold",
        "context.chars_per_token",
        "routing.prior_weight",
        "routing.regret_weight",
        "score.evidence_saturation",
        "score.route_advantage_scale",
    ):
        if policy.number(path) <= 0:
            raise PolicyError(f"{path} must be positive")
