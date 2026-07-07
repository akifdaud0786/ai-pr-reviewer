"""
ORM models shared across services:
  - PullRequest   : metadata about each PR event received
  - ReviewFinding : individual (deduplicated) findings posted on a PR
  - RepoPattern   : repo-specific style/issue patterns learned from merged PRs
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text, ForeignKey, Enum, UniqueConstraint, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from shared.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class PRStatus(str, enum.Enum):
    RECEIVED = "received"
    QUEUED = "queued"
    REVIEWING = "reviewing"
    REVIEWED = "reviewed"
    MERGED = "merged"
    CLOSED = "closed"
    FAILED = "failed"


class Severity(str, enum.Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentType(str, enum.Enum):
    STATIC_ANALYSIS = "static_analysis"
    SECURITY = "security"
    STYLE = "style"
    ARCHITECTURE = "architecture"


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (UniqueConstraint("repo_full_name", "pr_number", "head_sha", name="uq_pr_sha"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    repo_full_name = Column(String, nullable=False, index=True)   # e.g. "octocat/hello-world"
    pr_number = Column(Integer, nullable=False, index=True)
    head_sha = Column(String, nullable=False)
    base_branch = Column(String, nullable=True)
    head_branch = Column(String, nullable=True)
    title = Column(String, nullable=True)
    author = Column(String, nullable=True)
    installation_id = Column(String, nullable=True)
    status = Column(Enum(PRStatus), default=PRStatus.RECEIVED, nullable=False)
    diff_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    findings = relationship("ReviewFinding", back_populates="pull_request", cascade="all, delete-orphan")


class ReviewFinding(Base):
    __tablename__ = "review_findings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    pull_request_id = Column(UUID(as_uuid=False), ForeignKey("pull_requests.id"), nullable=False)
    agent = Column(Enum(AgentType), nullable=False)
    severity = Column(Enum(Severity), default=Severity.INFO, nullable=False)
    file_path = Column(String, nullable=True)
    line_number = Column(Integer, nullable=True)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    suggestion = Column(Text, nullable=True)
    content_hash = Column(String, nullable=False, index=True)  # used for dedup
    posted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    pull_request = relationship("PullRequest", back_populates="findings")


class RepoPattern(Base):
    """Repo-specific learned patterns, extracted by the Learner service
    after PRs are merged. Fed back into the Orchestrator's prompt context
    for future reviews (`Load Repo Patterns` step)."""
    __tablename__ = "repo_patterns"
    __table_args__ = (UniqueConstraint("repo_full_name", "pattern_key", name="uq_repo_pattern"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    repo_full_name = Column(String, nullable=False, index=True)
    pattern_key = Column(String, nullable=False)     # e.g. "naming_convention", "frequent_issue:missing_null_check"
    pattern_value = Column(JSON, nullable=False)     # arbitrary structured detail
    frequency = Column(Integer, default=1)
    last_seen_pr = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
