# IA/backend/app/common/understanding_gaps.py
"""Content-free structured logging for prompt-understanding and fallback gaps."""

import logging

from app.diagnostics import context as diagnostic_context
from app.diagnostics import manager as diagnostics_manager

logger = logging.getLogger("ia.understanding")

_GAPS = {
    "memory.extraction.provider_failed": (
        "memory_extraction",
        "provider_failure",
        "continue_without_memory_update",
    ),
    "memory.extraction.output_invalid": (
        "memory_extraction",
        "provider_output_validation",
        "continue_without_memory_update",
    ),
    "memory.extraction.operation_failed": (
        "memory_extraction",
        "unexpected_or_persistence_failure",
        "continue_without_memory_update",
    ),
    "memory.forget.unresolved": (
        "memory_extraction",
        "forget_target_unresolved",
        "retain_memory_fail_closed",
    ),
    "memory.query.classification_failed": (
        "memory_retrieval",
        "low_overlap_query_classification",
        "continue_with_lexical_results",
    ),
    "ai_suggestions.action_selection_failed": (
        "ai_suggestions",
        "provider_or_action_validation",
        "choose_rule_based_action",
    ),
    "flashcards.generation_failed": (
        "flashcards",
        "provider_output_or_operation_failure",
        "return_error_without_saving_deck",
    ),
    "notes.image_ocr.unavailable": (
        "notes_from_images",
        "ocr_dependency_unavailable",
        "reject_when_no_text_is_extracted",
    ),
    "notes.image_ocr.image_failed": (
        "notes_from_images",
        "image_ocr_failed",
        "skip_failed_image",
    ),
    "notes.image_summary.empty": (
        "notes_from_images",
        "empty_summary",
        "save_ocr_text_excerpt",
    ),
    "notes.pdf_extract.unavailable": (
        "notes_from_pdf",
        "pdf_dependency_unavailable",
        "reject_extraction",
    ),
    "notes.pdf_extract.read_failed": (
        "notes_from_pdf",
        "upload_read_failed",
        "reject_extraction",
    ),
    "notes.pdf_extract.parse_failed": (
        "notes_from_pdf",
        "pdf_parse_failed",
        "reject_extraction",
    ),
    "notes.pdf_extract.encrypted": (
        "notes_from_pdf",
        "pdf_encrypted",
        "reject_extraction",
    ),
    "notes.pdf_extract.page_failed": (
        "notes_from_pdf",
        "pdf_page_extract_failed",
        "skip_page_continue",
    ),
    "ask.provider_failed": (
        "ask",
        "provider_failure",
        "return_error_to_client",
    ),
    "ask.operation_failed": (
        "ask",
        "unexpected_or_processing_failure",
        "return_error_to_client",
    ),
    "ask.feedback.reported": (
        "ask",
        "user_reported_answer",
        "review_without_stored_conversation",
    ),
}

_FEEDBACK_CATEGORY = {
    "wrong": "answer_incorrect",
    "unhelpful": "answer_unhelpful",
    "harmful": "answer_harmful",
    "other": "answer_other",
}


def gap_metadata(code: str) -> tuple[str, str, str]:
    try:
        return _GAPS[code]
    except KeyError as missing:
        raise ValueError("Unknown understanding-gap code") from missing


def report_understanding_gap(
    code: str,
    error: BaseException | None = None,
    *,
    user_id: str | None = None,
) -> None:
    """Emit fixed metadata only; optionally persist a bounded diagnostic record."""
    feature, category, fallback = gap_metadata(code)
    error_type = type(error).__name__ if error is not None else "none"
    if not error_type.isidentifier():
        error_type = "Unknown"
    logger.warning(
        "understanding_gap code=%s feature=%s category=%s fallback=%s error_type=%s",
        code,
        feature,
        category,
        fallback,
        error_type,
    )
    if not user_id:
        return
    metadata = diagnostic_context.context_metadata()
    metadata.setdefault("feature", feature)
    event = diagnostics_manager.build_automatic_event(
        user_id,
        code=code,
        feature=metadata.get("feature", feature),
        category=category,
        fallback=fallback,
        error_type=error_type,
        metadata=metadata,
    )
    diagnostics_manager.record_event(user_id, event)


def report_user_feedback(
    user_id: str,
    *,
    feature: str,
    reason: str,
    operation_id: str,
) -> dict:
    """Record an allow-listed user report linked to a completed Ask operation."""
    code = "ask.feedback.reported"
    _, _, fallback = gap_metadata(code)
    category = _FEEDBACK_CATEGORY[reason]
    metadata = diagnostic_context.context_metadata()
    metadata["operation_id"] = operation_id
    metadata["feature"] = feature
    event = diagnostics_manager.build_user_report_event(
        user_id,
        code=code,
        feature=feature,
        category=category,
        fallback=fallback,
        feedback_reason=reason,
        operation_id=operation_id,
        metadata=metadata,
    )
    logger.warning(
        "understanding_gap code=%s feature=%s category=%s fallback=%s error_type=none",
        code,
        feature,
        category,
        fallback,
    )
    recorded = diagnostics_manager.record_event(user_id, event)
    if recorded is None:
        raise ValueError("Diagnostics persistence is disabled")
    return recorded
