# Shell Primitive

Purpose: execute commands in a sandbox for git, tests, build tools, and local
project automation.

Planned capability names:

* `shell_run`

Current registry entry:

* `tool.shell.run`

Current behavior:

* validates `command`, `cwd`, and timeout intent
* fails closed with a command-style result envelope

This primitive should never expose unrestricted host execution. Timeouts,
working-directory checks, command policy, and output caps belong at the
broker/policy boundary.
