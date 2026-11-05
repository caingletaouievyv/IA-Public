# IA/backend/app/ai/flashcards_job.py
"""Background flashcard generation with PostgreSQL-backed operation state."""

import logging
import threading

from app.ai.flashcards import (
    FlashcardGenerationError,
    FlashcardJobStopped,
    build_progress_result,
    generate_flashcards_batched,
)
from app.common.understanding_gaps import report_understanding_gap
from app.credits.manager import (
    complete_operation,
    fail_flashcard_operation,
    operation_is_pending_guarded,
    recover_abandoned_flashcard_operations,
    update_pending_operation_result,
)

logger = logging.getLogger(__name__)
_active_threads: set[tuple[str, str]] = set()
_thread_lock = threading.Lock()


def recover_flashcard_jobs_on_startup() -> int:
    """Refund and fail flashcard jobs that cannot resume after a process restart."""
    return recover_abandoned_flashcard_operations()


def _thread_key(user_id: str, operation_id: str) -> tuple[str, str]:
    return (user_id, operation_id)


def _mark_thread_running(user_id: str, operation_id: str) -> bool:
    key = _thread_key(user_id, operation_id)
    with _thread_lock:
        if key in _active_threads:
            return False
        _active_threads.add(key)
        return True


def _clear_thread(user_id: str, operation_id: str) -> None:
    with _thread_lock:
        _active_threads.discard(_thread_key(user_id, operation_id))


def _initial_progress(options: dict, total_batches: int) -> dict:
    return build_progress_result(0, total_batches, options["card_count"])


def _persist_progress(user_id: str, operation_id: str, progress: dict) -> None:
    if not operation_is_pending_guarded(user_id, operation_id):
        raise FlashcardJobStopped()
    if not update_pending_operation_result(user_id, operation_id, progress):
        raise FlashcardJobStopped()


def start_flashcard_generation(app, user_id: str, operation_id: str, options: dict, source_notes: list[dict]) -> None:
    """Persist initial progress and run batched generation on a background thread."""
    from app.ai.flashcards import batch_sizes

    total_batches = len(batch_sizes(options["card_count"]))
    update_pending_operation_result(
        user_id,
        operation_id,
        _initial_progress(options, total_batches),
    )
    if not _mark_thread_running(user_id, operation_id):
        return

    def runner() -> None:
        with app.app_context():
            try:
                if not operation_is_pending_guarded(user_id, operation_id):
                    return

                def pending_check() -> bool:
                    return operation_is_pending_guarded(user_id, operation_id)

                def on_progress(current_batch, total, card_count):
                    _persist_progress(
                        user_id,
                        operation_id,
                        build_progress_result(current_batch, total, card_count),
                    )

                cards = generate_flashcards_batched(
                    options,
                    source_notes,
                    progress_callback=on_progress,
                    pending_check=pending_check,
                )
                if not operation_is_pending_guarded(user_id, operation_id):
                    return
                complete_operation(user_id, operation_id, {"cards": cards})
            except FlashcardJobStopped:
                return
            except ValueError as error:
                fail_flashcard_operation(user_id, operation_id, str(error))
            except FlashcardGenerationError as error:
                fail_flashcard_operation(user_id, operation_id, str(error))
            except Exception as error:
                report_understanding_gap("flashcards.generation_failed", error, user_id=user_id)
                fail_flashcard_operation(user_id, operation_id, "Flashcard generation failed.")
                logger.exception("flashcard_generation_failed user_id=%s operation_id=%s", user_id, operation_id)
            finally:
                _clear_thread(user_id, operation_id)

    thread = threading.Thread(target=runner, name=f"flashcards-{operation_id[:8]}", daemon=True)
    thread.start()


def seed_pending_operation(user_id: str, operation_id: str, card_count: int, total_batches: int) -> None:
    """Mark a new flashcard operation before credit reservation completes."""
    update_pending_operation_result(
        user_id,
        operation_id,
        build_progress_result(0, total_batches, card_count),
    )
