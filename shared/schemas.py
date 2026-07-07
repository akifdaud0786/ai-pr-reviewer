"""
Pydantic schemas used for validation and inter-service HTTP/queue payloads.
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class GitHubPREventPayload(BaseModel):
    """Minimal shape we care about from GitHub's `pull_request` webhook event."""
    action: str
    number: int
    repo_full_name: str
    pr_title: Optional[str] = None
    author: Optional[str] = None
    head_sha: str
    base_branch: Optional[str] = None
    head_branch: Optional[str] = None
    diff_url: Optional[str] = None
    installation_id: Optional[str] = None
    merged: bool = False


class ReviewJob(BaseModel):
    """Message pushed onto the Redis/Celery queue for the Orchestrator to consume."""
    pull_request_id: str
    repo_full_name: str
    pr_number: int
    head_sha: str
    installation_id: Optional[str] = None
    diff_url: Optional[str] = None


class FindingOut(BaseModel):
    agent: str
    severity: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    title: str
    message: str
    suggestion: Optional[str] = None


class ReviewResult(BaseModel):
    pull_request_id: str
    repo_full_name: str
    pr_number: int
    head_sha: str
    installation_id: Optional[str] = None
    findings: List[FindingOut] = Field(default_factory=list)
    summary: str = ""


class PostCommentsRequest(BaseModel):
    repo_full_name: str
    pr_number: int
    head_sha: str
    installation_id: Optional[str] = None
    findings: List[FindingOut] = Field(default_factory=list)
    summary: str = ""


class LearnRequest(BaseModel):
    repo_full_name: str
    pr_number: int
    installation_id: Optional[str] = None
