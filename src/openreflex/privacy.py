"""Minimize telemetry before persistence; never read accessed files or transcripts."""

import hashlib
import json
import re
from pathlib import Path

SECRET = re.compile(
    r"(?i)(bearer\s+)[\w.\-]+|((?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,;]+|"
    r"\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_\-]{8,}|"
    r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----"
)
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)

CATEGORY_BY_TOOL = {
    "read": "read", "view": "read", "notebookread": "read", "read_file": "read",
    "edit": "edit", "write": "edit", "multiedit": "edit", "notebookedit": "edit", "apply_patch": "edit",
    "str_replace": "edit", "create": "edit", "patch": "edit", "edit_file": "edit", "write_file": "edit",
    "grep": "search", "glob": "search", "ls": "search", "list": "search", "codebase_search": "search",
    "file_search": "search", "search": "search", "list_dir": "search",
    "webfetch": "web", "websearch": "web", "fetch": "web",
    "task": "delegate", "agent": "delegate",
    "todowrite": "plan", "todoread": "plan", "exitplanmode": "plan", "update_plan": "plan",
}
SHELL_TOOLS = {"bash", "shell", "local_shell", "exec_command", "run_terminal_cmd", "terminal", "powershell"}
COMMAND_CATEGORIES = [
    ("test", re.compile(r"\b(pytest|jest|vitest|mocha|rspec|phpunit|unittest|nox|tox|go test|cargo test|"
                        r"dotnet test|mvn (?:-\S+ )*test|gradlew? test|(?:npm|pnpm|yarn|bun) (?:run )?test|"
                        r"make test|ctest|helm (?:test|unittest)|ct install)\b")),
    ("lint", re.compile(r"\b(ruff|eslint|flake8|pylint|mypy|pyright|clippy|golangci-lint|prettier|biome|"
                        r"stylelint|tsc --noEmit|(?:npm|pnpm|yarn|bun) (?:run )?(?:lint|typecheck)|"
                        r"helm lint|ct lint|kubeconform|kubeval|yamllint)\b")),
    ("build", re.compile(r"\b(tsc|cargo build|go build|mvn|gradlew?|make|cmake|webpack|vite build|"
                         r"(?:npm|pnpm|yarn|bun) (?:run )?build|dotnet build|helm template|helmfile template)\b|"
                         r"\bhelm (?:install|upgrade)\b[^;&|\n]*--dry-run\b")),
    ("vcs", re.compile(r"^\s*(git|gh)\b")),
    ("search", re.compile(r"^\s*(grep|rg|ag|find|fd|ls|tree|dir|Get-ChildItem|Select-String)\b")),
    ("read", re.compile(r"^\s*(cat|head|tail|less|more|sed -n|type|Get-Content)\b")),
]
VERIFICATION = {"test", "lint", "build"}
PROGRESS = VERIFICATION | {"edit"}
NOISE_LINE = re.compile(r"^(Traceback|File \"|\s*at |[-=~^]{3,}|\s*$)")
RUN_SUMMARY = re.compile(r"^(?:(?:Tests?|Test Suites|Test Files):\s*)?\d+ (?:failed|passed|errors?)\b", re.I)


def redact(value: str, limit: int = 2000) -> str:
    return SECRET.sub(lambda m: (m.group(1) or m.group(2) or "") + "[REDACTED]", value)[:limit]


# Arguments that describe or bound a call without changing what it does. Claude's Bash tool gets a fresh
# model-written `description` every time, which made identical retried commands look distinct.
VOLATILE_ARGUMENTS = frozenset({"description", "justification", "timeout", "timeout_ms"})


def fingerprint(name: str, arguments: object) -> str:
    # Full inputs are deliberately discarded, but the hash distinguishes repeated calls.
    if isinstance(arguments, dict):
        arguments = {key: value for key, value in arguments.items() if key not in VOLATILE_ARGUMENTS}
    return hashlib.sha256((name + json.dumps(arguments, sort_keys=True, default=str)).encode()).hexdigest()


