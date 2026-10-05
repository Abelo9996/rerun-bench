# Security policy

rerun-bench runs coding agents on task workspaces and executes each task's verifier, so anything that lets a task, an agent or a result file reach outside its temporary workspace is a security issue.

## Reporting

Report privately through GitHub: open the [Security tab](https://github.com/Abelo9996/rerun-bench/security) and choose "Report a vulnerability". Please do not open a public issue.

Include the rerun-bench version or commit, your OS and Python version, the command you ran, and what happened.

You can expect an acknowledgement within 7 days.

## In scope

- A task, agent run or verifier that reads or writes files outside its temporary workspace and the results directory
- A real agent run that starts without the cost estimate and `--yes`
- Reports that include prompts, file contents or paths beyond what the docs describe

## Supported versions

Only the latest release and `main` receive fixes while the project is at 0.x.

## Privacy

rerun-bench runs on your machine and makes no network requests of its own. The mock agent is fully offline. Real agents (`claude`, `codex`, `opencode`) are the CLIs you already use and contact their providers as they normally do, with your account. Results, diffs and reports are written only to the output directory you choose. Nothing is sent to the author or to any service.
