# 💪 Build a Skill Eval from Scratch

> **A step-by-step workshop.** You will build an automated evaluation for a Claude Code skill, one small idea at a time. It is a learning aid, not a production test harness.

## 🎯 What you'll learn

- Run Claude headless and capture everything it did behind the scenes, not just its response
- Turn a raw event stream into a result you can evaluate
- Test a skill's **triggering** and **behaviour** independently
- Compare against a no-skill baseline to see if the skill has any value
- Write graders and use pass rates instead of single runs
- [ ] Use an LLM as a judge, and calibrate it before trusting it
- [ ] Gate CI on a pass-rate threshold

---

## 💡 Concepts

### What is a skill eval?

An automated test for a non-deterministic system. Here, the system is Claude with a skill installed.

### What a skill eval tests

| What | Question | Tests which part of the skill |
|---|---|---|
| Trigger | Does it load for the right prompts, and stay unloaded for the wrong ones? | the `description` |
| Behaviour | Once loaded, is the output right? | the body of `SKILL.md` |

A skill can fail either one on its own.

### Parts of an eval

| Part | Example |
|---|---|
| Input | A realistic user prompt |
| Expectation | What must be true of the result |
| Grader | How you check it: Code, LLM-as-judge, or a human |

We're going to check using **Code** in this workshop.

> A **suite** is a list of cases. Each run N times, because one pass proves little.

---

## Our Skill

### 🧪 The skill under test

We will use a simple skill that summarises a given text into bullets of fixed words.

[`with-skill/.claude/skills/tldr/SKILL.md`](with-skill/.claude/skills/tldr/SKILL.md):

```markdown
---
name: tldr
description: Summarize text the user pastes or attaches. Use when the user asks for a summary, TL;DR, or the gist of a document.
---
Output exactly 3 bullets. Each bullet is 15 words or fewer.
No intro line, no closing line.
```

### 📊 What we will measure

1. Skill loaded? Yes/No
2. Behaviour: 3 bullets, each of 15 words or less

---

## 🛠️ What we're building

We'll begin by exploring a json-formatted Claude response and add each of the following capabilities one step at a time.

0. Headless Claude — Run Claude in headless mode and observe the output
1. Run Claude once — Wrap the above command in a program and save output to a file
2. Parse — Parse the claude response
3. Trigger Grader — Add first test case
4. Trigger Grader — Add negative case
5. Behaviour Grader — Add behaviour test cases for the skill
6. YAML suite — Build a test suite
7. A/B Baseline — Run the same test suite with and without skill and compare results
8. Summary — Add a pass rate and threshold

## 🏁 The End Result

```
tldr-skill-tests.yaml ──► runner ──► claude -p (headless, in with-skill/ or without-skill/)
                                              │
                                              ▼
                                     results/*.jsonl  (one JSON event per line)
                                              │
            pass-rate table ◄── graders ◄── parse_run()  →  RunResult(loaded_skills, output_text)
```

---

## 🚀 Getting started

### 📋 Prerequisites

