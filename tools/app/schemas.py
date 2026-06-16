"""Pydantic request/response models для Tools REST API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CalcRequest(BaseModel):
    expression: str


class FetchRequest(BaseModel):
    url: str


class SearchRequest(BaseModel):
    query: str
    max_results: int = 5


class ParseRequest(BaseModel):
    path: str


class CodeRequest(BaseModel):
    code: str


class AgentRequest(BaseModel):
    user_id: int
    text: str
    mode: str | None = None


class ComputerConfirmRequest(BaseModel):
    user_id: int
    code: str = ""


class ComputerUserRequest(BaseModel):
    user_id: int


class ModeRequest(BaseModel):
    mode: str


class ToolDispatchRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = {}
    user_id: int = 0
    allow_computer: bool = True


class PlanCreateRequest(BaseModel):
    user_id: int
    text: str


class PlanUserRequest(BaseModel):
    user_id: int


class CodeReviewRequest(BaseModel):
    user_id: int
    diff: str
    context: str = ""


class CodeFixRequest(BaseModel):
    user_id: int
    exe: str
    args: list[str] | None = None
    path: str = ""
    task: str = ""
    max_rounds: int | None = None
    no_confirm: bool = False  # CA-6.4: headless auto-apply (за policy gate)
    review: bool = False  # CA-5.1: self-review + авто-fix зауважень перед звітом


class FilePathRequest(BaseModel):
    user_id: int
    path: str


class FileUploadRequest(BaseModel):
    user_id: int
    path: str
    data_b64: str


class MacroRunRequest(BaseModel):
    user_id: int
    name: str


class SeeRequest(BaseModel):
    user_id: int
    question: str = ""


class TrustRequest(BaseModel):
    user_id: int
    full: bool = False


class BgJobCreate(BaseModel):
    user_id: int
    text: str = ""
    mode: str = "auto"
    job_type: str = "agent_turn"
    max_hops: int = 3
    # coding_task (CA-5.3): раннер + аргументи + cwd + стеля раундів fix-петлі.
    exe: str = ""
    args: list[str] | None = None
    path: str = ""
    max_rounds: int = 0


class ResearchRunRequest(BaseModel):
    job_id: str
    user_id: int
    query: str
    max_hops: int = 3


class ResearchRequest(BaseModel):
    user_id: int
    query: str
    max_hops: int = 3
    async_mode: bool = True


class McpCallRequest(BaseModel):
    server: str
    tool: str
    arguments: dict[str, Any] = {}


class BgJobFinish(BaseModel):
    result: str = ""
    error: str = ""
    status: str = "done"


class SkillActiveBody(BaseModel):
    user_id: int
    skill_id: str | None = None


class SubagentSpawnBody(BaseModel):
    user_id: int
    task: str
    budget_iters: int = 3
    mode: str = "agent"
    async_mode: bool = True


class SubagentRunBody(BaseModel):
    run_id: str
    user_id: int
    task: str
    budget_iters: int = 3
    mode: str = "agent"
    job_id: str = ""


class TeamSpawnBody(BaseModel):
    user_id: int
    task: str
    budget_per_role: int = 3
    roles: list[str] | None = None
    kind: str = ""  # "coding" → пресет Coder→Reviewer→Tester (CA-5.2)
    async_mode: bool = True


class TeamRunBody(BaseModel):
    team_id: str
    user_id: int
    job_id: str = ""


class OrchestratorSpawnBody(BaseModel):
    user_id: int
    task: str
    worker_budget: int = 5
    max_revisions: int = 1
    async_mode: bool = True


class OrchestratorRunBody(BaseModel):
    run_id: str
    user_id: int
    job_id: str = ""


class ImproveReviewBody(BaseModel):
    item_ids: list[str]
    action: str
    reviewer: str = ""


class LoraDeployRequest(BaseModel):
    version: str = ""
    path: str = ""


class CursorTaskBody(BaseModel):
    user_id: int
    task: str
    async_mode: bool = True
