import ast
import operator

# Only these maths operations are allowed. Nothing else can run.
_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _evaluate(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left = _evaluate(node.left)
        right = _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("Exponent too large")
        return _OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_evaluate(node.operand))
    raise ValueError("Unsupported expression")


def calculate(expression: str) -> str:
    """Evaluate a maths expression and return the exact result.

    Use this for any arithmetic. Supports + - * / ** % and brackets.

    Args:
        expression: The maths expression, for example "25 * 40" or "(3 + 4) ** 2".
    """
    tree = ast.parse(expression, mode="eval")
    result = _evaluate(tree.body)
    if isinstance(result, float):
        result = round(result, 6)
    return str(result)
