#!/usr/bin/env python3
"""Phase 1 of the dreaming pipeline: extract one raw memory per rollout.

Codex `phase1.rs`. For each claimed rollout (a past Claude Code session): render
the transcript to a filtered, secret-redacted DATA digest, ask a SMALL headless
model for strict JSON (`raw_memory`, `rollout_summary`, `rollout_slug`), apply
the no-op gate (default + preferred), and upsert into `stage1_outputs`. No-op and
parse/spawn failures don't crash the batch — each rollout is fault-isolated and
the job is marked done (no_output) or failed-with-backoff.

SECURITY (the dormant memory-loop threats this reactivates):
- T1/T7 injection: the transcript is DATA. The model runs with `--allowedTools ""`
  — no Read/Write/Bash/network — so an instruction injected into the transcript
  has NO mechanism to act (stronger than a writable-roots sandbox, which still
  permits reads). The system prompt also states the data-not-instructions rule.
- T4 secrets: `redact_secrets` runs BEFORE the model sees anything AND on the
  model's output before storage (defense in depth).
- T6 no-raw-content-in-argv: the prompt is piped via STDIN, not argv — out of
  `ps` and clear of ARG_MAX; we carry a redacted DIGEST, never the raw rollout.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import dream_discover as dd
import harness_lib as hl
import memories_db as mdb

DEFAULT_MODEL = "haiku"                # Codex phase 1 = small/cheap model
PHASE1_TIMEOUT = 600
MAX_DIGEST_CHARS = 280_000            # bound prompt size (Codex caps at 70% ctx)
TOOL_OUTPUT_CAP = 1500               # "avoid copying large tool outputs"
TOOL_INPUT_CAP = 600
REQUIRED_KEYS = ("rollout_summary", "rollout_slug", "raw_memory")

# Harness-injected context (AGENTS.md/CLAUDE.md/skill blocks) is noise, not user
# intent — Codex drops the equivalent `developer`/AGENTS/`<skill>` items.
SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)

# Best-effort secret redaction. Conservative: each key=value form needs a 6+ char
# contiguous value, so `token: 0` / prose won't match.
_SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),                              # AWS access key id
    re.compile(r"gh[posru]_[A-Za-z0-9]{30,}"),                    # GitHub tokens
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),                  # Slack tokens
    re.compile(r"sk-(?:ant-)?[A-Za-z0-9_\-]{20,}"),              # OpenAI/Anthropic keys
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),  # JWT
]
_KV_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd|access[_-]?key|client[_-]?secret)\b"
    r"(\s*[:=]\s*)(['\"]?)([^\s'\"]{6,})\3")


def redact_secrets(text):
    """Replace token/key/password-shaped substrings with `[REDACTED_SECRET]`."""
    if not text:
        return text
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED_SECRET]", text)
    return _KV_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED_SECRET]", text)


def _truncate(s, cap):
    s = (s or "").strip()
    return s if len(s) <= cap else s[:cap] + f"\n…[truncated {len(s) - cap} chars]"


def _stringify(content):
    """Flatten a tool_result `content` (str, or a list of content blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                parts.append(b.get("text", "") if b.get("type") == "text"
                             else json.dumps(b, ensure_ascii=False)[:200])
            else:
                parts.append(str(b))
        return "\n".join(parts)
    return str(content)


def render_rollout(transcript_path, max_chars=MAX_DIGEST_CHARS):
    """Render a Claude `.jsonl` transcript to a filtered DATA digest.

    Keeps (evidence order): genuine USER text, assistant TEXT, compact TOOL CALLS,
    truncated TOOL RESULTS. Drops `thinking` (large, low-signal), strips injected
    `<system-reminder>` blocks, ignores non-message records. Over the cap, keeps
    the tail (most recent turns = highest value). Returns "" on an unreadable or
    content-free transcript (→ no-op upstream)."""
    try:
        lines = Path(transcript_path).read_text(
            encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    blocks = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        typ = rec.get("type")
        if typ not in ("user", "assistant"):
            continue
        msg = rec.get("message")
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if typ == "user":
            if isinstance(content, str):
                text = SYSTEM_REMINDER_RE.sub("", content).strip()
                if text:
                    blocks.append("## User\n" + text)
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        out = _truncate(_stringify(b.get("content", "")), TOOL_OUTPUT_CAP)
                        if out:
                            blocks.append("## Tool result\n" + out)
        else:  # assistant
            if isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    bt = b.get("type")
                    if bt == "text":
                        t = (b.get("text") or "").strip()
                        if t:
                            blocks.append("## Assistant\n" + t)
                    elif bt == "tool_use":
                        inp = _truncate(
                            json.dumps(b.get("input", {}), ensure_ascii=False),
                            TOOL_INPUT_CAP)
                        blocks.append(f"## Tool call: {b.get('name', '?')}\n{inp}")
                    # `thinking` intentionally dropped
            elif isinstance(content, str) and content.strip():
                blocks.append("## Assistant\n" + content.strip())
    digest = "\n\n".join(blocks).strip()
    if len(digest) > max_chars:
        digest = "…[older turns truncated]\n\n" + digest[-max_chars:]
    return digest


def parse_strict_json(text):
    """Extract the model's strict JSON object and coerce the 3 required string
    fields. Raises ValueError on empty/missing-key/non-object output (→ job
    failure + backoff). Tolerant of a ```fence``` or surrounding prose by taking
    the outermost `{...}`."""
    if not text or not text.strip():
        raise ValueError("empty model output")
    s = text.strip()
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    obj = json.loads(s[start:end + 1])
    if not isinstance(obj, dict):
        raise ValueError("model output is not a JSON object")
    out = {}
    for k in REQUIRED_KEYS:
        if k not in obj:
            raise ValueError(f"missing key `{k}` in model output")
        v = obj[k]
        out[k] = v if isinstance(v, str) else ("" if v is None else str(v))
    return out


def is_noop(raw_memory, rollout_summary):
    """No-op when both content fields are empty — matches the DB selection
    eligibility (`length(trim(raw_memory)) > 0 OR length(trim(rollout_summary))
    > 0`), so an empty extraction is never selectable for Phase 2."""
    return not (raw_memory.strip() or rollout_summary.strip())


def _templates_dir():
    return hl.plugin_root() / "skills" / "dream-rollouts" / "templates"


def load_templates():
    d = _templates_dir()
    return (d / "stage_one_system.md").read_text(encoding="utf-8"), \
           (d / "stage_one_input.md").read_text(encoding="utf-8")


def render_prompt(system_tmpl, input_tmpl, rollout_path, rollout_cwd, contents):
    """Combine the system + filled input templates into one stdin prompt. Only
    the input template is `.format`-substituted; `contents` is inserted literally
    (its braces are not re-scanned), so code in the digest can't break framing."""
    filled = input_tmpl.format(rollout_path=rollout_path, rollout_cwd=rollout_cwd,
                               rollout_contents=contents)
    return system_tmpl + "\n\n" + filled


def spawn_phase1(prompt, model, timeout=PHASE1_TIMEOUT):
    """Pipe the prompt to a no-tools headless claude (the model can read/write/run
    NOTHING — max injection safety). A neutral temp cwd keeps project CLAUDE.md
    out of the extraction context. Returns stdout; raises on nonzero/timeout/OS
    error so the caller marks the job failed."""
    with tempfile.TemporaryDirectory() as cwd:
        proc = subprocess.run(
            ["claude", "-p", "--model", model, "--allowedTools", ""],
            input=prompt, capture_output=True, text=True,
            cwd=cwd, env=hl.headless_env(), timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p exit {proc.returncode}: {proc.stderr[:300]}")
    return proc.stdout


def _extract_one(conn, root, tid, path, src_ts, token, model, now,
                 spawn, system_tmpl, input_tmpl):
    """Process one claimed rollout end-to-end; never raises (fault isolation —
    one bad rollout must not abort the batch). Marks the job done/no_output or
    failed-with-backoff and returns an outcome dict."""
    try:
        contents = redact_secrets(render_rollout(path))
        if not contents.strip():
            mdb.finish_stage1_job(conn, tid, token, src_ts, now, ok=True)
            return {"thread_id": tid, "outcome": "no_output", "reason": "empty rollout"}
        out = spawn(render_prompt(system_tmpl, input_tmpl, path, root, contents), model)
        parsed = parse_strict_json(out)
        raw = redact_secrets(parsed["raw_memory"]).strip()
        summ = redact_secrets(parsed["rollout_summary"]).strip()
        slug = parsed["rollout_slug"].strip()[:80]
        if is_noop(raw, summ):
            mdb.finish_stage1_job(conn, tid, token, src_ts, now, ok=True)
            return {"thread_id": tid, "outcome": "no_output"}
        mdb.upsert_stage1_output(conn, tid, src_ts, raw, summ, slug, now)
        mdb.finish_stage1_job(conn, tid, token, src_ts, now, ok=True)
        return {"thread_id": tid, "outcome": "saved", "slug": slug,
                "raw_len": len(raw), "summary_len": len(summ)}
    except Exception as exc:  # noqa: BLE001 — per-item fault boundary, recorded
        mdb.finish_stage1_job(conn, tid, token, src_ts, now, ok=False,
                              error=str(exc)[:500])
        return {"thread_id": tid, "outcome": "failed", "error": str(exc)[:200]}


def extract_rollouts(conn, root, claimed, model, now, spawn=spawn_phase1,
                     templates=None):
    """Run Phase-1 extraction over a claimed batch. `spawn`/`templates` are
    injectable so the deterministic path is unit-testable without a live model."""
    system_tmpl, input_tmpl = templates or load_templates()
    return [_extract_one(conn, root, tid, path, src_ts, token, model, now,
                         spawn, system_tmpl, input_tmpl)
            for tid, path, src_ts, token in claimed]


def main():
    root = hl.repo_root()
    now = int(time.time())
    model = os.environ.get("HARNESS_DREAM_PHASE1_MODEL", DEFAULT_MODEL)
    conn = mdb.connect(root)
    try:
        rollouts = dd.discover_rollouts(hl.project_transcripts_dir(root), now)
        claimed = dd.claim_rollouts(conn, rollouts, f"dream-{os.getpid()}", now)
        results = extract_rollouts(conn, root, claimed, model, now)
    finally:
        conn.close()
    json.dump({"claimed": len(claimed), "results": results}, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
