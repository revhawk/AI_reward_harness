import ast
from typing import Any


class CodePolicyVerifier(ast.NodeVisitor):
    """Statically analyzes generated Python AST to enforce security policies and contract constraints."""

    def __init__(
        self,
        allowed_imports: set[str],
        required_func: str,
        expected_args: int,
    ):
        self.allowed_imports = allowed_imports
        self.required_func = required_func
        self.expected_args = expected_args

        self.violations: list[str] = []
        self.found_required_func = False

    def visit_Import(self, node: ast.Import) -> Any:
        """Inspects top-level imports like 'import os'."""
        for alias in node.names:
            if alias.name not in self.allowed_imports:
                self.violations.append(
                    f"Line {node.lineno}: Prohibited import '{alias.name}'."
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        """Inspects from-imports like 'from os import system'."""
        if node.module and node.module not in self.allowed_imports:
            self.violations.append(
                f"Line {node.lineno}: Prohibited import from module '{node.module}'."
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        """Blocks unsafe built-in executions like eval() or exec()."""
        if isinstance(node.func, ast.Name) and node.func.id in {
            "eval",
            "exec",
            "__import__",
        }:
            self.violations.append(
                f"Line {node.lineno}: Dangerous built-in call '{node.func.id}()' is blocked."
            )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        """Verifies target function presence and parameter count."""
        if node.name == self.required_func:
            self.found_required_func = True
            param_count = len(node.args.args)
            if param_count != self.expected_args:
                self.violations.append(
                    f"Line {node.lineno}: Function '{self.required_func}' expects {self.expected_args} "
                    f"argument(s), but found {param_count}."
                )
        self.generic_visit(node)


def verify_code(
    code: str, required_func: str, expected_args: int
) -> tuple[bool, list[str]]:
    """Runs complete static AST validation against security and signature policies."""
    # 1. Syntax check
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, [f"SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"]

    # 2. Structural & security policy check
    allowed_modules = {
        "math",
        "typing",
        "collections",
        "itertools",
        "dataclasses",
    }
    verifier = CodePolicyVerifier(
        allowed_imports=allowed_modules,
        required_func=required_func,
        expected_args=expected_args,
    )
    verifier.visit(tree)

    if not verifier.found_required_func:
        verifier.violations.append(
            f"Required function '{required_func}' was not defined."
        )

    is_valid = len(verifier.violations) == 0
    return is_valid, verifier.violations


if __name__ == "__main__":
    target_function = "compute_dot_product"
    target_args = 2

    # Scenario 1: Prohibited OS call (Security check)
    scenario_1 = """
import os

def compute_dot_product(vec_a, vec_b):
    os.system("echo compromised")
    return [a * b for a, b in zip(vec_a, vec_b)]
"""

    # Scenario 2: Signature mismatch (Contract check)
    scenario_2 = """
import math

def compute_dot_product(single_vector):
    return sum(x * x for x in single_vector)
"""

    # Scenario 3: Valid conforming solution
    scenario_3 = """
from math import sqrt
from typing import Sequence

def compute_dot_product(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(vec_a, vec_b))
"""

    test_cases = [
        ("Scenario 1 (Security Violation)", scenario_1),
        ("Scenario 2 (Signature Mismatch)", scenario_2),
        ("Scenario 3 (Valid Code)", scenario_3),
    ]

    for label, snippet in test_cases:
        passed, violations = verify_code(snippet, target_function, target_args)
        print(f"\n{'=' * 10} {label} {'=' * 10}")
        print(f"Status: {'PASSED' if passed else 'FAILED'}")
        if violations:
            print("Issues detected:")
            for v in violations:
                print(f"  - {v}")