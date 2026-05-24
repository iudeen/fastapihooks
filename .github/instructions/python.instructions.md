---
applyTo: "fasthooks/**/*.py"
description: "Use when editing Python source files in fasthooks; enforce lightweight core and extension-first backend design."
---

# Python File Instructions

## Backend Policy
- Keep BackgroundTaskBackend as the only bundled backend.
- For additional transports, implement or guide users to implement subclasses of BaseBackend.

## Implementation Standards
- Keep function signatures aligned across BaseBackend, concrete backends, and call sites.
- Preserve async interfaces for publish, consume, ack, and dispatcher methods.
- Use Optional and concrete collection types consistently in public method signatures.

## Safety and Compatibility
- Avoid introducing breaking API changes unless explicitly requested.
- If changing constructor args, update all usage sites in the repository.
- Prefer additive changes over removals.

## Minimalism
- Do not add heavy optional integrations by default.
- Keep dependencies minimal in pyproject.