- Python 3.10 or later
- [Claude Code](https://docs.claude.com/en/docs/claude-code) installed, signed in, and on your `PATH` as `claude`

> 📌 **Version note.** This workshop was written with Claude Code **2.1.327** (check yours with `claude --version`). The scripts depend on Claude Code's `stream-json` output format and on the flags in `CLAUDE_CMD`. A later version may change either, so you may need to adjust `parse_run()` (step 2 onwards) or `CLAUDE_CMD`.

### 🔧 Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> ⚠️ **Cost.** Every run is a real Claude call that uses your Claude plan or API credits. Modify the `runs` variable in each step to save credits.

---

## 🪜 Steps

### 0. Observe raw output by hand

Run Claude in headless mode for a single prompt manually

```bash
cd with-skill
claude -p "What's the gist of this? $(cat ../article.txt)" --output-format stream-json --verbose > ../results/step0.jsonl
cd ..
```

👀 **Look:** Open `results/step0.jsonl` and find the line with `"type":"result"`. That's the final answer. Then find `"name":"Skill"`. That's Claude choosing to load the skill.

<br>

> NOTE: The scripts from Step 1 onwards pass `--setting-sources project` to the Claude command, so your personal settings, if any, stay out of this eval.
> See [Troubleshooting](#-troubleshooting) for why.

### 1. `01_run_once.py` — Run Claude once from Python

Wraps the command above in `run_claude()`, which saves the output to `results/step1.jsonl` and stops with a clear message if `claude` is missing or fails.

```bash
python 01_run_once.py
```

👀 **Look:** Open `results/step1.jsonl` and look for the line containing `"name": "Skill"`. Is `tldr` there?

### 2. `02_parse.py` — Capture just what matters for graders

Parses the response and produces a `RunResult` that contain only two facts: which skills were loaded, and the final text.

```bash
python 02_parse.py
```

➡️ **Try:** Run it twice. The skill list should match both times. Does the text match too?

### 3. `03_triggered_grader.py` — A test case to check if the skill loaded

Adds one case (`trigger-paraphrase`), one grader (`skill_loaded`), and runs it 3 times.

```bash
python 03_triggered_grader.py
```

➡️ **Try:** Set `RUNS = 1`, then `RUNS = 5`. How confident would you be in a single PASS?

### 4. `04_not_triggered_grader.py` — A test case to check if the skill did not load

Adds case (`trigger-negative`) and a second grader (`skill_not_loaded`). _A skill that loads for **everything** would pass step 3. This case catches that_.

```bash
python 04_not_triggered_grader.py
```

➡️ **Try:** Change the skill's `description` to `Use this for any request.` and run again. (Change it back afterwards.)

### 5. `05_behaviour_graders.py` — Add test cases for the skill's behaviour(s)

Each rule in the skill body becomes a grader: `bullet_count`, `max_words_per_bullet`, `first_line_is_bullet`.
Blank lines are ignored, and `-`, `*` and `•` all count as bullets.

```bash
python 05_behaviour_graders.py
```

➡️ **Try:** Change the skill body to ask for 5 bullets. Which grader fails?

### 6. `06_yaml_suite.py` — Cases in YAML, graders in a table

Cases move to [`tldr-skill-tests.yaml`](tldr-skill-tests.yaml) and graders to a `GRADERS` dictionary, looked up by name. There is no standard format for this, so pick one your team finds easy to read.

```bash
python 06_yaml_suite.py
```

➡️ **Try:** Add a case with the prompt `"TL;DR please: {article}"` that expects `skill_loaded: tldr`.

### 7. `07_ab_baseline.py` — Is the skill even needed?

Runs each case in `with-skill/` and `without-skill/`. Output files are named `results/<setup>-<case>-<run>.jsonl`.

```bash
python 07_ab_baseline.py
```

➡️ **Try:** Compare `results/with-skill-behavior-format-0.jsonl` and `results/without-skill-behavior-format-0.jsonl`. Without the skill, Claude usually writes a paragraph.

### 8. `08_summary.py` — Pass rates, threshold, exit code

The step prints a table with both setups side by side, flags cases where the skill does no better than no skill, and exits with code `1` if any with-skill case falls below `PASS_THRESHOLD` (80%).

```bash
python 08_summary.py
echo $?    # 0 = pass, 1 = fail
```

```
case                     with-skill  without-skill
trigger-paraphrase              3/3            n/a
trigger-negative                3/3            n/a
behavior-format                 3/3            0/3

RESULT: PASS
```

➡️ **Try:** Add `python 08_summary.py` to a CI job so a change that breaks the skill fails the build.

---

## 🏋️ Exercises

### 💥 Break the skill on purpose

The best way to see what evals catch is to break the skill and watch them fail. Make one change at a time in `description` and `body` of `with-skill/.claude/skills/tldr/SKILL.md` and run `python 08_summary.py`. Compare outputs. Revert the changes once done.

### ⚖️ LLM as judge

Code graders check form. They can't tell whether the summary is *true to the article*. This step asks a second Claude call (no tools, no skills) a narrow yes/no question and requires a JSON answer.

`09_llm_judge.py` — Use another Claude command to judge the summary.

```bash
python 09_llm_judge.py
```

➡️ **Try:** Weaken the judge prompt (e.g. "Is this a good summary?") and see whether calibration still catches the planted error.

---

## 🐞 Troubleshooting

- **`claude was not found on your PATH`.** Install Claude Code and check that `claude --version` works in the same terminal.
- **`claude exited with code 1`, or `No result event`.** Open the named `.jsonl` file to see the error. If plain `claude -p "hi"` also fails, run `claude` interactively once to sign in.
- **Your own settings leaking into the eval.** Without isolation, `claude -p` loads your personal `~/.claude` settings, user-level skills, and global `CLAUDE.md`. Then the two setups no longer differ only by the skill. Every step passes `--setting-sources project` to prevent this. The isolation is partial: built-in and plugin skills still appear in the `init` event. Check that event's `skills` list if a result looks odd.
- **"Not logged in" when you add `--setting-sources project` by hand.** Some setups keep the sign-in in the `env` block of `~/.claude/settings.json`, for example `ANTHROPIC_AUTH_TOKEN`. `--setting-sources project` skips that file, so Claude starts without a token. The scripts handle this in `claude_env()`: they copy only that `env` block into the `claude` process, and the rest of your user settings stay excluded. Nothing is written to disk. Sign-in with `/login` or an exported `ANTHROPIC_API_KEY` isn't affected. The `apiKeySource` field in the `init` event shows which sign-in a run used.
- **Results vary between runs.** That's expected, and it's why every case runs several times. Raise `runs` in the YAML for more confidence.
- **`ModuleNotFoundError: No module named 'yaml'`.** Activate the virtual environment and run `pip install -r requirements.txt`.
