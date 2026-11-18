"""Step 3: The first eval case, the first grader, and a pass rate.

An eval case has three parts:
  - input:       a realistic user prompt
  - expectation: what must be true of the result
  - grader:      code that checks the expectation and returns True/False

Model output is non-deterministic, so one pass proves little.
We run the same case N times and report a pass rate.
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


# --- NEW in step 3 ----------------------------------------------------------

def skill_loaded(run, expected):
    return expected in run.loaded_skills


RUNS = 3   # try 1, then 5: how much does one run tell you?

article = (ROOT / "article.txt").read_text()
case = {
    "id": "trigger-paraphrase",
    "prompt": f"What's the gist of this? {article}",
    "expect_skill": "tldr",
}

passed = 0
for i in range(RUNS):
    out_path = RESULTS / f"step3-{case['id']}-{i}.jsonl"
    run_claude(case["prompt"], "with-skill", out_path)
    ok = skill_loaded(parse_run(out_path), case["expect_skill"])
    passed += ok
    print(f"{case['id']} run {i}: skill_loaded {'PASS' if ok else 'FAIL'}")

print(f"\nPass rate: {passed}/{RUNS} ({passed / RUNS:.0%})")
