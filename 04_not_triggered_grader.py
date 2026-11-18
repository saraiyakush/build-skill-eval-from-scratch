"""Step 4: A negative case. The skill must NOT load for the wrong prompt.

A trigger eval that only checks "does it load?" rewards a skill that
loads for everything. A negative case catches that. Together, the
positive and negative cases test the skill's `description`, which is
the only part of SKILL.md Claude reads when deciding whether to load it.
"""
import json
import os
import pathlib
import subprocess
import sys
from dataclasses import dataclass

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


def skill_loaded(run, expected):
    return expected in run.loaded_skills


# --- NEW in step 4 ----------------------------------------------------------

def skill_not_loaded(run, expected):
    return expected not in run.loaded_skills


RUNS = 3   # kept low to save credits while learning; raise it for a real pass rate

article = (ROOT / "article.txt").read_text()
cases = [
    {
        "id": "trigger-paraphrase",
        "prompt": f"What's the gist of this? {article}",
        "grader": skill_loaded,
        "expected": "tldr"
    },
    {
        "id": "trigger-negative",
        "prompt": "Write a poem about autumn",
        "grader": skill_not_loaded,
        "expected": "tldr"
    },
]

for case in cases:
    passed = 0
    for i in range(RUNS):
        out_path = RESULTS / f"step4-{case['id']}-{i}.jsonl"
        run_claude(case["prompt"], "with-skill", out_path)
        ok = case["grader"](parse_run(out_path), case["expected"])
        passed += ok
        print(f"{case['id']} run {i}: {case['grader'].__name__} {'PASS' if ok else 'FAIL'}")
    print(f"  pass rate: {passed}/{RUNS}\n")
