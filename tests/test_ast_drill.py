import pytest
from ast_drill import verify_code, CodePolicyVerifier


def test_verify_code_syntax_error():
    code = "def foo(:"
    passed, violations = verify_code(code, "foo", 1)
    assert not passed
    assert any("SyntaxError" in v for v in violations)


def test_verify_code_prohibited_import():
    code = "import sys\ndef compute(x): return x"
    passed, violations = verify_code(code, "compute", 1)
    assert not passed
    assert any("Prohibited import 'sys'" in v for v in violations)


def test_verify_code_blocked_builtin():
    code = """
def compute(x):
    eval("x + 1")
    return x
"""
    passed, violations = verify_code(code, "compute", 1)
    assert not passed
    assert any("Dangerous built-in call 'eval()'" in v for v in violations)


def test_verify_code_signature_mismatch():
    code = "def compute_dot_product(vec_a): return vec_a"
    passed, violations = verify_code(code, "compute_dot_product", 2)
    assert not passed
    assert any("expects 2 argument(s), but found 1" in v for v in violations)


def test_verify_code_valid():
    code = """
from math import sqrt
from typing import Sequence

def compute_dot_product(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(vec_a, vec_b))
"""
    passed, violations = verify_code(code, "compute_dot_product", 2)
    assert passed
    assert len(violations) == 0
