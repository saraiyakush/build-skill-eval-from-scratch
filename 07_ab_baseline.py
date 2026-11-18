"""Step 7: A/B baseline. Does the skill earn its place?

A skill that passes its evals might still be useless if Claude does
just as well without it. So every case also runs in `without-skill/`,
a folder with no skills installed, and we compare the two.

Graders named `skill_*` are skipped for `without-skill`: the skill
cannot load there, so those checks would pass or fail trivially.

Usage:  python 07_ab_baseline.py [runs]
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


# --- NEW in step 7 ----------------------------------------------------------

CONFIGS = ["with-skill", "without-skill"]   # the A and B of the A/B test


def applies(grader_name, config):
    return not (config == "without-skill" and grader_name.startswith("skill_"))

DEFAULT_RUNS = 3
article = (ROOT / "article.txt").read_text()

for case in load_suite(ROOT / "tldr-skill-tests.yaml"):
    prompt = case["prompt"].replace("{article}", article)
    for config in CONFIGS:
        if not any(applies(name, config) for name in case["expect"]):
            continue   # e.g. trigger cases: nothing to check without the skill
        for i in range(case.get("runs", DEFAULT_RUNS)):
            out_path = RESULTS / f"{config}-{case['id']}-{i}.jsonl"
            run_claude(prompt, config, out_path)
            result = parse_run(out_path)
            for name, expected in case["expect"].items():
                if applies(name, config):
                    ok = GRADERS[name](result, expected)
                    print(f"{config:13} {case['id']} run {i}: {name} {'PASS' if ok else 'FAIL'}")
