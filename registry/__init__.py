"""Public authoring surface for registry decorators.

Most capability authors should import decorators from here:

    from registry import tool, expert

The deeper modules remain available for internal registry/discovery code and
for primitive capability work that needs to be explicit about the registration
layer it is touching.
"""

from .register import tool, expert

__all__ = ["tool", "expert"]
