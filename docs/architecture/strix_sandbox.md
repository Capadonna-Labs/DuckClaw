# Strix Sandbox

The Strix sandbox isolates untrusted or tool-generated execution from core gateway processes.

## Security Objectives

- Minimize privilege surface for generated code execution.
- Prevent direct access to sensitive host resources.
- Keep deterministic audit traces for sandbox operations.

## Practical Constraints

- Network and filesystem exposure are explicitly constrained.
- Outputs are passed back through controlled channels.
- Gateway responses must not claim artifacts that sandbox did not actually produce.

## Related Operations

See also [Strix Sandbox Security](../Strix-Sandbox-Security.md) for operational controls, hardening checklists, and troubleshooting.
