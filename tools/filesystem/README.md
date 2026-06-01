# Filesystem Primitive

Purpose: read, write, append, list, search, exists, and stat workspace files
through one primitive interface.

Current registry entry:

* `tool.filesystem.operate`

Broker route names:

* `file_read`
* `file_write`
* `file_append`
* `file_list`
* `file_search`
* `file_exists`
* `file_stat`

Supported operations:

* `read`
* `write`
* `append`
* `list`
* `search`
* `exists`
* `stat`

Keep this layer deterministic. Path validation, workspace boundaries, immutable
file checks, and output limits belong at the broker/policy boundary before this
primitive executes.