def categorize(name: str, arguments: object) -> str:
    """Coarse action category; a shell command is classified here and then discarded."""
    lowered = name.lower()
    if lowered.startswith(("mcp__", "mcp:")):
        return "mcp"
    if lowered in SHELL_TOOLS or any(word in lowered for word in ("shell", "bash", "terminal")):
        command = arguments.get("command", arguments.get("cmd", "")) if isinstance(arguments, dict) else arguments
        if isinstance(command, list):
            command = " ".join(map(str, command))
        command = str(command or "")
        if PATCH_FILE.search(command) or "apply_patch" in command:
            return "edit"
        return _command_category(command)
    return CATEGORY_BY_TOOL.get(lowered, "other")


# Commands that only set up context (location, echo) and say nothing about what the call is for.
NEUTRAL_COMMAND = re.compile(r"^\s*(cd|pushd|popd|Set-Location|Get-Location|pwd|echo|Write-Output|Write-Host|clear|cls)\b", re.I)
LOOKUP_CATEGORIES = {"search", "read", "vcs"}


def _command_category(command: str) -> str:
    """Classify a possibly compound command by the program each segment runs, not by words in its arguments.

    `Get-Location; rg --files -g '*test*' -g pytest.ini` is a search, even though "pytest" appears in an argument.
    """
    segments = [s for s in re.split(r"\s*(?:;|&&|\|\||\n)\s*", command) if s.strip() and not NEUTRAL_COMMAND.match(s)]
    first_lookup = None
    for segment in segments:
        head = next((category for category, pattern in COMMAND_CATEGORIES
                     if category in LOOKUP_CATEGORIES and pattern.search(segment)), None)
        if head:
            first_lookup = first_lookup or head
            continue  # a search or read never becomes a test just because its arguments mention one
        for category, pattern in COMMAND_CATEGORIES:
            if category not in LOOKUP_CATEGORIES and pattern.search(segment):
                return category
    return first_lookup or "shell"


def error_signature(error: str | None) -> str | None:
    """A short, low-cardinality error signature: the last meaningful line with volatile tokens masked."""
    if not error:
        return None
    # Strip pytest's "E   " / "F   " gutters and CLI "error: " style prefixes are kept as meaningful text.
    stripped = (re.sub(r"^[EF]\s{2,}", "", line.strip()) for line in redact(error, 4000).splitlines())
    lines = [line for line in stripped if not NOISE_LINE.match(line)]
    # Python/JS put the exception last; most CLIs put it first. Prefer a line that names an error.
    named = [line for line in lines if re.search(r"(?i)error|exception|fail|denied|not found|cannot", line)]
    # A test runner's closing tally ("2 failed in 0.03s") says less than the failing test line above it.
    named = [line for line in named if not RUN_SUMMARY.match(line)] or named
    line = (named or lines or [""])[-1 if named else 0]
    if len(line) < 4:
        return None
    line = re.sub(r"(?:[A-Za-z]:)?[\\/][^\s:'\"]+", "<path>", line)
    line = re.sub(r"0x[0-9a-fA-F]+|\b\d+(?:\.\d+)?(?:ms|s)?\b", "<n>", line)
    line = re.sub(r"(['\"]).{1,80}?\1", "<str>", line)
    return line[:160]


def file_paths(arguments: object, project: Path) -> list[str]:
    found: set[str] = set()
    root = project.resolve()

    def add(item: str) -> None:
        # Only project-relative paths are kept; anything outside the project is dropped entirely.
        try:
            relative = (project / Path(item)).resolve().relative_to(root)
        except (ValueError, OSError):
            return
        if relative.parts:
            found.add(redact(relative.as_posix(), 300))

    def visit(value: object, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"file_path", "filePath", "path", "filename", "notebook_path"} and isinstance(item, str):
                    add(item)
                elif isinstance(item, str) and key in {"input", "patch", "command", "cmd"}:
                    for match in PATCH_FILE.finditer(item[:200_000]):
                        add(match.group(1).strip())
                elif isinstance(item, (dict, list)):
                    visit(item, depth + 1)
        elif isinstance(value, list):
            for item in value[:100]:
                visit(item, depth + 1)

    visit(arguments)
    return sorted(found)[:100]
