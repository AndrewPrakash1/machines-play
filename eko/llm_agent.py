"""A coding-agent loop: bash, a workspace, and an automatic 'please continue'."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

from eko.memory import episode_summaries, semantic_text
from eko.prompts import BEGIN, CONTINUE, RESET_WARNING, SOUL, SYSTEM_TEMPLATE


BASH_TOOL = {
    "name": "bash",
    "description": "Run a shell command in your workspace. Use curl against the world URL. Timeout stays under 30 seconds.",
    "input_schema": {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
    },
}


def system_prompt(workspace: Path, base_url: str, session: str, name: str) -> str:
    return SYSTEM_TEMPLATE.format(
        name=name,
        workspace=str(workspace),
        base_url=base_url,
        session=session,
        soul=SOUL.strip(),
        semantic=semantic_text(workspace).strip(),
        episodes=episode_summaries(workspace).strip(),
    )


def run_bash(command: str, workspace: Path, timeout: float = 30) -> str:
    env = {key: os.environ[key] for key in ("PATH", "LANG", "TMPDIR", "TERM") if key in os.environ}
    env["HOME"] = str(workspace)
    env["PATH"] = env.get("PATH", "/usr/bin:/bin")
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=min(max(timeout, 1), 30),
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return f"timed out after {timeout:.0f}s\n{exc.stdout or ''}\n{exc.stderr or ''}"
    out = (completed.stdout or "") + (("\n" + completed.stderr) if completed.stderr else "")
    if len(out) > 16000:
        out = out[:16000] + "\n…[truncated]"
    if not out.strip():
        out = f"(exit {completed.returncode}, no output)"
    return out


def _post(url, headers, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read())


def _anthropic(messages, system, model):
    headers = {
        "content-type": "application/json",
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
    }
    return _post(
        "https://api.anthropic.com/v1/messages",
        headers,
        {"model": model, "max_tokens": 4096, "system": system, "tools": [BASH_TOOL], "messages": messages},
    )


def _openai(messages, system, model):
    headers = {"content-type": "application/json", "authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
    tools = [{"type": "function", "function": {"name": "bash", "description": BASH_TOOL["description"], "parameters": BASH_TOOL["input_schema"]}}]
    packed = [{"role": "system", "content": system}, *messages]
    return _post("https://api.openai.com/v1/chat/completions", headers, {"model": model, "messages": packed, "tools": tools})


def _provider():
    choice = os.environ.get("EKO_PROVIDER", "").strip().lower()
    if choice == "anthropic" or (not choice and os.environ.get("ANTHROPIC_API_KEY")):
        return "anthropic", os.environ.get("EKO_MODEL", "claude-sonnet-4-5")
    if choice == "openai" or os.environ.get("OPENAI_API_KEY"):
        return "openai", os.environ.get("EKO_MODEL", "gpt-4.1")
    return None, None


def run_llm(workspace: Path, base_url: str, session: str, name: str, seconds: float, hour_seconds: float, on_hour):
    provider, model = _provider()
    if provider is None:
        raise SystemExit("Set ANTHROPIC_API_KEY or OPENAI_API_KEY, or run with --backend demo.")
    deadline = time.monotonic() + seconds
    hour_index = 0
    while time.monotonic() < deadline:
        system = system_prompt(workspace, base_url, session, name)
        messages = [{"role": "user", "content": BEGIN}]
        hour_deadline = min(deadline, time.monotonic() + hour_seconds)
        warned = hour_seconds < 360
        print(f"hour {hour_index + 1}  model {model}")
        while time.monotonic() < hour_deadline:
            if provider == "anthropic":
                reply = _anthropic(messages, system, model)
                blocks = reply.get("content") or []
                messages.append({"role": "assistant", "content": blocks})
                tools = [block for block in blocks if block.get("type") == "tool_use"]
                texts = [block.get("text", "") for block in blocks if block.get("type") == "text" and block.get("text")]
                if texts:
                    print("eko:", " ".join(texts)[:400])
                if tools:
                    results = []
                    for tool in tools:
                        command = (tool.get("input") or {}).get("command", "")
                        print("$", command[:180])
                        results.append({"type": "tool_result", "tool_use_id": tool.get("id"), "content": run_bash(command, workspace)})
                    messages.append({"role": "user", "content": results})
                    continue
            else:
                reply = _openai(messages, system, model)
                choice = reply["choices"][0]["message"]
                messages.append(choice)
                calls = choice.get("tool_calls") or []
                if choice.get("content"):
                    print("eko:", str(choice["content"])[:400])
                if calls:
                    for call in calls:
                        command = json.loads(call["function"]["arguments"]).get("command", "")
                        print("$", command[:180])
                        messages.append({"role": "tool", "tool_call_id": call["id"], "content": run_bash(command, workspace)})
                    continue
            remaining = hour_deadline - time.monotonic()
            if remaining <= 0:
                break
            if (not warned) and remaining < 300:
                messages.append({"role": "user", "content": RESET_WARNING})
                warned = True
            else:
                messages.append({"role": "user", "content": CONTINUE})
        hour_index += 1
        if time.monotonic() >= deadline:
            break
        on_hour()
        print("the island resets. the workspace stays.")
