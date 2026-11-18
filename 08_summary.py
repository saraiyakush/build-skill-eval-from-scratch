"""Step 8: Pass rates, a threshold, and an exit code.

Lines of PASS/FAIL are hard to read and impossible to automate.
This step:
  - counts a run as passed only if every grader for it passed
  - prints a pass-rate table, with-skill next to without-skill
  - flags cases where the skill does no better than no skill
  - exits with code 1 if any with-skill case is below PASS_THRESHOLD,
    so CI can block a change that breaks the skill

Usage:  python 08_summary.py [runs]
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


# --- carried over from step 7 -----------------------------------------------

CONFIGS = ["with-skill", "without-skill"]


def applies(grader_name, config):
    return not (config == "without-skill" and grader_name.startswith("skill_"))

DEFAULT_RUNS = 3
# --- NEW in step 8 ----------------------------------------------------------

PASS_THRESHOLD = 0.8   # with 3 runs, this means 3/3; try 0.6 to allow one miss


def run_suite(cases, article):
    """Run every case and return {(case_id, config): [True/False per run]}."""
    outcomes = {}
    for case in cases:
        prompt = case["prompt"].replace("{article}", article)
        for config in CONFIGS:
            graders = [(n, v) for n, v in case["expect"].items() if applies(n, config)]
            if not graders:
                continue   # e.g. trigger cases: nothing to check without the skill
            for i in range(case.get("runs", DEFAULT_RUNS)):
                out_path = RESULTS / f"{config}-{case['id']}-{i}.jsonl"
                run_claude(prompt, config, out_path)
                result = parse_run(out_path)
                failed = [n for n, v in graders if not GRADERS[n](result, v)]
                outcomes.setdefault((case["id"], config), []).append(not failed)
                status = "PASS" if not failed else "FAIL (" + ", ".join(failed) + ")"
                print(f"{config:13} {case['id']} run {i}: {status}")
    return outcomes


def summarize(cases, outcomes, threshold=PASS_THRESHOLD):
    """Print the pass-rate table and return the process exit code."""
    def rate(case_id, config):
        runs = outcomes.get((case_id, config))
        return (sum(runs) / len(runs), f"{sum(runs)}/{len(runs)}") if runs else (None, "n/a")

    print(f"\n{'case':22} {'with-skill':>12} {'without-skill':>14}")
    exit_code = 0
    for case in cases:
        with_rate, with_text = rate(case["id"], "with-skill")
        base_rate, base_text = rate(case["id"], "without-skill")
        notes = []
        if with_rate is not None and with_rate < threshold:
            notes.append(f"below threshold {threshold:.0%}")
            exit_code = 1
        if base_rate is not None and with_rate is not None and with_rate <= base_rate:
            notes.append("skill adds no value here")
        print(f"{case['id']:22} {with_text:>12} {base_text:>14}  {'; '.join(notes)}")

    print("\nRESULT:", "PASS" if exit_code == 0 else "FAIL")
    return exit_code


if __name__ == "__main__":
    cases = load_suite(ROOT / "tldr-skill-tests.yaml")
    outcomes = run_suite(cases, (ROOT / "article.txt").read_text())
    sys.exit(summarize(cases, outcomes))
