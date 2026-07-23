# AGENTS — AI coding agent instructions (concise)

Purpose
- Help AI coding agents get productive quickly in this repository without duplicating existing docs.

Quick links
- Project README: [README.md](README.md)
- Runtime: Docker Compose (`docker compose up`) — see `docker-compose.yml`
- Key scripts: [src/run_sync.py](src/run_sync.py), [src/sqs_consumer.py](src/sqs_consumer.py), [src/run_due_schedules.py](src/run_due_schedules.py)

What agents should do first
- Read `README.md` for environment and common commands.
- Inspect the `src/` folder for implementation entrypoints and tests.
- Avoid changing runtime configs without asking — many services run in Docker.

Link, don't embed
- If a topic is already documented (README, notebooks, or scripts), link to it rather than copying.

Conventions & tips
- Use `docker compose exec spark python /app/src/<script>.py` to run scripts inside the Spark container.
- Data directories are under `booking/`, `warehouse/`, and `localstack_data/` — treat these as large volumes.
- Tests and verification: prefer small, targeted test runs in-container where possible.

Text size (agent output guidance)
- Default responses: be concise. Prefer a short summary (2–6 bullets) and an optional one-paragraph explanation.
- Code diffs: produce minimal, focused patches (use apply_patch) and avoid large single-file rewrites.
- Large outputs (logs, datasets, file dumps): summarize findings and offer to write the full output to a new file in the repo (e.g., `docs/` or `tmp/`) instead of pasting inline.
- When asked for examples, prefer short runnable snippets. If the user requests full files or large generated content, confirm before creating them.

If you're unsure
- Ask a short clarifying question. Example: "Do you want the full file generated or a concise patch?"

Suggested next customizations
- Create a small skill for common container commands (start/stop/status) so agents can run reproducible steps.
- Add a test-run skill that runs quick smoke tests inside the Spark container.

Contact / Iteration
- If these instructions need more detail for specific areas (e.g., scheduler, ES mappings, or notebook workflows), request an area and I'll draft a focused instruction file.
