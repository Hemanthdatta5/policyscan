# Starting PolicyScan in Claude Code

## 1. Set up the folder

1. Make a new folder, for example `policyscan`.
2. Put `CLAUDE.md` in it (Claude Code reads it automatically).
3. Make a `demo` folder inside it and put `policyscan.html` there (the front-end prototype).
4. Optional: download the OPP-115 corpus from https://usableprivacy.org/data and unzip it into `data/raw/`. If you skip this, Claude Code will tell you when it needs it.

## 2. Open Claude Code in that folder

Open the folder in Claude Code (terminal: `cd policyscan` then `claude`, or the Code tab in the desktop app).

## 3. Paste this first prompt

```
Read CLAUDE.md. We're building the full PolicyScan app it describes.

Before writing code:
1. Ask me which front end to use (FastAPI-served page like demo/policyscan.html, Streamlit, or React).
2. Check what's installed (Python version, Docker, git) and tell me what's missing.
3. Propose a step-by-step plan that follows the milestones in CLAUDE.md, with a test I can run at the end of each step.

Then start with Stage 1: project skeleton, config, the SSRF-safe policy fetcher, the segmenter, the rules layer, and the scorer, each with offline tests. Initialize a git repo and commit after each working step.
```

## 4. Prompts for later steps

- "Build the OPP-115 loader and category map, train the baseline classifier, and write the evaluation report to docs/model-evaluation.md."
- "Write the DistilBERT fine-tuning script so it runs on Google Colab, and give me a notebook to run it."
- "Build the Playwright tracker audit worker in Docker and the comparison against the policy. Test it on 3 real sites."
- "Build the web UI and connect it to the API. Make it look like demo/policyscan.html."
- "Add login and saved reports."
- "Write the STRIDE threat model, run Bandit, pip-audit and an OWASP ZAP baseline scan, fix what they find, and write docs/security-report.md."
- "Run the case study on these 20 sites and compare against ToS;DR: <list sites>."

## Tips

- Use plan mode (Shift+Tab in the terminal) for big steps so you can approve the plan first.
- Ask Claude Code to commit after each working step so you can roll back.
- Share the repo on GitHub with your two teammates once Stage 1 works.
