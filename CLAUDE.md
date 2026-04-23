# CLAUDE.md

Guidance specific to Claude Code. Core conventions, layout, commands, and anti-patterns live in [AGENTS.md](./AGENTS.md) — read that first.

This file only covers Claude-Code-specific behavior.

## Where to find context

- **Sub-project decomposition + status**: `AGENTS.md` §"Sub-project decomposition"
- **Current design spec**: `docs/superpowers/specs/` — pick the latest dated file for the sub-project you're working on
- **Architecture diagrams**: `docs/architecture.md` (mermaid)
- **Ignore `plan.md`** — that is the user's original stream-of-consciousness brainstorm. The canonical design is the dated spec in `docs/superpowers/specs/`. `plan.md` exists for historical reference only.

## Skills policy

Use [superpowers](https://github.com/obra/superpowers) skills actively. In particular:

- **`superpowers:brainstorming`** — before any creative work (new features, new sub-projects, design changes). Do not skip this even for "obviously simple" changes.
- **`superpowers:writing-plans`** — once a design spec is approved, before writing any code.
- **`superpowers:executing-plans`** — when working through an approved plan.
- **`superpowers:test-driven-development`** — tests before implementation for every repository method and every schema.
- **`superpowers:systematic-debugging`** — when any test fails or behavior surprises you. Do not guess-and-retry.
- **`superpowers:verification-before-completion`** — before claiming a task is done, run the actual verification commands. "Done" = `uv run pytest && uv run mypy packages && uv run ruff check` all green.
- **`superpowers:receiving-code-review`** — when review feedback feels wrong, verify technically before agreeing.

## Subagents

Use subagents to protect the main context:

- **`Explore`** — for any search across more than ~3 files. Don't burn context doing it yourself.
- **`feature-dev:code-explorer`** — when you need deep codebase analysis of an existing feature (rare in this repo since it's early).
- **`feature-dev:code-reviewer`** — before declaring a logical chunk complete. Runs against the spec and the conventions in `AGENTS.md`.
- **`general-purpose`** — fallback for multi-step research.

Parallelize independent subagent runs. Do not duplicate work a subagent is already doing.

## MCP usage

- **Context7** (`claude.ai Context7`) — use for library docs (SQLAlchemy, Alembic, OpenAI Agents SDK, Langfuse, Pydantic v2, Clerk, Supabase Python). Prefer it over web search for library syntax; your training data is often outdated.
- Do not use Context7 for business-logic debugging or refactoring — that's codebase analysis, not library docs.

## Destructive actions

- Never commit without explicit user approval. Always ask first. Use `git status` + `git diff` to surface what would be committed before asking.
- Never run `scripts/reset_db.py` without an explicit ask from the user. The guard protects prod, but the user's dev DB still matters.
- Never force-push. Never `git reset --hard`. Never amend merged commits.
- Never skip hooks (`--no-verify`) unless the user explicitly asks.

## Conversation style

- Keep inter-tool narration to one short sentence; reserve longer text for actual findings or results.
- End-of-turn summary: one or two sentences, max.
- Prefer markdown file links `[name](path)` over backticks for file references (VS Code extension renders them clickable).
- Match response length to the task. A simple question gets a direct answer; a design spec gets sections.

## Memory

The persistent memory index lives in the Claude Code memory directory for this project. Before recommending memory-based facts (library paths, flags, commands), verify they still exist in the current code. Memories decay; code doesn't.
