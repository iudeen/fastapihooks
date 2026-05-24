# Claude Adapter

Use AGENTS.md as the single source of truth for repository policy.

Operational notes:
- Keep core lightweight and extension-first.
- Keep BackgroundTaskBackend as the only bundled backend.
- Implement non-core transports via BaseBackend in external extensions.
- Preserve backward compatibility unless a breaking change is explicitly requested.
- Prefer small, verifiable edits with diagnostics/import validation.

If any instruction here conflicts with AGENTS.md, AGENTS.md wins.
