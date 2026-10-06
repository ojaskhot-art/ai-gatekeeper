"""AI Gatekeeper: reviews the latest git diff, rates risk, writes release notes."""
import html
import json
import os
import subprocess
import sys
import time

import requests

API_KEY = os.environ.get("GEMINI_API_KEY")
# If this model name is rejected, copy a current one from https://aistudio.google.com
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
MAX_CHARS = 15000

PROMPT = """You are a strict senior code reviewer and DevSecOps engineer.
Review the git diff below. Respond ONLY with JSON in this exact shape:
{
  "risk": "Low" | "Medium" | "High",
  "summary": "one sentence",
  "issues": [{"severity": "Low|Medium|High", "file": "name", "problem": "...", "fix": "..."}],
  "release_notes": ["user-friendly bullet", "..."]
}
Rules:
- Rate High if there are hardcoded secrets, injection flaws, or serious bugs.
  Rate Low only if the change is clean.
- Also check for logic bugs such as division by zero, missing input validation
  and missing error handling. List every issue as a separate item, even in the same file.
- release_notes must describe ONLY what the diff actually adds, changes or removes.
  Never describe the fixes you recommend as if they were already done.
- If risk is High, the first release note must be: "BLOCKED: not safe to release, see issues."

DIFF:
"""


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout


def get_diff():
    code, out = run(["git", "diff", "HEAD~1", "HEAD"])
    if code != 0 or not out.strip():  # shallow clone or first commit
        code, out = run(["git", "show", "HEAD"])
    return out[:MAX_CHARS]


class ApiError(Exception):
    pass


def model_list():
    wanted = [MODEL, "gemini-3.1-flash-lite", "gemini-3.5-flash"]
    seen = []
    for m in wanted:
        if m and m not in seen:
            seen.append(m)
    return seen


def call_ai(diff):
    body = {
        "contents": [{"parts": [{"text": PROMPT + diff}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
    }
    last = "no attempt made"
    for model in model_list():
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(1, 4):
            try:
                r = requests.post(url, json=body, headers={"x-goog-api-key": API_KEY}, timeout=90)
            except requests.RequestException as e:
                last = f"{model}: network error {e}"
                print(f"[retry] {last}")
                time.sleep(5 * attempt)
                continue
            if r.status_code in (429, 500, 503):
                last = f"{model}: HTTP {r.status_code} (busy/rate limited)"
                print(f"[retry] {last}, attempt {attempt}/3")
                time.sleep(10 * attempt)
                continue
            if r.status_code != 200:
                last = f"{model}: HTTP {r.status_code} {r.text[:200]}"
                print(f"[skip] {last}")
                break  # try the next model
            try:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                text = text.strip().removeprefix("```json").removesuffix("```").strip()
                print(f"Model used: {model}")
                return json.loads(text)
            except (KeyError, IndexError, ValueError) as e:
                last = f"{model}: bad response ({e})"
                print(f"[retry] {last}")
    raise ApiError(last)


def write_report(d):
    colors = {"Low": "#2e7d32", "Medium": "#ef6c00", "High": "#c62828"}
    risk = d.get("risk", "Medium")
    rows = "".join(
        f"<tr><td>{html.escape(i.get('severity',''))}</td><td>{html.escape(i.get('file',''))}</td>"
        f"<td>{html.escape(i.get('problem',''))}</td><td>{html.escape(i.get('fix',''))}</td></tr>"
        for i in d.get("issues", [])
    )
    notes = "".join(f"<li>{html.escape(n)}</li>" for n in d.get("release_notes", []))
    page = f"""<html><body style="font-family:Arial;margin:30px">
<h1>AI Gatekeeper Report</h1>
<h2>Risk: <span style="color:{colors.get(risk,'#000')}">{risk}</span></h2>
<p>{html.escape(d.get('summary',''))}</p>
<h3>Issues found</h3>
<table border="1" cellpadding="6" style="border-collapse:collapse">
<tr><th>Severity</th><th>File</th><th>Problem</th><th>Suggested fix</th></tr>{rows}</table>
<h3>Release notes</h3><ul>{notes}</ul></body></html>"""
    with open("review.html", "w", encoding="utf-8") as f:
        f.write(page)
    with open("RELEASE_NOTES.md", "w", encoding="utf-8") as f:
        f.write("# Release Notes\n\n" + "\n".join(f"- {n}" for n in d.get("release_notes", [])) + "\n")


def main():
    if not API_KEY:
        print("ERROR: GEMINI_API_KEY not set")
        sys.exit(2)
    start = time.time()
    diff = get_diff()
    if not diff.strip():
        print("No diff found, skipping review")
        return
    try:
        result = call_ai(diff)
    except ApiError as e:
        print(f"AI SERVICE UNAVAILABLE (not a code problem): {e}")
        sys.exit(2)
    write_report(result)
    print(f"AI review finished in {time.time() - start:.1f}s")
    print(f"RISK: {result.get('risk')}  |  {result.get('summary')}")
    for i in result.get("issues", []):
        print(f" - [{i.get('severity')}] {i.get('file')}: {i.get('problem')}")
    if result.get("risk") == "High":
        print("GATE FAILED: High risk change blocked by AI Gatekeeper")
        sys.exit(1)
    print("GATE PASSED")


if __name__ == "__main__":
    main()