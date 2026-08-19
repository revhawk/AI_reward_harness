import ast
import subprocess
import sys
import time
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
    pass_rate: float = 0.0
    exec_time_ms: float = 0.0
    complexity: int = 1
    loc: int = 0


@dataclass
class BatchEvalSummary:
    total_candidates: int
    passed_candidates: int
    pass_at_1: float
    mean_reward: float
    mean_exec_time_ms: float
    mean_complexity: float


def calculate_cyclomatic_complexity(tree: ast.AST) -> int:
    """
    Calculates static Cyclomatic Complexity V(G) = 1 + decision points.
    Decision points include: If, For, While, ExceptHandler, With, Assert, BoolOp (And/Or), IfExp, match_case, comprehension.
    """
    complexity = 1
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With, ast.Assert, ast.IfExp, ast.match_case)):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            complexity += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            complexity += len(node.ifs)
    return complexity


def calculate_loc(code: str) -> int:
    """Calculates non-empty, non-comment lines of code."""
    lines = [
        line.strip()
        for line in code.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return len(lines)


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
            "dataclasses",
        }

    def check_ast(self, code: str, required_func: str) -> tuple[bool, str, int]:
        """
        Static AST verification.
        Returns: (is_valid, feedback_msg, cyclomatic_complexity)
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"SyntaxError: {e.msg} at line {e.lineno}", 1

        complexity = calculate_cyclomatic_complexity(tree)

        # Ensure no disallowed imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    if root_mod not in self.allowed_imports:
                        return False, f"Prohibited import '{alias.name}'", complexity
            elif isinstance(node, ast.ImportFrom):
                root_mod = node.module.split(".")[0] if node.module else None
                if root_mod is None or root_mod not in self.allowed_imports:
                    mod_desc = f"from '{node.module}'" if node.module else "relative import"
                    return False, f"Prohibited import {mod_desc}", complexity

        # Ensure required function is present
        funcs = [
            n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
        ]
        if required_func not in funcs:
            return False, f"Required function '{required_func}' not found.", complexity

        return True, "AST Validated", complexity

    def execute_tests(
        self, code: str, unit_tests: list[str], timeout_sec: int = 4
    ) -> tuple[int, int, str, float]:
        """
        Executes candidate code against individual unit test assertions.
        Returns: (tests_passed, total_tests, stderr/feedback, wall_time_ms)
        """
        passed_count = 0
        total_count = len(unit_tests)
        start_time = time.perf_counter()

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
                    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    err = (
                        res.stderr.strip().split("\n")[-1]
                        if res.stderr
                        else "Assertion failed"
                    )
                    return (
                        passed_count,
                        total_count,
                        f"Failed on `{test_expr}` -> {err}",
                        elapsed_ms,
                    )
            except subprocess.TimeoutExpired:
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return (
                    passed_count,
                    total_count,
                    f"Timeout on test: `{test_expr}`",
                    elapsed_ms,
                )

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return passed_count, total_count, "All tests passed", elapsed_ms

    def compute_reward(
        self,
        code: str,
        required_func: str,
        unit_tests: list[str],
        step_idx: int = 1,
    ) -> EvalResult:
        """
        Calculates shaped scalar reward R in range [-1.0, 1.0] and rich execution metrics.
        """
        loc = calculate_loc(code)

        # Tier 1: Static AST Check
        ast_ok, ast_msg, complexity = self.check_ast(code, required_func)
        if not ast_ok:
            return EvalResult(
                passed_ast=False,
                passed_runtime=False,
                passed_tests=False,
                reward=-1.0,
                total_tests=len(unit_tests),
                tests_passed=0,
                pass_rate=0.0,
                exec_time_ms=0.0,
                complexity=complexity,
                loc=loc,
                feedback=ast_msg,
            )

        # Tier 2: Dynamic Execution & Unit Tests
        passed_cnt, total_cnt, exec_msg, exec_time_ms = self.execute_tests(code, unit_tests)
        if total_cnt == 0:
            return EvalResult(
                passed_ast=True,
                passed_runtime=False,
                passed_tests=False,
                reward=0.0,
                total_tests=0,
                tests_passed=0,
                pass_rate=0.0,
                exec_time_ms=exec_time_ms,
                complexity=complexity,
                loc=loc,
                feedback="No unit tests provided for evaluation.",
            )

        pass_rate = round(passed_cnt / total_cnt, 3)

        if passed_cnt == total_cnt:
            step_penalty = max(0.0, (step_idx - 1) * 0.05)
            final_reward = round(1.0 - step_penalty, 3)
            return EvalResult(
                passed_ast=True,
                passed_runtime=True,
                passed_tests=True,
                reward=final_reward,
                total_tests=total_cnt,
                tests_passed=passed_cnt,
                pass_rate=1.0,
                exec_time_ms=exec_time_ms,
                complexity=complexity,
                loc=loc,
                feedback="All tests passed successfully.",
            )

        partial_reward = round(0.5 * pass_rate, 3)
        return EvalResult(
            passed_ast=True,
            passed_runtime=(passed_cnt > 0),
            passed_tests=False,
            reward=partial_reward,
            total_tests=total_cnt,
            tests_passed=passed_cnt,
            pass_rate=pass_rate,
            exec_time_ms=exec_time_ms,
            complexity=complexity,
            loc=loc,
            feedback=exec_msg,
        )

    def evaluate_batch(
        self,
        candidates: list[str],
        required_func: str,
        unit_tests: list[str],
    ) -> tuple[list[EvalResult], BatchEvalSummary]:
        """
        Evaluates a batch of candidate solutions and returns aggregate summary metrics.
        """
        results = [
            self.compute_reward(code=c, required_func=required_func, unit_tests=unit_tests, step_idx=1)
            for c in candidates
        ]

        total = len(results)
        if total == 0:
            return [], BatchEvalSummary(0, 0, 0.0, 0.0, 0.0, 0.0)

        passed = sum(1 for r in results if r.passed_tests)
        pass_at_1 = round(passed / total, 3)
        mean_reward = round(sum(r.reward for r in results) / total, 3)
        mean_exec_time = round(sum(r.exec_time_ms for r in results) / total, 2)
        mean_complexity = round(sum(r.complexity for r in results) / total, 2)

        summary = BatchEvalSummary(
            total_candidates=total,
            passed_candidates=passed,
            pass_at_1=pass_at_1,
            mean_reward=mean_reward,
            mean_exec_time_ms=mean_exec_time,
            mean_complexity=mean_complexity,
        )

        return results, summary


if __name__ == "__main__":
    engine = CodeRewardEngine()

    target_func = "clamp"
    test_cases = [
        "clamp(5, 0, 10) == 5",
        "clamp(-2, 0, 10) == 0",
        "clamp(15, 0, 10) == 10",
        "clamp(0, 0, 10) == 0",
    ]

    cand_1 = "import os\ndef clamp(val, low, high): return val"
    cand_2 = "def clamp(val, low, high):\n    return max(val, low)"
    cand_3 = "def clamp(val, low, high):\n    return max(low, min(val, high))"

    for i, code_snippet in enumerate([cand_1, cand_2, cand_3], start=1):
        result = engine.compute_reward(
            code=code_snippet,
            required_func=target_func,
            unit_tests=test_cases,
            step_idx=i,
        )
        print(f"\n--- Candidate {i} ---")
        print(f"Reward: {result.reward} | Pass Rate: {result.pass_rate * 100}% | Complexity: {result.complexity} | LOC: {result.loc} | Time: {result.exec_time_ms} ms")
        print(f"Feedback: {result.feedback}")

    # Batch summary demo
    _, summary = engine.evaluate_batch([cand_1, cand_2, cand_3], target_func, test_cases)
    print(f"\n=== Batch Evaluation Summary ===")
    print(f"Pass@1: {summary.pass_at_1 * 100}% ({summary.passed_candidates}/{summary.total_candidates})")
    print(f"Mean Reward: {summary.mean_reward} | Mean Time: {summary.mean_exec_time_ms} ms | Mean Complexity: {summary.mean_complexity}")