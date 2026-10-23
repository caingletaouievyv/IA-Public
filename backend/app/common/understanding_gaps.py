# IA/backend/app/common/understanding_gaps.py
"""Content-free structured logging for prompt-understanding and fallback gaps."""

import logging

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
}


def report_understanding_gap(code: str, error: BaseException | None = None) -> None:
    """Emit fixed metadata only; never pass prompt, note, or exception text."""
    try:
        feature, category, fallback = _GAPS[code]
    except KeyError as error:
        raise ValueError("Unknown understanding-gap code") from error

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
