"""A safe arithmetic calculator. Parses with ``ast``; never calls ``eval``."""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable
from typing import Any

from adversi.errors import ToolError
from adversi.protocol.evidence import SourceType
from adversi.tools.base import Tool

_BIN: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_FUNCS: dict[str, Callable[..., Any]] = {
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "floor": math.floor,
    "ceil": math.ceil,
}
_CONSTS = {"pi": math.pi, "e": math.e}
MAX_EXPRESSION_CHARS = 500
MAX_EXPONENT = 1000
MAX_MAGNITUDE = 1e300


def evaluate(expression: str) -> float | int:
    if len(expression) > MAX_EXPRESSION_CHARS:
        raise ToolError(f"expression longer than {MAX_EXPRESSION_CHARS} characters")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolError(f"invalid expression: {exc.msg}") from exc
    result: float | int = _eval(tree.body)
    return result


def _check(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ToolError("expression must evaluate to a number")
    if abs(value) > MAX_MAGNITUDE:
        raise ToolError("result magnitude too large")
    return value


def _eval(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return _check(node.value)
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise ToolError(f"exponent larger than {MAX_EXPONENT}")
        try:
            return _check(_BIN[type(node.op)](left, right))
        except (ZeroDivisionError, OverflowError, ValueError) as exc:
            raise ToolError(str(exc)) from exc
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _check(_UNARY[type(node.op)](_eval(node.operand)))
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCS
        and not node.keywords
    ):
        args = [_eval(a) for a in node.args]
        try:
            return _check(_FUNCS[node.func.id](*args))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ToolError(f"{node.func.id}: {exc}") from exc
    raise ToolError(f"unsupported syntax: {ast.dump(node)[:80]}")


def _calculate(expression: str) -> str:
    return f"{expression} = {evaluate(expression)!r}"


def calculator_tool() -> Tool:
    return Tool(
        "calculator",
        "Evaluate an arithmetic expression exactly. Supports + - * / // % **, parentheses, "
        "pi, e and sqrt, log, log10, log2, exp, sin, cos, tan, abs, round, min, max, floor, ceil.",
        _calculate,
        source_type=SourceType.CALCULATION,
        timeout_s=5.0,
    )
