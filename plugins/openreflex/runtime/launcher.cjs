#!/usr/bin/env node
"use strict";

/*
 * OpenReflex Claude plugin runtime supervisor.
 *
 * The plugin never executes an arbitrary `openreflex` from PATH. It keeps an exact
 * plugin-version runtime under ~/.openreflex/runtime/vX.Y.Z and dispatches hooks to it.
 * First bootstrap is allowed only at SessionStart or explicit onboarding; all other
 * hook events fail open if the managed runtime is unavailable.
 */

const fs = require("fs");
const os = require("os");
const path = require("path");
const cp = require("child_process");

const args = process.argv.slice(2);
const sleepBuffer = new Int32Array(new SharedArrayBuffer(4));

function sleep(ms) {
  Atomics.wait(sleepBuffer, 0, 0, ms);
}

function argValue(name) {
  const exact = args.indexOf(name);
  if (exact >= 0 && exact + 1 < args.length) return args[exact + 1];
  const prefix = name + "=";
  const found = args.find((item) => item.startsWith(prefix));
  return found ? found.slice(prefix.length) : null;
}

const pluginRoot = argValue("--plugin-root") || path.resolve(__dirname, "..");
const manifestPath = path.join(pluginRoot, ".claude-plugin", "plugin.json");
let expectedVersion = "";
try {
  expectedVersion = String(JSON.parse(fs.readFileSync(manifestPath, "utf8")).version || "").trim();
} catch (_) {
  expectedVersion = "";
}

const openreflexHome = process.env.OPENREFLEX_HOME || path.join(os.homedir(), ".openreflex");
const runtimeBase = process.env.OPENREFLEX_RUNTIME_ROOT || path.join(openreflexHome, "runtime");
const runtimeDir = path.join(runtimeBase, expectedVersion ? "v" + expectedVersion : "unknown");
const runtimePython = process.platform === "win32"
  ? path.join(runtimeDir, "Scripts", "python.exe")
  : path.join(runtimeDir, "bin", "python");
const runtimeExecutable = process.platform === "win32"
  ? path.join(runtimeDir, "Scripts", "openreflex.exe")
  : path.join(runtimeDir, "bin", "openreflex");
const lockPath = path.join(runtimeBase, expectedVersion ? ".v" + expectedVersion + ".lock" : ".bootstrap.lock");
const logPath = path.join(openreflexHome, "logs", "bootstrap.log");

function appendLog(message) {
  try {
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    fs.appendFileSync(logPath, new Date().toISOString() + " " + message + "\n", "utf8");
  } catch (_) {
    // Bootstrap diagnostics must never block Claude.
  }
}

function run(command, commandArgs, options = {}) {
  try {
    return cp.spawnSync(command, commandArgs, {
      encoding: "utf8",
      windowsHide: true,
      timeout: options.timeout || 120000,
      input: options.input,
      env: options.env || process.env,
    });
  } catch (error) {
    return { status: 1, stdout: "", stderr: String(error) };
  }
}

function versionFrom(python) {
  if (!python || !fs.existsSync(python)) return null;
  const result = run(
    python,
    ["-c", "import openreflex; print(openreflex.__version__)"],
    { timeout: 10000 },
  );
  if (result.status !== 0) return null;
  return String(result.stdout || "").trim() || null;
}

