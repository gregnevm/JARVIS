"""Passport — домен культури Context Passport (P9/P10/C1, DESIGN §1.2.1).

Підсистема «context module» (див. docs/CONTEXT_MODULE.md): доменний шар — модель
паспорта, таксономія тегів, редакція. Без HTTP/DB/FS — споживають memory/gateway/agent.
"""
from __future__ import annotations

from .models import (
    DEFAULT_KIND,
    DEFAULT_SENSITIVITY,
    VALID_SENSITIVITIES,
    Passport,
    normalize_sensitivity,
    should_store_raw,
)
from .jobs import (
    CONTEXT_JOB_NAMES,
    DEFAULT_RETENTION_DAYS,
    ContextStore,
    build_daily,
    build_proposals,
    run_retention,
    summarize_pending,
)
from .build import PROVISIONAL_SUMMARY_LEN, build_store_event
from .redaction import Redactor, Rule, default_redactor
from .retrieval import format_context_block
from .tags import normalize_tags, split_tag, tags_contain

__all__ = [
    "ContextStore",
    "CONTEXT_JOB_NAMES",
    "DEFAULT_RETENTION_DAYS",
    "summarize_pending",
    "build_daily",
    "build_proposals",
    "run_retention",
    "Passport",
    "DEFAULT_KIND",
    "DEFAULT_SENSITIVITY",
    "VALID_SENSITIVITIES",
    "normalize_sensitivity",
    "should_store_raw",
    "normalize_tags",
    "split_tag",
    "tags_contain",
    "Redactor",
    "Rule",
    "default_redactor",
    "format_context_block",
    "build_store_event",
    "PROVISIONAL_SUMMARY_LEN",
]
