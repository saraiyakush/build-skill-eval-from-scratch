"""Step 1: Run Claude once, headless, and save everything it did.

An eval needs a record of what the agent did, not just what it said.
`claude -p` runs one prompt without the interactive UI, and
`--output-format stream-json` writes one JSON event per line:
the session setup, every tool call, and the final answer.
"""
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

CLAUDE_CMD = [
    "claude",
    "--output-format", "stream-json", "--verbose",  # one JSON event per line
    "--setting-sources", "project",  # ignore your personal ~/.claude settings and skills
    "--no-session-persistence",      # don't save eval runs to your session history
    "-p",                            # headless: run one prompt and exit
]


def claude_env():
    """Your environment plus the `env` block of ~/.claude/settings.json.

    `--setting-sources project` skips your user settings, so their `env`
    block is skipped too. If that block holds your sign-in (for example
    ANTHROPIC_AUTH_TOKEN), claude would report "Not logged in".

    Copy just that block back in.
    """
    env = dict(os.environ)
    user_settings = pathlib.Path.home() / ".claude" / "settings.json"
    try:
        env.update({k: str(v) for k, v in json.loads(user_settings.read_text()).get("env", {}).items()})
    except (FileNotFoundError, json.JSONDecodeError):
        pass   # no user settings: nothing to copy
    return env


def run_claude(prompt, config, out_path):
    """Run Claude inside the `config` folder and save its stream-json output."""
    try:
        with open(out_path, "w") as out:
            proc = subprocess.run(CLAUDE_CMD + [prompt], cwd=ROOT / config,
                                  stdin=subprocess.DEVNULL, stdout=out, env=claude_env())
    except FileNotFoundError:
        sys.exit("`claude` was not found on your PATH. Install Claude Code first.")
    if proc.returncode != 0:
        sys.exit(f"claude exited with code {proc.returncode}. "
                 f"Check {out_path}. If it says \"Not logged in\", see Troubleshooting in the README.")


article = (ROOT / "article.txt").read_text()
prompt = f"What's the gist of this? {article}"

out_path = RESULTS / "step1.jsonl"
run_claude(prompt, "with-skill", out_path)
