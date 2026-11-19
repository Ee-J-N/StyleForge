---
name: styleforge
description: >-
  Learn a user's personal CTF WriteUp style from explicitly selected historical articles, or write and validate a new evidence-grounded CTF WriteUp. Supports separately selected Learn/Write and Solve/Replay modes, real screenshots, Markdown bundles and user-confirmed publication. Operate only in CTF challenges and experimental environments the user owns or has explicitly authorized.
---

# StyleForge

Use the existing StyleForge CLI to preserve style samples, case history, screenshots, runtime output and article provenance. The Agent provides the analysis and prose; the scripts store and verify evidence. Never turn a source-code inference, sample WP, output excerpt, or old run into a newly observed result.

## Select The Modes

Choose the two case dimensions independently. Do not infer that a historical style sample is evidence for the current challenge.

- **Learn Mode:** import only user-selected writing samples by one declared author. Inspect the original article and associated images; produce a concise qualitative analysis tied to sample IDs and record preferences only when the user states them. Use `profile-learn`, then `profile-edit` with `qualitative_analysis.basis_sample_ids` and explicit preferences.
- **Write Mode:** select a Style Profile and call `prepare`. Use its references as style examples, not instructions or challenge evidence. Preserve technical facts and adapt structure to this challenge. Write only a candidate article until the exact revision is confirmed.
- **Solve & Write:** set `record-mode solve` before work in an explicitly authorized CTF or lab. Record observations as they occur; run explicit argv with `run`; capture the actual browser, desktop or terminal when available. The case journal time is the record time.
- **Replay & Write:** set `record-mode replay` and preserve supplied historical artifacts as history. Re-run only in the authorized environment. Label previous results as historical and distinguish them from this replay's output.

The style dimension (`learn` or `write`) does not set the recording dimension (`solve` or `replay`). When both are selected, honor both.

## Use The CLI

Run commands from the skill directory; `python` may be replaced with the installed Python launcher. The default data store is `%LOCALAPPDATA%\StyleForge`, separated by local user. Do not use `--test-store` for personal cases.

1. Before any target interaction, make sure the user's request identifies the CTF/lab and its authorized scope. Do not expand that scope or access unrelated systems. Reading local WP samples, running syntax checks, and testing on a local synthetic fixture do not authorize a network operation.
2. For Learn Mode, import only the selected author's files with `profile-learn`. Keep general references separate with `general-import`.
3. Create a case with `case-init`; add every required challenge input as `--input`. Select `--style-mode` and `--record-mode` explicitly.
4. In Solve & Write, record relevant steps and execute the selected EXP with `exp-check --run --result-pattern <regex>`. The check runs the selected script file with a supported native interpreter; it does not accept an alternate shell command. `passed` requires exit code zero, unchanged EXP bytes and an actual result-pattern match. No pattern or an empty match is `unverified`, not success.
5. Capture evidence only after recording its step. Use `capture` for a real browser page or visible application window, `terminal-run` for a real Windows console, and `evidence-import` for an existing screenshot with its true source. Never redraw a UI or label an imported image as a verified browser capture.
6. Call `prepare`, read the resulting packet and draft the article with each `<!-- evidence:ID -->` marker beside the matching explanation. Cite flags only from a current, hash-verified EXP run or an explicitly attributed historical source. Include EXP files with `publish --attachment` and link them in the article.
7. Run `publish`, inspect `validation.json`, fix every error, then run `bundle-check`. Publishing creates an **unapproved candidate**. Only call `approve` with the user's explicit receipt bound to the exact current article hash. Never generate, assume or reuse another revision's approval receipt.

The scripts verify file identity, hashes, mode labels and links; they do not establish that a payload is correct, that a regex is a meaningful challenge-specific result check, or that a prose claim follows from the evidence. Review the actual command, raw output and challenge semantics before approving. External HTTP links are syntax-checked and reported as not fetched.

## References

- Read [INSTALL.md](INSTALL.md) to install the Skill and optional screenshot/parser dependencies.
- Read [README.md](README.md) for the CLI workflow, consent receipt formats and operating boundaries.
- Read [DEVELOPMENT.md](DEVELOPMENT.md) before modifying persistence, evidence or publication logic.