function pythonVersion(command, prefix = []) {
  const result = run(
    command,
    [...prefix, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
    { timeout: 10000 },
  );
  if (result.status !== 0) return null;
  const match = String(result.stdout || "").trim().match(/^(\d+)\.(\d+)$/);
  if (!match) return null;
  const major = Number(match[1]);
  const minor = Number(match[2]);
  return major > 3 || (major === 3 && minor >= 11) ? { command, prefix } : null;
}

function findBasePython() {
  const candidates = [];
  if (process.env.OPENREFLEX_PYTHON) candidates.push([process.env.OPENREFLEX_PYTHON, []]);
  if (process.platform === "win32") {
    candidates.push(["py", ["-3.13"]], ["py", ["-3.12"]], ["py", ["-3.11"]], ["py", ["-3"]]);
  }
  candidates.push(["python3.13", []], ["python3.12", []], ["python3.11", []], ["python3", []], ["python", []]);
  for (const [command, prefix] of candidates) {
    const found = pythonVersion(command, prefix);
    if (found) return found;
  }
  return null;
}

function acquireLock(timeoutMs = 120000) {
  fs.mkdirSync(runtimeBase, { recursive: true });
  const deadline = Date.now() + timeoutMs;
  while (true) {
    try {
      const fd = fs.openSync(lockPath, "wx");
      fs.writeFileSync(fd, String(process.pid));
      fs.closeSync(fd);
      return true;
    } catch (error) {
      if (error && error.code !== "EEXIST") throw error;
      try {
        const ageMs = Date.now() - fs.statSync(lockPath).mtimeMs;
        if (ageMs > 300000) {
          fs.unlinkSync(lockPath);
          appendLog("reclaimed stale bootstrap lock");
          continue;
        }
      } catch (_) {
        // The lock disappeared between attempts; retry immediately.
        continue;
      }
      if (Date.now() >= deadline) return false;
      sleep(100);
    }
  }
}

function releaseLock() {
  try { fs.unlinkSync(lockPath); } catch (_) {}
}

function bootstrapAllowed() {
  if (args[0] === "onboard" || args[0] === "tui") return true;
  return args[0] === "hook" && args[2] === "SessionStart";
}

function ensureRuntime() {
  if (!expectedVersion) throw new Error("plugin manifest version is unavailable");
  if (versionFrom(runtimePython) === expectedVersion && fs.existsSync(runtimeExecutable)) return runtimePython;
  if (!bootstrapAllowed()) return null;

  if (!acquireLock()) throw new Error("timed out waiting for another OpenReflex runtime bootstrap");
  try {
    if (versionFrom(runtimePython) === expectedVersion && fs.existsSync(runtimeExecutable)) return runtimePython;

    const basePython = findBasePython();
    if (!basePython) {
      throw new Error("Python 3.11+ was not found; set OPENREFLEX_PYTHON to a compatible interpreter");
    }

    try { fs.rmSync(runtimeDir, { recursive: true, force: true }); } catch (_) {}
    fs.mkdirSync(runtimeBase, { recursive: true });

    appendLog("creating managed runtime " + expectedVersion);
    let result = run(
      basePython.command,
      [...basePython.prefix, "-m", "venv", runtimeDir],
      { timeout: 120000 },
    );
    if (result.status !== 0) {
      throw new Error("could not create managed Python environment: " + String(result.stderr || "").trim());
    }

    const spec = process.env.OPENREFLEX_BOOTSTRAP_SPEC || ("openreflex==" + expectedVersion);
    result = run(
      runtimePython,
      ["-m", "pip", "install", "--disable-pip-version-check", "--quiet", "--upgrade", spec],
      { timeout: 180000 },
    );
    if (result.status !== 0) {
      throw new Error("could not install " + spec + ": " + String(result.stderr || "").trim());
    }

    const installed = versionFrom(runtimePython);
    if (installed !== expectedVersion) {
      throw new Error("managed runtime reports " + (installed || "unknown") + ", expected " + expectedVersion);
    }
    appendLog("managed runtime ready " + installed);
    return runtimePython;
  } finally {
    releaseLock();
  }
}

function shellQuote(value) {
  return '"' + String(value).replace(/"/g, '\\"') + '"';
}

function setupFailure(error) {
  const detail = error && error.message ? error.message : String(error);
  appendLog("bootstrap failed: " + detail);
  const short = "OpenReflex could not prepare its managed runtime " + (expectedVersion || "") +
    ". Run /openreflex:openreflex to retry. Details: " + logPath;
  if (args[0] === "hook") {
    if (args[2] === "SessionStart") {
      process.stdout.write(JSON.stringify({ systemMessage: "↺ OpenReflex · SETUP REQUIRED\n" + short }));
    }
    return 0;
  }
  process.stdout.write("OPENREFLEX / SETUP\n  state       repair required\n  detail      " + short + "\n");
  return 1;
}

function main() {
  let python;
  try {
    python = ensureRuntime();
  } catch (error) {
    return setupFailure(error);
  }

  if (!python) {
    // Normal hook events fail open while SessionStart/onboarding owns bootstrap.
    return 0;
  }

  const forwarded = args[0] === "onboard" ? ["onboard", ...args.slice(1)] : args;
  const input = ["hook", "statusline"].includes(args[0]) ? fs.readFileSync(0) : Buffer.alloc(0);
  const env = {
    ...process.env,
    OPENREFLEX_PLUGIN_VERSION: expectedVersion,
    OPENREFLEX_RUNTIME_COMMAND: shellQuote(runtimeExecutable),
  };
  const result = run(python, ["-m", "openreflex", ...forwarded], {
    timeout: args[0] === "hook" ? 30000 : 120000,
    input,
    env,
  });

  if (result.stdout) process.stdout.write(result.stdout);
  if (result.stderr) process.stderr.write(result.stderr);
  return Number.isInteger(result.status) ? result.status : 1;
}

process.exitCode = main();
