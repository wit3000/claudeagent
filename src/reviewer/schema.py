from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

PassId = Literal["p1", "p2", "p3"]
Category = Literal["facts", "logic", "style", "reader"]
Priority = Literal["high", "low"]


class Finding(BaseModel):
    quote: str
    paragraph: int = Field(ge=1)
    sentence: int | None = None
    category: Category
    defect: str
    fix: str
    source_pass: PassId
    hallucinated: bool = False


class PassResult(BaseModel):
    pass_id: PassId
    pass_version: str
    findings: list[Finding] = []
    raw_response: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    failed: bool = False
    failure_reason: str | None = None
    hallucinated_count: int = 0


class ConsensusItem(BaseModel):
    quote: str
    paragraph: int
    sentence: int | None
    category: Category
    confirmed_by: list[PassId]
    priority: Priority
    defects: list[str]
    fixes: list[str]


class ReviewReport(BaseModel):
    text_id: str
    created_at: datetime
    model_id: str
    provider: str = ""
    pass_version: str
    passes: list[PassResult]
    consensus: list[ConsensusItem]
    clean_categories: list[Category]
    warnings: list[str] = []
    source_text: str
