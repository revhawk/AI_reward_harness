import pytest
from reward_harness import (
    CodeRewardEngine,
    calculate_cyclomatic_complexity,
    calculate_loc,
    BatchEvalSummary,
)
import ast


def test_calculate_loc():
    code = """
# This is a comment
def foo(x):
    if x > 0:
        return x

    return 0
"""
    # 4 non-empty, non-comment lines
    assert calculate_loc(code) == 4


def test_calculate_cyclomatic_complexity():
    code = """
def complex_fn(x, y):
    if x > 0 and y < 10:
        for i in range(x):
            if i % 2 == 0:
                print(i)
    elif x < -5:
        while y > 0:
            y -= 1
    return x + y
"""
    tree = ast.parse(code)
    # 1 base + If (1) + BoolOp 'and' (1) + For (1) + If (1) + IfExp/elif (1) + While (1) = 7
    complexity = calculate_cyclomatic_complexity(tree)
    assert complexity >= 6


def test_eval_result_new_metrics():
    engine = CodeRewardEngine()
    code = "def clamp(v, l, h):\n    return max(l, min(v, h))"
    unit_tests = ["clamp(5, 0, 10) == 5", "clamp(-2, 0, 10) == 0"]

    res = engine.compute_reward(code=code, required_func="clamp", unit_tests=unit_tests)
    assert res.pass_rate == 1.0
    assert res.complexity == 1
    assert res.loc == 2
    assert res.exec_time_ms > 0.0


def test_batch_evaluation_summary():
    engine = CodeRewardEngine()
    target_func = "clamp"
    test_cases = [
        "clamp(5, 0, 10) == 5",
        "clamp(-2, 0, 10) == 0",
        "clamp(15, 0, 10) == 10",
    ]

    cand_bad = "import os\ndef clamp(v, l, h): return v"
    cand_partial = "def clamp(v, l, h):\n    return max(v, l)"
    cand_good = "def clamp(v, l, h):\n    return max(l, min(v, h))"

    results, summary = engine.evaluate_batch([cand_bad, cand_partial, cand_good], target_func, test_cases)

    assert summary.total_candidates == 3
    assert summary.passed_candidates == 1
    assert summary.pass_at_1 == 0.333
    assert len(results) == 3


def test_calculate_cyclomatic_complexity_match_and_comprehension():
    code = """
def process(val, items):
    res = [x for x in items if x > 0 if x < 10]
    match val:
        case 1:
            return 10
        case 2:
            return 20
    return 0
"""
    tree = ast.parse(code)
    # 1 base + 2 comprehension ifs + 2 match cases = 5
    complexity = calculate_cyclomatic_complexity(tree)
    assert complexity == 5

