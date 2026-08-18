# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Rules

### 1. Keep `docs/` current with every feature

Documentation is part of the change, not a follow-up. A feature is not done
until the documents it affects are updated **in the same commit**.

| If you changed | Update |
|---|---|
| A route, schema, or status code | `docs/api.md` |
| The agent loop, prompts, or sandbox lifecycle | `docs/agent.md` |
| A model, migration, or ordering rule | `docs/database.md` |
| The Streamlit page or its API client | `docs/ui.md` |
| Service layout, boundaries, or data flow | `docs/architecture.md` |
| Setup, env vars, tests, or how to swap a provider | `docs/development.md` |
| Anything that changes what the project *is* | `docs/README.md` and the root `README.md` |

Write down **why**, not only what. A reader can see what the code does; what
they cannot recover is the reasoning — why history is snapshotted before the
question is stored, why a sandbox session is a cache rather than the source of
truth. Those explanations are the point.

### 2. Comment and document every file and function, in English

Every module gets a docstring saying what it is for. Every function, method and
class gets one saying what it does — and where the behaviour is subtle, why it
is written that way.

**English**, always, for comments and docstrings.

**Exception: user-facing strings stay Vietnamese.** Error messages, UI labels,
and the LLM prompts in `api/app/core/agent/prompts.py` are runtime data for a
Vietnamese-speaking audience, not documentation. Do not translate them.

Write comments where a reader would otherwise stop and wonder. A comment that
restates the code is noise; a comment explaining a non-obvious ordering, a
deliberate broad `except`, or a workaround for someone else's contract is worth
its space.

## Project

A framework for asking questions about an uploaded document. A file is
converted to markdown, then a CodeAct agent answers follow-up questions by
writing Python that reads the markdown inside a sandbox. It is a demo skeleton,
not a product.

Start at `docs/README.md`; `docs/architecture.md` explains how the pieces fit.

**Three compose services** — `postgres`, `api` (FastAPI, all agent logic), `ui`
(Streamlit, HTTP only).

**python-vm runs outside this compose project**, on port 8081, from a separate
repository. Chat turns return 503 when it is down.

## Commands

```bash
# tests — from the repository root, needs Postgres running
~/miniconda3/envs/minhln/bin/python -m pytest -m "not integration" -q

# smoke tests — needs the whole stack plus python-vm
~/miniconda3/envs/minhln/bin/python -m pytest -m integration -q

# the stack
docker compose up --build
```

Python runs from the conda environment **`minhln`**
(`/Users/macpro24/miniconda3/envs/minhln/bin/python`, Python 3.14). Never
create a virtualenv; install with that environment's `pip`.

## Working style

- **TDD.** The failing test comes first, then the implementation.
- **Do not put the whole document into the LLM context.** That is the reason
  CodeAct exists here; passing the markdown in as text defeats the design.
- **Postgres is the source of truth.** A sandbox session is a cache that may
  vanish at any time; code must survive that.
- Commit messages in Vietnamese with a `feat:` / `fix:` / `test:` / `chore:`
  prefix, matching the existing history.
- `docs/superpowers/` is git-ignored scratch from the build process. It is not
  project documentation — do not treat it as authoritative or update it.
