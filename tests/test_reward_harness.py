import pytest
from reward_harness import CodeRewardEngine, EvalResult


def test_reward_engine_prohibited_import():
    engine = CodeRewardEngine()
    code = "import os\ndef clamp(v, l, h): return v"
    result = engine.compute_reward(
        code=code,
        required_func="clamp",
        unit_tests=["clamp(5, 0, 10) == 5"],
        step_idx=1,
    )
    assert not result.passed_ast
    assert result.reward == -1.0
    assert "Prohibited import 'os'" in result.feedback


def test_reward_engine_missing_function():
    engine = CodeRewardEngine()
    code = "def wrong_func(v): return v"
    result = engine.compute_reward(
        code=code,
        required_func="clamp",
        unit_tests=["clamp(5, 0, 10) == 5"],
        step_idx=1,
    )
    assert not result.passed_ast
    assert result.reward == -1.0
    assert "Required function 'clamp' not found." in result.feedback


def test_reward_engine_partial_credit():
    engine = CodeRewardEngine()
    code = "def clamp(v, l, h):\n    return max(v, l)"
    unit_tests = [
        "clamp(5, 0, 10) == 5",
        "clamp(-2, 0, 10) == 0",
        "clamp(15, 0, 10) == 10",
        "clamp(0, 0, 10) == 0",
    ]
    result = engine.compute_reward(
        code=code,
        required_func="clamp",
        unit_tests=unit_tests,
        step_idx=1,
    )
    assert result.passed_ast
    assert result.passed_runtime
    assert not result.passed_tests
    assert result.tests_passed == 2
    assert result.reward == 0.25


def test_reward_engine_full_pass_with_step_penalty():
    engine = CodeRewardEngine()
    code = "def clamp(v, l, h):\n    return max(l, min(v, h))"
    unit_tests = [
        "clamp(5, 0, 10) == 5",
        "clamp(-2, 0, 10) == 0",
        "clamp(15, 0, 10) == 10",
    ]
    # Step 1: 1.0 - 0.0 = 1.0
    res1 = engine.compute_reward(code=code, required_func="clamp", unit_tests=unit_tests, step_idx=1)
    assert res1.reward == 1.0

    # Step 3: 1.0 - (2 * 0.05) = 0.9
    res3 = engine.compute_reward(code=code, required_func="clamp", unit_tests=unit_tests, step_idx=3)
    assert res3.reward == 0.9


def test_reward_engine_empty_unit_tests():
    engine = CodeRewardEngine()
    code = "def clamp(v, l, h):\n    return max(l, min(v, h))"
    res = engine.compute_reward(code=code, required_func="clamp", unit_tests=[])
    assert not res.passed_tests
    assert res.reward == 0.0
    assert "No unit tests provided" in res.feedback


def test_reward_engine_relative_import():
    engine = CodeRewardEngine()
    code = "from . import os\ndef clamp(v, l, h): return v"
    res = engine.compute_reward(code=code, required_func="clamp", unit_tests=["clamp(1, 0, 2) == 1"])
    assert not res.passed_ast
    assert res.reward == -1.0
    assert "Prohibited import" in res.feedback

