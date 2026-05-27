"""Basic math tool."""

from __future__ import annotations

import ast
from ARIA.core.registry import register_tool


class _SafeEval(ast.NodeVisitor):
    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Num,
        ast.Constant,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Mod,
        ast.Pow,
        ast.FloorDiv,
        ast.USub,
        ast.UAdd,
        ast.Load,
    )

    def visit(self, node):
        if not isinstance(node, self.allowed_nodes):
            raise ValueError("Gecersiz ifade")
        return super().visit(node)


@register_tool("calculator")
def calculator(expr: str) -> str:
    tree = ast.parse(expr, mode="eval")
    _SafeEval().visit(tree)
    result = eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}})
    return str(result)
