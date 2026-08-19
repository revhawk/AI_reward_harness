import pytest
from main import execute_python_code, AgentState, AgentStatus, step, TOOL_REGISTRY


def test_execute_python_code_success():
    res = execute_python_code("print('Hello World')")
    assert res["success"]
    assert res["stdout"] == "Hello World"
    assert res["exit_code"] == 0


def test_execute_python_code_runtime_error():
    res = execute_python_code("1 / 0")
    assert not res["success"]
    assert "ZeroDivisionError" in res["stderr"]
    assert res["exit_code"] == 1


def test_agent_trajectory_flow():
    state = AgentState(task_goal="Test execution flow", max_steps=3)

    # Step 1: Call Tool with syntax error
    step1_action = {
        "action_type": "CALL_TOOL",
        "tool_name": "run_python",
        "tool_input": {"code": "print(x)"},
    }
    state = step(state, step1_action)
    assert state.current_step == 1
    assert state.status == AgentStatus.RUNNING
    assert not state.trajectory[-1].tool_output["success"]

    # Step 2: Call Tool with correct code
    step2_action = {
        "action_type": "CALL_TOOL",
        "tool_name": "run_python",
        "tool_input": {"code": "x = 42\nprint(x)"},
    }
    state = step(state, step2_action)
    assert state.current_step == 2
    assert state.trajectory[-1].tool_output["stdout"] == "42"

    # Step 3: Finish
    step3_action = {
        "action_type": "FINISH",
        "tool_input": {"answer": "42"},
    }
    state = step(state, step3_action)
    assert state.status == AgentStatus.SUCCESS
    assert state.trajectory[-1].is_terminal


def test_agent_max_steps_exceeded():
    state = AgentState(task_goal="Infinite loop test", max_steps=2)

    step_action = {
        "action_type": "CALL_TOOL",
        "tool_name": "run_python",
        "tool_input": {"code": "print(1)"},
    }

    state = step(state, step_action)
    assert state.status == AgentStatus.RUNNING

    state = step(state, step_action)
    assert state.status == AgentStatus.MAX_STEPS_EXCEEDED
