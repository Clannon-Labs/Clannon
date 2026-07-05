"""
Tests for the calculator tool (math.calculator).

Acceptance matrix:
  (a) tool is discoverable through the registry with populated metadata, READ perm
  (b) run() evaluates every supported operator correctly, respecting precedence
      and parentheses
  (c) edge cases: division/modulo by zero raise; a malformed or
      whitelist-escaping expression (attribute access, calls, names, literals
      other than numbers) raises "unsupported expression" rather than executing
      -- this is a hand-rolled AST evaluator specifically to avoid `eval()`, so
      the whitelist actually holding is the point of the tool
"""

import asyncio

import pytest

from tools.calculator import CalcIn, CalcOut, CalculatorTool


def _run(coro):
    return asyncio.run(coro)


def _calc(expression: str) -> float:
    return _run(CalculatorTool().run(CalcIn(expression=expression))).result


# ─── (a) registry discovery ────────────────────────────────────────────────

def test_calculator_tool_registered_and_not_broken():
    from registry.capabilities import discover, registry
    discover()
    spec = registry.get_tool("math.calculator")
    assert spec is not None, "math.calculator not found in registry after discover()"
    assert "math.calculator" not in {b.key for b in registry.broken()}


def test_calculator_tool_metadata_populated():
    from registry.capabilities import discover, registry
    discover()
    spec = registry.get_tool("math.calculator")
    assert spec.description
    assert spec.input_schema is CalcIn
    assert spec.output_schema is CalcOut


def test_calculator_tool_permission_read():
    from foundation import PermissionLevel
    from registry.capabilities import discover, registry
    discover()
    assert registry.get_tool("math.calculator").permission == PermissionLevel.READ


# ─── (b) every supported operator, precedence, parentheses ────────────────

def test_basic_operators():
    assert _calc("2 + 3") == 5
    assert _calc("5 - 3") == 2
    assert _calc("4 * 3") == 12
    assert _calc("7 / 2") == 3.5
    assert _calc("7 // 2") == 3
    assert _calc("7 % 2") == 1
    assert _calc("2 ** 10") == 1024


def test_unary_operators():
    assert _calc("-5 + 3") == -2
    assert _calc("+5") == 5
    assert _calc("--5") == 5   # double negation


def test_operator_precedence_and_parentheses():
    assert _calc("2 + 3 * 4") == 14
    assert _calc("(2 + 3) * 4") == 20
    assert _calc("2 * (3 + 4 * (5 - 2))") == 2 * (3 + 4 * (5 - 2))


def test_result_type_is_float():
    result = _run(CalculatorTool().run(CalcIn(expression="2 + 2")))
    assert isinstance(result, CalcOut)
    assert result.result == 4.0 and isinstance(result.result, float)


# ─── (c) edge cases: fail closed, whitelist actually holds ─────────────────

def test_division_by_zero_raises():
    with pytest.raises(ZeroDivisionError):
        _calc("1 / 0")


def test_modulo_by_zero_raises():
    with pytest.raises(ZeroDivisionError):
        _calc("1 % 0")


@pytest.mark.parametrize("expression", [
    "__import__('os').system('echo pwned')",   # function call
    "().__class__",                            # attribute access
    "x + 1",                                   # a bare name (no variables supported)
    "'a' + 'b'",                               # non-numeric constant
    "[1, 2, 3]",                                # a list literal
    "1 if True else 2",                        # a conditional expression
    "lambda: 1",                                # a lambda
])
def test_unsupported_expression_never_executes(expression):
    """The whitelist AST-walker's whole reason to exist: anything outside
    {Constant(int|float), BinOp, UnaryOp} must raise, never evaluate — this is
    what keeps the tool safe without a sandbox (invariant: no `eval()`)."""
    with pytest.raises((ValueError, SyntaxError)):
        _calc(expression)


def test_malformed_syntax_raises():
    with pytest.raises(SyntaxError):
        _calc("2 + * 3")
