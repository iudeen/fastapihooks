# Agent Runbook

This repository is configured to stay lightweight and extension-first.

This file is the canonical, tool-agnostic policy for AI coding agents.
If a tool supports its own instruction file (for example, `CLAUDE.md` or
`.github/copilot-instructions.md`), those files should mirror this runbook.

## Core Principle
- BackgroundTaskBackend is the only bundled backend.
- Additional transports should be implemented outside core using BaseBackend.

## Where Instructions Live
- Canonical policy: `AGENTS.md` (this file).
- Python file-specific guidance: `.github/instructions/python.instructions.md`.
- Reusable backend generation workflow: `.github/prompts/create-custom-backend.prompt.md`.
- Tool adapters: `.github/copilot-instructions.md`, `CLAUDE.md`.

## Agent Expectations
- Preserve current public API behavior unless a breaking change is requested.
- Prefer small, verifiable edits.
- Keep docs accurate for shipped functionality while preserving product vision.

## Backend Scope Rule
- Keep `BackgroundTaskBackend` as the only bundled backend in core.
- Implement additional transports externally via `BaseBackend`.
