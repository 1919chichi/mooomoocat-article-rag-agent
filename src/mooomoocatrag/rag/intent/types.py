from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class IntentType(str, Enum):
    CHITCHAT  = "chitchat"
    OFF_TOPIC = "off_topic"
    LIST      = "list"
    SUMMARIZE = "summarize"
    QA        = "qa"


@dataclass
class IntentResult:
    intent:       IntentType
    confidence:   float
    method:       Literal["rule", "llm", "fallback"]
    raw_response: str | None = None
    metadata:     dict = field(default_factory=dict)
