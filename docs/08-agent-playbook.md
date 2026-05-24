# 08. Agent Playbook

## Policy Hierarchy
- AGENTS.md is canonical and tool-agnostic.
- CLAUDE.md and .github/copilot-instructions.md are adapters.
- Python-scoped rules are in .github/instructions/python.instructions.md.

## Repo Rules Agents Must Respect
- Keep BackgroundTaskBackend as the only bundled backend.
- Add non-core transports as external BaseBackend implementations.
- Preserve backward compatibility unless explicitly requested.

## Recommended Agent Workflow
1. Read AGENTS.md before edits.
2. Apply file-scoped instructions when editing Python under fastapihooks.
3. Keep changes small and verifiable.
4. Run diagnostics and one smoke check after meaningful edits.

## Built-In Prompt Asset
Reusable prompt:
- .github/prompts/create-custom-backend.prompt.md

Use this prompt when creating custom Redis/Kafka/SQS backends outside core.

## Drift Prevention
- Do not duplicate policy text across many files.
- Keep adapter files concise and defer to AGENTS.md.
- Update adapters when AGENTS.md semantics change.
