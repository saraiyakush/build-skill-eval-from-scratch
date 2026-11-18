"""Step 9 (optional): An LLM-as-judge grader.

Code graders check form: bullet count, word count. They cannot tell
whether a summary is *true to the article*. For that, we ask a second
model to judge, with a narrow yes/no question and a required JSON answer.

A judge is itself non-deterministic and can be wrong, so before trusting
it we calibrate it: feed it a summary with a planted false claim and
confirm it fails that summary. If the judge can't catch a planted error,
its PASS on real output means nothing.

The judge runs with no tools and no skills, in the without-skill folder.

Usage:  python 09_llm_judge.py [runs]
"""
import json
import os
import pathlib
import subprocess
import sys
from dataclasses import dataclass

import yaml

ROOT = pathlib.Path(__file__).parent
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

CLAUDE_CMD = [
    "claude",
    "--output-format", "stream-json", "--verbose",
    "--setting-sources", "project",
    "--no-session-persistence",
    "-p",
]


def claude_env():
    """Your environment plus the `env` block of ~/.claude/settings.json.

    `--setting-sources project` skips your user settings, so their `env`
    block is skipped too. If that block holds your sign-in (for example
    ANTHROPIC_AUTH_TOKEN and ANTHROPIC_BASE_URL for a company gateway),
    claude would report "Not logged in". Copy just that block back in.
    """
    env = dict(os.environ)
    user_settings = pathlib.Path.home() / ".claude" / "settings.json"
    try:
        env.update({k: str(v) for k, v in json.loads(user_settings.read_text()).get("env", {}).items()})
    except (FileNotFoundError, json.JSONDecodeError):
        pass   # no user settings: nothing to copy
    return env


def run_claude(prompt, config, out_path):
    try:
        with open(out_path, "w") as out:
            proc = subprocess.run(CLAUDE_CMD + [prompt], cwd=ROOT / config,
                                  stdin=subprocess.DEVNULL, stdout=out, env=claude_env())
    except FileNotFoundError:
        sys.exit("`claude` was not found on your PATH. Install Claude Code first.")
    if proc.returncode != 0:
        sys.exit(f"claude exited with code {proc.returncode}. "
                 f"Check {out_path}. If it says \"Not logged in\", see Troubleshooting in the README.")


@dataclass
class RunResult:
    loaded_skills: list[str]
    output_text: str


def parse_run(path):
    events = [json.loads(line) for line in open(path) if line.strip()]
    skills = [block["input"]["skill"]
              for event in events if event.get("type") == "assistant"
              for block in event["message"]["content"]
              if block["type"] == "tool_use" and block["name"] == "Skill"]
    final = next((e for e in events if e.get("type") == "result"), None)
    if final is None:
        sys.exit(f"No `result` event in {path}. The run did not finish; open the file to see why.")
    return RunResult(skills, final.get("result", ""))


BULLET_MARKERS = ("- ", "* ", "• ")


def lines(text):
    return [line.strip() for line in text.strip().splitlines() if line.strip()]


def bullets(text):
    return [line[2:] for line in lines(text) if line.startswith(BULLET_MARKERS)]


GRADERS = {
    "skill_loaded":         lambda run, expected: expected in run.loaded_skills,
    "skill_not_loaded":     lambda run, expected: expected not in run.loaded_skills,
    "bullet_count":         lambda run, expected: len(bullets(run.output_text)) == expected,
    "max_words_per_bullet": lambda run, expected: all(len(b.split()) <= expected
                                                      for b in bullets(run.output_text)),
    "first_line_is_bullet": lambda run, expected: bool(lines(run.output_text)[:1]
                                                       and lines(run.output_text)[0].startswith(BULLET_MARKERS)) == expected,
}


def load_suite(path):
    cases = yaml.safe_load(open(path))
    for case in cases:
        unknown = set(case["expect"]) - set(GRADERS)
        if unknown:
            sys.exit(f"Case {case['id']!r} uses unknown grader(s): {', '.join(sorted(unknown))}")
    return cases

DEFAULT_RUNS = 3
# --- NEW in step 9 ----------------------------------------------------------

import re

JUDGE_CMD = [
    "claude",
    "--output-format", "json",       # a single JSON object, enough for a judge
    "--setting-sources", "project",
    "--no-session-persistence",
    "--tools", "",                   # the judge only reads and answers
    "-p",
]

JUDGE_PROMPT = """You are grading a summary for faithfulness.

<article>
{article}
</article>

<summary>
{summary}
</summary>

Does the summary state anything that the article does not support?
Reply with only this JSON and nothing else:
{{"faithful": true or false, "reason": "<one sentence>"}}"""


def judge_faithful(summary, article):
    """Return (passed, reason) from the judge model."""
    proc = subprocess.run(JUDGE_CMD + [JUDGE_PROMPT.format(article=article, summary=summary)],
                          cwd=ROOT / "without-skill", stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, env=claude_env())
    if proc.returncode != 0:
        sys.exit(f"Judge call failed (exit {proc.returncode}): {proc.stderr.strip()}")
    answer = json.loads(proc.stdout).get("result", "")
    match = re.search(r"\{.*\}", answer, re.S)    # tolerate stray text around the JSON
    if not match:
        return False, f"judge did not return JSON: {answer[:100]!r}"
    verdict = json.loads(match.group(0))
    return verdict.get("faithful") is True, verdict.get("reason", "")


PLANTED_ERROR = ("- A payments team added a dollar-to-rupee converter and listed 12 checks for it.\n"
                 "- Running all 252 checks by hand took about three hours.\n"   # false: three hours was for 12 checks
                 "- Unit tests ran every check in seconds as more currencies were added.")

if __name__ == "__main__":
    article = (ROOT / "article.txt").read_text()

    print("Calibrating the judge with a planted false claim...")
    ok, reason = judge_faithful(PLANTED_ERROR, article)
    print(f"  judge said faithful={ok}: {reason}")
    if ok:
        sys.exit("The judge missed a planted error, so its verdicts can't be trusted. Fix the judge prompt.")
    print("  judge caught it. Now judging real output.\n")

    case = next(c for c in load_suite(ROOT / "tldr-skill-tests.yaml") if c["id"] == "behavior-format")
    prompt = case["prompt"].replace("{article}", article)
    passed = 0
    runs = case.get("runs", DEFAULT_RUNS)
    for i in range(runs):
        out_path = RESULTS / f"step9-{case['id']}-{i}.jsonl"
        run_claude(prompt, "with-skill", out_path)
        summary = parse_run(out_path).output_text
        ok, reason = judge_faithful(summary, article)
        passed += ok
        print(f"{case['id']} run {i}: judge_faithful {'PASS' if ok else 'FAIL'} ({reason})")
    print(f"\nPass rate: {passed}/{runs}")
    sys.exit(0 if passed == runs else 1)
