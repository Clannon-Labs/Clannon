"""calculator tool (key: math.calculator) — safe arithmetic, no eval."""

from __future__ import annotations

import ast
import operator

from pydantic import BaseModel

from foundation import PermissionLevel

from ..registry import tool

_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    raise ValueError("unsupported expression")


class CalcIn(BaseModel):
    expression: str


class CalcOut(BaseModel):
    result: float


@tool(
    name="calculator",
    domain="math",
    description="Evaluate a basic arithmetic expression (+ - * / // % ** and parentheses).",
    input_schema=CalcIn,
    output_schema=CalcOut,
    permission=PermissionLevel.READ,
    tags=("math",),
)
class CalculatorTool:
    async def run(self, args: CalcIn) -> CalcOut:
        tree = ast.parse(args.expression, mode="eval")
        return CalcOut(result=_eval(tree.body))
