import ast
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


@dataclass
class EvalResult:
    passed_ast: bool
    passed_runtime: bool
    passed_tests: bool
    reward: float
    total_tests: int
    tests_passed: int
    feedback: str


class CodeRewardEngine:
    """
    Evaluates generated code submissions and computes a scalar reward
    signal for reinforcement learning and automated evaluation.
    """

    def __init__(self, allowed_imports: set[str] | None = None):
        self.allowed_imports = allowed_imports or {
            "math",
            "typing",
            "collections",
            "itertools",
        }

    def check_ast(self, code: str, required_func: str) -> tuple[bool, str]:
        """Static AST verification."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"SyntaxError: {e.msg} at line {e.lineno}"

        # Ensure no disallowed imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name not in self.allowed_imports:
                        return False, f"Prohibited import '{alias.name}'"
            elif isinstance(node, ast.ImportFrom):
                if node.module not in self.allowed_imports:
                    return False, f"Prohibited import from '{node.module}'"

        # Ensure required function is present
        funcs = [
            n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
        ]
        if required_func not in funcs:
            return False, f"Required function '{required_func}' not found."

        return True, "AST Validated"

    def execute_tests(
        self, code: str, unit_tests: list[str], timeout_sec: int = 4
    ) -> tuple[int, int, str]:
        """
        Executes candidate code against individual unit test assertions.
        Returns: (tests_passed, total_tests, stderr/feedback)
        """
        passed_count = 0
        total_count = len(unit_tests)

        for test_expr in unit_tests:
            test_script = f"{code}\nassert {test_expr}"
            try:
                res = subprocess.run(
                    [sys.executable, "-"],
                    input=test_script,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                )
                if res.returncode == 0:
                    passed_count += 1
                else:
                    err = (
                        res.stderr.strip().split("\n")[-1]
                        if res.stderr
                        else "Assertion failed"
                    )
                    return (
                        passed_count,
                        total_count,
                        f"Failed on `{test_expr}` -> {err}",
                    )
            except subprocess.TimeoutExpired:
                return (
                    passed_count,
                    total_count,
                    f"Timeout on test: `{test_expr}`",
                )

        return passed_count, total_count, "All tests passed"

    def compute_reward(
        self,
        code: str,
        required_func: str,
        unit_tests: list[str],
        step_idx: int = 1,
    ) -> EvalResult:
        """
        Calculates the shaped scalar reward R in range [-1.0, 1.0].
        """
        # Tier 1: Static AST Check
        ast_ok, ast_msg = self.check_ast(code, required_func)
        if not ast_ok:
            return EvalResult(
                passed_ast=False,
                passed_runtime=False,
                passed_tests=False,
                reward=-1.0,
                total_tests=len(unit_tests),
                tests_passed=0,
                feedback=ast_msg,
            )

        # Tier 2: Dynamic Execution & Unit Tests
        passed_cnt, total_cnt, exec_msg = self.execute_tests(code, unit_tests)

        if passed_cnt == total_cnt:
            # Full pass: base reward 1.0 with a small penalty for taking extra turns
            step_penalty = max(0.0, (step_idx - 1) * 0.05)
            final_reward = round(1.0 - step_penalty, 3)
            return EvalResult(
                passed_ast=True,
                passed_runtime=True,
                passed_tests=True,
                reward=final_reward,
                total_tests=total_cnt,
                tests_passed=passed_cnt,
                feedback="All tests passed successfully.",
            )

        # Partial credit: fraction of unit tests passed (scaled between 0.0 and 0.5)
        partial_ratio = passed_cnt / total_cnt if total_cnt > 0 else 0.0
        partial_reward = round(0.5 * partial_ratio, 3)

        return EvalResult(
            passed_ast=True,
            passed_runtime=(passed_cnt > 0),
            passed_tests=False,
            reward=partial_reward,
            total_tests=total_cnt,
            tests_passed=passed_cnt,
            feedback=exec_msg,
        )


if __name__ == "__main__":
    engine = CodeRewardEngine()

    target_func = "clamp"
    test_cases = [
        "clamp(5, 0, 10) == 5",
        "clamp(-2, 0, 10) == 0",
        "clamp(15, 0, 10) == 10",
        "clamp(0, 0, 10) == 0",
    ]

    # Candidate 1: Syntax / Module violation
    cand_1 = "import os\ndef clamp(val, low, high): return val"

    # Candidate 2: Partial logic (fails upper bound check)
    cand_2 = "def clamp(val, low, high):\n    return max(val, low)"

    # Candidate 3: Correct solution on step 1
    cand_3 = "def clamp(val, low, high):\n    return max(low, min(val, high))"

    for i, code_snippet in enumerate([cand_1, cand_2, cand_3], start=1):
        result = engine.compute_reward(
            code=code_snippet,
            required_func=target_func,
            unit_tests=test_cases,
            step_idx=i,
        )
        print(f"\n--- Candidate {i} ---")
        print(f"Reward: {result.reward}")
        print(f"Tests Passed: {result.tests_passed}/{result.total_tests}")
        print(f"Feedback: {result.feedback}")