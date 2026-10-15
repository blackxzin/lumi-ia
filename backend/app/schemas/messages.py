from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChatRequest(StrictModel):
    v: Literal[1] = 1
    type: Literal["chat"] = "chat"
    request_id: UUID
    session: UUID
    project: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=8000)
    mode: Literal["tutor", "copilot", "silent", "focus", "assistant", "exercise"] = "tutor"
    provider: Literal["default", "ollama", "codex"] = "default"
    skill: str | None = Field(default="auto", pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    use_editor: bool = False


class Diagnostic(StrictModel):
    line: int = Field(ge=1)
    message: str = Field(max_length=2000)
    severity: Literal["error", "warning", "info", "hint"]


class EditorEvent(StrictModel):
    v: Literal[1] = 1
    project: str = Field(max_length=80)
    path: str = Field(min_length=1, max_length=1024)
    language: str = Field(max_length=80)
    selection: str = Field(default="", max_length=8000)
    selection_line: int = Field(default=1, ge=1)
    diagnostics: list[Diagnostic] = Field(default_factory=list, max_length=30)


class Observation(StrictModel):
    paused: StrictBool


class FocusCommand(StrictModel):
    action: Literal["start", "pause", "resume", "complete", "cancel"]
    goal: str = Field(default="", max_length=240)
    focus_minutes: int = Field(default=25, ge=1, le=120)
    break_minutes: int = Field(default=5, ge=1, le=30)


class FocusReview(StrictModel):
    outcome: str = Field(min_length=1, max_length=1000)
    next_step: str = Field(default="", max_length=500)


class FocusStepInput(StrictModel):
    text: str = Field(min_length=1, max_length=200)
    done: bool = False


class FocusStepsInput(StrictModel):
    goal: str = Field(min_length=1, max_length=240)
    steps: list[FocusStepInput] = Field(max_length=20)


class ApprovalDecision(StrictModel):
    approved: StrictBool


class MemoryInput(StrictModel):
    kind: Literal["preference", "difficulty", "topic", "result", "decision", "lesson", "focus_outcome"]
    content: str = Field(min_length=1, max_length=4000)


class TerminalObservation(StrictModel):
    v: Literal[1] = 1
    project: str = Field(min_length=1, max_length=80)
    command: str = Field(default="", max_length=1000)
    output: str = Field(min_length=1, max_length=32000)


class ExerciseInput(StrictModel):
    prompt: str = Field(min_length=1, max_length=4000)
    answer: str = Field(default="", max_length=8000)
    topic: str = Field(default="", max_length=120)


class ExerciseReview(StrictModel):
    rating: int = Field(ge=0, le=5)


class ToolInput(StrictModel):
    name: Literal[
        "get_active_editor",
        "get_diagnostics",
        "read_project_file",
        "search_project",
        "get_git_status",
        "get_git_diff",
        "get_terminal_output",
        "run_project_tests",
        "propose_code_patch",
        "get_screen_context",
        "get_learning_progress",
    ]
    project: str = Field(max_length=80)
    path: str = Field(default="", max_length=1024)
    query: str = Field(default="", max_length=120)
    patch: str = Field(default="", max_length=16000)
    approval_id: UUID | None = None
