import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# 1. Execution Tool
def execute_python_code(code: str, timeout_seconds: int = 5) -> dict[str, Any]:
    """Executes Python code via standard input in an isolated subprocess."""
    try:
        result = subprocess.run(
            [sys.executable, "-"],
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout_seconds} seconds.",
            "exit_code": -1,
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
        }


# 2. Data Schemas & State
class AgentStatus(Enum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    MAX_STEPS_EXCEEDED = "MAX_STEPS_EXCEEDED"


@dataclass
class TrajectoryStep:
    step_idx: int
    action: str
    tool_name: str
    tool_input: dict[str, Any]
    tool_output: dict[str, Any]
    is_terminal: bool = False


@dataclass
class AgentState:
    task_goal: str
    max_steps: int = 4
    current_step: int = 0
    status: AgentStatus = AgentStatus.RUNNING
    trajectory: list[TrajectoryStep] = field(default_factory=list)


# 3. Tool Registry & Step Function
TOOL_REGISTRY = {
    "run_python": lambda kwargs: execute_python_code(kwargs.get("code", ""))
}


def step(state: AgentState, action_decision: dict[str, Any]) -> AgentState:
    """Applies one action to the environment, captures results, and returns new state."""
    if state.status != AgentStatus.RUNNING:
        return state

    state.current_step += 1
    tool_name = action_decision.get("tool_name", "")
    tool_input = action_decision.get("tool_input", {})
    action_type = action_decision.get("action_type", "CALL_TOOL")

    # Handle Final Answer
    if action_type == "FINISH":
        state.status = AgentStatus.SUCCESS
        state.trajectory.append(
            TrajectoryStep(
                step_idx=state.current_step,
                action="FINISH",
                tool_name="None",
                tool_input=tool_input,
                tool_output={"result": tool_input.get("answer", "")},
                is_terminal=True,
            )
        )
        return state

    # Dispatch Tool
    if tool_name in TOOL_REGISTRY:
        output = TOOL_REGISTRY[tool_name](tool_input)
    else:
        output = {
            "success": False,
            "stdout": "",
            "stderr": f"Unknown tool: {tool_name}",
            "exit_code": 1,
        }

    # Record Trajectory
    state.trajectory.append(
        TrajectoryStep(
            step_idx=state.current_step,
            action="CALL_TOOL",
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=output,
            is_terminal=False,
        )
    )

    # Check Termination Boundaries
    if state.current_step >= state.max_steps:
        state.status = AgentStatus.MAX_STEPS_EXCEEDED

    return state


# 4. Main Simulation Execution
if __name__ == "__main__":
    # Initialize state
    state = AgentState(task_goal="Compute the 10th Fibonacci number")

    # Mock Step 1: Agent writes buggy code (causes an error)
    step1_action = {
        "action_type": "CALL_TOOL",
        "tool_name": "run_python",
        "tool_input": {"code": "print(fib(10))"},
    }
    state = step(state, step1_action)

    # Mock Step 2: Agent corrects the code
    step2_action = {
        "action_type": "CALL_TOOL",
        "tool_name": "run_python",
        "tool_input": {
            "code": (
                "def fib(n):\n"
                "    a, b = 0, 1\n"
                "    for _ in range(n):\n"
                "        a, b = b, a + b\n"
                "    return a\n"
                "print(fib(10))"
            )
        },
    }
    state = step(state, step2_action)

    # Mock Step 3: Agent reports the final answer
    step3_action = {
        "action_type": "FINISH",
        "tool_input": {"answer": "The 10th Fibonacci number is 55"},
    }
    state = step(state, step3_action)

    # Print Trajectory Trace
    print(f"Final Status: {state.status.value}")
    print(f"Total Steps Taken: {state.current_step}")
    for t in state.trajectory:
        print(f"\n[Step {t.step_idx}] Action: {t.action} | Tool: {t.tool_name}")
        print(f"  Input:  {t.tool_input}")
        print(f"  Output: {t.tool_output}")