"""Step 5: Behaviour graders. Once the skill loads, is the output right?

Steps 3 and 4 tested the skill's `description` (triggering).
This step tests the skill's body, the rules in SKILL.md:
  "Output exactly 3 bullets. Each bullet is 15 words or fewer.
   No intro line, no closing line."
Each rule becomes one small grader. When one fails, you know which rule broke.
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


def skill_not_loaded(run, expected):
    return expected not in run.loaded_skills


# --- NEW in step 5 ----------------------------------------------------------

BULLET_MARKERS = ("- ", "* ", "• ")


def lines(text):
    """Non-empty lines, so a trailing blank line doesn't count as content."""
    return [line.strip() for line in text.strip().splitlines() if line.strip()]


def bullets(text):
    """Bullet lines with the marker removed."""
    return [line[2:] for line in lines(text) if line.startswith(BULLET_MARKERS)]


def bullet_count(run, expected):
    return len(bullets(run.output_text)) == expected


def max_words_per_bullet(run, expected):
    return all(len(b.split()) <= expected for b in bullets(run.output_text))


def first_line_is_bullet(run, expected):
    """Catches an intro line such as "Here is a summary:"."""
    first = lines(run.output_text)[:1]
    return bool(first and first[0].startswith(BULLET_MARKERS)) == expected


RUNS = 3

article = (ROOT / "article.txt").read_text()
case = {
    "id": "behavior-format",
    "prompt": f"Summarize: {article}",
    "expect": [
        (skill_loaded, "tldr"),
        (bullet_count, 3),
        (max_words_per_bullet, 15),
        (first_line_is_bullet, True),
    ],
}

for i in range(RUNS):
    out_path = RESULTS / f"step5-{case['id']}-{i}.jsonl"
    run_claude(case["prompt"], "with-skill", out_path)
    result = parse_run(out_path)
    # print(f"--- output of run {i} ---\n{result.output_text}\n")
    for grader, expected in case["expect"]:
        ok = grader(result, expected)
        print(f"{case['id']} run {i}: {grader.__name__}={expected!r} {'PASS' if ok else 'FAIL'}")
