"""Authenticated flashcard-generation route regressions."""

import datetime
import json
import os
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET", "ia-unit-test-jwt-secret-with-enough-variety-2026")

import jwt

from flask import Flask

from app import create_app, config
from app.ai.flashcards import (
    FLASHCARDS_OPERATION_KIND,
    FLASHCARD_DUPLICATE_QUESTIONS_ERROR,
    FlashcardGenerationError,
    FlashcardJobStopped,
    batch_sizes,
    build_progress_result,
    generate_flashcards_batched,
    generate_flashcard_batch,
    _parse_batch_response,
)
from app.ai import flashcards_job
from app.credits import manager as credit_manager
from app.notes import manager as notes_manager
from scripts.test.notes_db import close_notes_database, ensure_note_owner, install_notes_database


def _run_flashcard_job_sync(app, user_id, operation_id, options, source_notes):
    total_batches = len(batch_sizes(options["card_count"]))
    credit_manager.update_pending_operation_result(
        user_id,
        operation_id,
        build_progress_result(0, total_batches, options["card_count"]),
    )
    try:
        def on_progress(current_batch, total, card_count):
            credit_manager.update_pending_operation_result(
                user_id,
                operation_id,
                build_progress_result(current_batch, total, card_count),
            )

        cards = generate_flashcards_batched(
            options,
            source_notes,
            progress_callback=on_progress,
            pending_check=lambda: credit_manager.operation_is_pending(user_id, operation_id),
        )
        credit_manager.complete_operation(user_id, operation_id, {"cards": cards})
    except (ValueError, FlashcardGenerationError) as error:
        credit_manager.fail_flashcard_operation(user_id, operation_id, str(error))
    except Exception:
        credit_manager.fail_flashcard_operation(user_id, operation_id, "Flashcard generation failed.")


class FlashcardRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_notes_database()
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.notes_data_patch = patch.object(notes_manager, "DATA_DIR", cls.temp_dir.name)
        cls.credits_data_patch = patch.object(credit_manager, "DATA_DIR", cls.temp_dir.name)
        cls.notes_data_patch.start()
        cls.credits_data_patch.start()
        cls.app = create_app()
        cls.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        from app import limiter

        limiter.enabled = False
        cls.client = cls.app.test_client()
        cls.role_patch = patch("app.ai.routes.get_user_role", return_value="user")
        cls.role_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.role_patch.stop()
        cls.credits_data_patch.stop()
        cls.notes_data_patch.stop()
        close_notes_database()
        cls.temp_dir.cleanup()

    def user_id(self):
        return ensure_note_owner(str(uuid.uuid4()))

    def headers(self, user_id):
        token = jwt.encode(
            {
                "sub": user_id,
                "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1),
            },
            config.JWT_SECRET,
            algorithm=config.JWT_ALGORITHM,
        )
        return {"Authorization": f"Bearer {token}"}

    def add_note(self, user_id, title, content, category="study"):
        return notes_manager.add_note(
            {"title": title, "category": category, "content": content, "tags": []},
            user_id,
        )

    def request_data(self, note_id, **overrides):
        return {
            "note_ids": [note_id],
            "card_count": 2,
            "difficulty": "Mixed",
            "question_style": "Understanding",
            "language": "Same as notes",
            "additional_instructions": "",
            "request_id": str(uuid.uuid4()),
            **overrides,
        }

    def _cards_json(self, count, prefix="Q"):
        return json.dumps({
            "cards": [
                {"question": f"{prefix}{index}?", "answer": f"A{index}."}
                for index in range(1, count + 1)
            ],
        })

    def test_generation_uses_only_selected_owned_notes_and_validates_cards(self):
        user_id = self.user_id()
        selected = self.add_note(user_id, "Biology", "Plants use light to make sugars.")
        self.add_note(user_id, "Other", "This material must not be sent.")
        initial_balance = credit_manager.get_credit_account(user_id)["credit_balance"]
        provider_output = self._cards_json(2)

        with (
            patch("app.ai.flashcards.call_flashcard_batch", return_value=provider_output) as provider,
            patch("app.ai.routes.start_flashcard_generation", side_effect=_run_flashcard_job_sync),
        ):
            response = self.client.post(
                "/ai/flashcards/generate",
                json=self.request_data(selected["id"]),
                headers=self.headers(user_id),
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(len(payload["cards"]), 2)
        self.assertEqual(
            credit_manager.get_credit_account(user_id)["credit_balance"],
            initial_balance - config.AI_ASK_CREDIT_COST,
        )
        provider.assert_called_once()
        messages = provider.call_args.kwargs["messages"]
        self.assertIn("untrusted user data", messages[0]["content"])
        source_payload = json.loads(messages[1]["content"])
        self.assertEqual(source_payload["source_notes"], [
            {"title": "Biology", "content": "Plants use light to make sugars."},
        ])

    def test_language_defaults_to_same_as_notes_when_omitted(self):
        user_id = self.user_id()
        note = self.add_note(user_id, "Biology", "Plants use light to make sugars.")
        request_data = self.request_data(note["id"])
        request_data.pop("language")

        with (
            patch("app.ai.flashcards.call_flashcard_batch", return_value=self._cards_json(2)),
            patch("app.ai.routes.start_flashcard_generation", side_effect=_run_flashcard_job_sync),
        ):
            response = self.client.post(
                "/ai/flashcards/generate",
                json=request_data,
                headers=self.headers(user_id),
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

    def test_authentication_and_note_ownership_are_required(self):
        user_id, other_user = self.user_id(), self.user_id()
        foreign_note = self.add_note(other_user, "Private", "Private source.")

        unauthenticated = self.client.post(
            "/ai/flashcards/generate",
            json=self.request_data(foreign_note["id"]),
        )
        self.assertEqual(unauthenticated.status_code, 401)

        with patch("app.ai.flashcards.call_flashcard_batch") as provider:
            response = self.client.post(
                "/ai/flashcards/generate",
                json=self.request_data(foreign_note["id"]),
                headers=self.headers(user_id),
            )
        self.assertEqual(response.status_code, 400)
        provider.assert_not_called()

    def test_invalid_request_and_history_note_are_rejected_before_provider_call(self):
        user_id = self.user_id()
        note = self.add_note(user_id, "Study", "A source.")
        history = self.add_note(user_id, "History", "[]", category="_history")
        deck = self.add_note(
            user_id,
            "Deck",
            '{"version":1,"cards":[{"question":"Q","answer":"A"}]}',
            category="_flashcards",
        )
        initial_balance = credit_manager.get_credit_account(user_id)["credit_balance"]

        with patch("app.ai.flashcards.call_flashcard_batch") as provider:
            invalid_count = self.client.post(
                "/ai/flashcards/generate",
                json=self.request_data(note["id"], card_count=100),
                headers=self.headers(user_id),
            )
            invalid_style = self.client.post(
                "/ai/flashcards/generate",
                json=self.request_data(note["id"], question_style="Unknown"),
                headers=self.headers(user_id),
            )
            history_response = self.client.post(
                "/ai/flashcards/generate",
                json=self.request_data(history["id"]),
                headers=self.headers(user_id),
            )
            deck_response = self.client.post(
                "/ai/flashcards/generate",
                json=self.request_data(deck["id"]),
                headers=self.headers(user_id),
            )

        self.assertEqual(invalid_count.status_code, 400)
        self.assertEqual(invalid_style.status_code, 400)
        self.assertEqual(history_response.status_code, 400)
        self.assertEqual(deck_response.status_code, 400)
        provider.assert_not_called()
        self.assertEqual(credit_manager.get_credit_account(user_id)["credit_balance"], initial_balance)

    def test_malformed_provider_response_fails_and_refunds_reserved_credit(self):
        user_id = self.user_id()
        note = self.add_note(user_id, "Study", "A source.")
        initial_balance = credit_manager.get_credit_account(user_id)["credit_balance"]

        with (
            patch(
                "app.ai.flashcards.call_flashcard_batch",
                return_value="PRIVATE_PROVIDER_OUTPUT_SENTINEL",
            ),
            patch("app.ai.routes.start_flashcard_generation", side_effect=_run_flashcard_job_sync),
        ):
            response = self.client.post(
                "/ai/flashcards/generate",
                json=self.request_data(note["id"]),
                headers=self.headers(user_id),
            )

        self.assertEqual(response.status_code, 502)
        payload = response.get_json()
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(
            credit_manager.get_credit_account(user_id)["credit_balance"],
            initial_balance,
        )

    def test_generates_99_cards_in_ten_batches(self):
        user_id = self.user_id()
        note = self.add_note(user_id, "Study", "Long source " * 50)
        request_data = self.request_data(note["id"], card_count=99, request_id="batch-99")
        sizes = batch_sizes(99)
        self.assertEqual(len(sizes), 10)
        self.assertEqual(sizes[-1], 9)
        call_count = {"value": 0}

        def provider_side_effect(*_args, **kwargs):
            call_count["value"] += 1
            batch_size = kwargs["batch_size"]
            start = sum(sizes[: call_count["value"] - 1]) + 1
            cards = [
                {"question": f"Question {index}?", "answer": f"Answer {index}."}
                for index in range(start, start + batch_size)
            ]
            return json.dumps({"cards": cards})

        with (
            patch("app.ai.flashcards.call_flashcard_batch", side_effect=provider_side_effect) as provider,
            patch("app.ai.routes.start_flashcard_generation", side_effect=_run_flashcard_job_sync),
        ):
            response = self.client.post(
                "/ai/flashcards/generate",
                json=request_data,
                headers=self.headers(user_id),
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(len(payload["cards"]), 99)
        self.assertEqual(provider.call_count, 10)

    def test_duplicate_questions_fail_and_refund(self):
        user_id = self.user_id()
        note = self.add_note(user_id, "Study", "Source text.")
        initial_balance = credit_manager.get_credit_account(user_id)["credit_balance"]

        with (
            patch(
                "app.ai.flashcards.call_flashcard_batch",
                side_effect=[
                    self._cards_json(2, prefix="Unique"),
                    json.dumps({"cards": [
                        {"question": "Unique1?", "answer": "A1."},
                        {"question": "Unique2?", "answer": "A2."},
                    ]}),
                ],
            ),
            patch("app.ai.routes.start_flashcard_generation", side_effect=_run_flashcard_job_sync),
        ):
            response = self.client.post(
                "/ai/flashcards/generate",
                json=self.request_data(note["id"], card_count=4, request_id="dup-test"),
                headers=self.headers(user_id),
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(credit_manager.get_credit_account(user_id)["credit_balance"], initial_balance)

    def test_middle_batch_failure_refunds_once(self):
        user_id = self.user_id()
        note = self.add_note(user_id, "Study", "Source text.")
        initial_balance = credit_manager.get_credit_account(user_id)["credit_balance"]
        calls = {"count": 0}

        def flaky_provider(*_args, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise FlashcardGenerationError("Batch failed.")
            return self._cards_json(2, prefix=f"B{calls['count']}")

        with (
            patch("app.ai.flashcards.call_flashcard_batch", side_effect=flaky_provider),
            patch("app.ai.routes.start_flashcard_generation", side_effect=_run_flashcard_job_sync),
        ):
            response = self.client.post(
                "/ai/flashcards/generate",
                json=self.request_data(note["id"], card_count=4, request_id="middle-fail"),
                headers=self.headers(user_id),
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(credit_manager.get_credit_account(user_id)["credit_balance"], initial_balance)

    def test_provider_request_failure_returns_failed_status_without_saving(self):
        user_id = self.user_id()
        note = self.add_note(user_id, "Study", "Source text.")
        initial_balance = credit_manager.get_credit_account(user_id)["credit_balance"]
        from app.ai.client import AIProviderError

        with (
            patch("app.ai.flashcards.call_flashcard_batch", side_effect=AIProviderError("groq request failed")),
            patch("app.ai.routes.start_flashcard_generation", side_effect=_run_flashcard_job_sync),
        ):
            response = self.client.post(
                "/ai/flashcards/generate",
                json=self.request_data(note["id"], card_count=2, request_id="provider-fail"),
                headers=self.headers(user_id),
            )

        self.assertEqual(response.status_code, 502)
        payload = response.get_json()
        self.assertEqual(payload.get("status"), "failed")
        self.assertEqual(payload.get("error"), "Flashcard provider request failed.")
        self.assertEqual(credit_manager.get_credit_account(user_id)["credit_balance"], initial_balance)

    def test_unexpected_worker_failure_returns_generic_failed_status(self):
        user_id = self.user_id()
        note = self.add_note(user_id, "Study", "Source text.")
        initial_balance = credit_manager.get_credit_account(user_id)["credit_balance"]

        with (
            patch("app.ai.flashcards.generate_flashcard_batch", side_effect=RuntimeError("boom")),
            patch("app.ai.routes.start_flashcard_generation", side_effect=_run_flashcard_job_sync),
        ):
            response = self.client.post(
                "/ai/flashcards/generate",
                json=self.request_data(note["id"], card_count=2, request_id="unexpected-fail"),
                headers=self.headers(user_id),
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json().get("error"), "Flashcard generation failed.")
        self.assertEqual(credit_manager.get_credit_account(user_id)["credit_balance"], initial_balance)

    def test_polling_does_not_charge_again(self):
        user_id = self.user_id()
        note = self.add_note(user_id, "Study", "Source text.")
        request_data = self.request_data(note["id"], request_id="poll-test")
        initial_balance = credit_manager.get_credit_account(user_id)["credit_balance"]

        with (
            patch("app.ai.flashcards.call_flashcard_batch", return_value=self._cards_json(2)),
            patch("app.ai.routes.start_flashcard_generation", side_effect=_run_flashcard_job_sync),
        ):
            started = self.client.post(
                "/ai/flashcards/generate",
                json=request_data,
                headers=self.headers(user_id),
            )
        self.assertEqual(started.status_code, 200)
        operation_id = started.get_json()["operation_id"]
        for _ in range(5):
            polled = self.client.get(
                f"/ai/flashcards/generate/{operation_id}",
                headers=self.headers(user_id),
            )
            self.assertEqual(polled.status_code, 200)
        self.assertEqual(
            credit_manager.get_credit_account(user_id)["credit_balance"],
            initial_balance - config.AI_ASK_CREDIT_COST,
        )

    def test_completed_operation_is_idempotent_without_extra_charge(self):
        user_id = self.user_id()
        note = self.add_note(user_id, "Study", "Source text.")
        request_data = self.request_data(note["id"], request_id="repeat-op")
        initial_balance = credit_manager.get_credit_account(user_id)["credit_balance"]

        with (
            patch("app.ai.flashcards.call_flashcard_batch", return_value=self._cards_json(2)),
            patch("app.ai.routes.start_flashcard_generation", side_effect=_run_flashcard_job_sync),
        ):
            first = self.client.post(
                "/ai/flashcards/generate",
                json=request_data,
                headers=self.headers(user_id),
            )
            second = self.client.post(
                "/ai/flashcards/generate",
                json=request_data,
                headers=self.headers(user_id),
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(second.get_json()["cards"]), 2)
        self.assertEqual(
            credit_manager.get_credit_account(user_id)["credit_balance"],
            initial_balance - config.AI_ASK_CREDIT_COST,
        )

    def test_startup_recovery_refunds_unfinished_flashcard_jobs(self):
        user_id = self.user_id()
        operation_id = "recover-me"
        initial_balance = credit_manager.get_credit_account(user_id)["credit_balance"]
        credit_manager.claim_operation(user_id, operation_id)
        credit_manager.reserve_credits(user_id, config.AI_ASK_CREDIT_COST, "ai_flashcards", operation_id)
        credit_manager.update_pending_operation_result(
            user_id,
            operation_id,
            {
                "kind": FLASHCARDS_OPERATION_KIND,
                "progress": {"current_batch": 2, "total_batches": 10, "card_count": 99},
            },
        )
        self.assertEqual(
            credit_manager.get_credit_account(user_id)["credit_balance"],
            initial_balance - config.AI_ASK_CREDIT_COST,
        )

        credit_manager.recover_abandoned_flashcard_operations()
        status = credit_manager.get_operation_status(user_id, operation_id)
        self.assertEqual(status["status"], "failed")
        self.assertEqual(credit_manager.get_credit_account(user_id)["credit_balance"], initial_balance)

    def test_resume_pending_post_does_not_charge_again(self):
        user_id = self.user_id()
        note = self.add_note(user_id, "Resume", "Body")
        request_id = "resume-same-op"
        request_data = self.request_data(note["id"], card_count=2, request_id=request_id)
        initial_balance = credit_manager.get_credit_account(user_id)["credit_balance"]
        credit_manager.claim_operation(user_id, request_id)
        credit_manager.reserve_credits(user_id, config.AI_ASK_CREDIT_COST, "ai_flashcards", request_id)
        credit_manager.update_pending_operation_result(
            user_id,
            request_id,
            build_progress_result(1, 1, 2),
        )
        with patch("app.ai.routes.start_flashcard_generation"):
            second = self.client.post(
                "/ai/flashcards/generate",
                json=request_data,
                headers=self.headers(user_id),
            )
        self.assertEqual(second.status_code, 202)
        self.assertEqual(second.get_json()["status"], "pending")
        self.assertEqual(
            credit_manager.get_credit_account(user_id)["credit_balance"],
            initial_balance - config.AI_ASK_CREDIT_COST,
        )


class FlashcardJobRaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_notes_database()

    @classmethod
    def tearDownClass(cls):
        close_notes_database()

    def setUp(self):
        self.user = ensure_note_owner(str(uuid.uuid4()))

    def test_batched_progress_refreshes_idle_activity(self):
        operation_id = "idle-refresh"
        credit_manager.claim_operation(self.user, operation_id)
        credit_manager.update_pending_operation_result(
            self.user,
            operation_id,
            build_progress_result(0, 3, 30),
        )
        with patch("app.ai.flashcards.call_flashcard_batch", return_value='{"cards":[{"question":"Q1","answer":"A1"}]}'):
            generate_flashcards_batched(
                {"card_count": 1, "difficulty": "Mixed", "question_style": "Mixed", "language": "Same as notes", "additional_instructions": ""},
                [{"title": "T", "content": "Body"}],
                progress_callback=lambda current, total, count: credit_manager.update_pending_operation_result(
                    self.user,
                    operation_id,
                    build_progress_result(current, total, count),
                ),
            )
        status = credit_manager.get_operation_status(self.user, operation_id)
        activity = status["result"]["last_activity_at"]
        started = status["started_at"]
        self.assertGreater(activity, started)

    def test_pending_check_stops_before_next_provider_batch(self):
        provider_calls = []

        def provider(**kwargs):
            batch_index = len(provider_calls) + 1
            provider_calls.append(batch_index)
            cards = [
                {"question": f"Q{batch_index}-{index}", "answer": f"A{batch_index}-{index}"}
                for index in range(kwargs["batch_size"])
            ]
            return json.dumps({"cards": cards})

        still_pending = {"value": True}

        def on_progress(*_args):
            still_pending["value"] = False

        with patch("app.ai.flashcards.call_flashcard_batch", side_effect=provider):
            with self.assertRaises(FlashcardJobStopped):
                generate_flashcards_batched(
                    {
                        "card_count": 20,
                        "difficulty": "Mixed",
                        "question_style": "Mixed",
                        "language": "Same as notes",
                        "additional_instructions": "",
                    },
                    [{"title": "T", "content": "Body"}],
                    progress_callback=on_progress,
                    pending_check=lambda: still_pending["value"],
                )
        self.assertEqual(provider_calls, [1])

    def test_concurrent_expiry_and_completion(self):
        operation_id = "race-complete"
        credit_manager.claim_operation(self.user, operation_id)
        credit_manager.reserve_credits(self.user, config.AI_ASK_CREDIT_COST, "ai_flashcards", operation_id)
        credit_manager.update_pending_operation_result(
            self.user,
            operation_id,
            build_progress_result(1, 3, 30),
        )
        from sqlalchemy import select

        from app.credits.models import CreditOperation
        from app.credits import repository

        with repository.credits_session() as session:
            row = session.scalar(
                select(CreditOperation).where(
                    CreditOperation.user_id == self.user,
                    CreditOperation.operation_id == operation_id,
                )
            )
            row.started_at = time.time() - config.FLASHCARD_JOB_MAX_SECONDS - 1
            result = dict(row.result or {})
            result["last_activity_at"] = row.started_at
            row.result = result
        outcomes = []

        def complete():
            outcomes.append(
                ("complete", credit_manager.complete_operation(self.user, operation_id, {"cards": []}))
            )

        def expire():
            outcomes.append(
                ("expire", credit_manager.maybe_fail_expired_flashcard_operation(self.user, operation_id))
            )

        threads = [threading.Thread(target=complete), threading.Thread(target=expire)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        status = credit_manager.get_operation_status(self.user, operation_id)["status"]
        self.assertIn(status, {"completed", "failed"})
        self.assertEqual(
            sum(1 for name, ok in outcomes if ok),
            1,
        )

    def test_startup_recovery_does_not_refund_twice(self):
        operation_id = "recover-twice"
        initial_balance = credit_manager.get_credit_account(self.user)["credit_balance"]
        credit_manager.claim_operation(self.user, operation_id)
        credit_manager.reserve_credits(self.user, config.AI_ASK_CREDIT_COST, "ai_flashcards", operation_id)
        credit_manager.update_pending_operation_result(
            self.user,
            operation_id,
            build_progress_result(0, 5, 50),
        )
        credit_manager.recover_abandoned_flashcard_operations()
        self.assertEqual(credit_manager.get_operation_status(self.user, operation_id)["status"], "failed")
        balance_after_first = credit_manager.get_credit_account(self.user)["credit_balance"]
        self.assertEqual(balance_after_first, initial_balance)
        credit_manager.recover_abandoned_flashcard_operations()
        self.assertEqual(credit_manager.get_credit_account(self.user)["credit_balance"], balance_after_first)

    def test_worker_skips_provider_after_operation_failed(self):
        operation_id = "worker-stop"
        credit_manager.claim_operation(self.user, operation_id)
        credit_manager.reserve_credits(self.user, config.AI_ASK_CREDIT_COST, "ai_flashcards", operation_id)
        options = {
            "card_count": 20,
            "difficulty": "Mixed",
            "question_style": "Mixed",
            "language": "Same as notes",
            "additional_instructions": "",
        }
        source_notes = [{"title": "T", "content": "Body"}]
        calls = []

        def provider(**kwargs):
            calls.append(1)
            if len(calls) == 1:
                credit_manager.fail_flashcard_operation(self.user, operation_id, "stopped")
            cards = [{"question": f"Q{index}", "answer": f"A{index}"} for index in range(kwargs["batch_size"])]
            return json.dumps({"cards": cards})

        app = Flask(__name__)
        app.config.update(TESTING=True)

        def immediate_start(thread_self):
            thread_self._target(*thread_self._args, **thread_self._kwargs)

        with (
            patch("app.ai.flashcards.call_flashcard_batch", side_effect=provider),
            patch.object(threading.Thread, "start", immediate_start),
        ):
            flashcards_job.start_flashcard_generation(app, self.user, operation_id, options, source_notes)
        self.assertEqual(calls, [1])
        self.assertEqual(credit_manager.get_operation_status(self.user, operation_id)["status"], "failed")


class FlashcardBatchRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.options = {
            "difficulty": "Mixed",
            "question_style": "Mixed",
            "language": "Same as notes",
            "additional_instructions": "",
        }
        self.source_notes = [{"title": "Biology", "content": "Cells have membranes."}]

    def test_json_validate_failed_recovers_by_splitting_batch(self):
        from app.ai.client import AIProviderError

        half_calls = {"count": 0}

        def provider_side_effect(*_args, **kwargs):
            batch_size = kwargs["batch_size"]
            if batch_size == 10:
                raise AIProviderError(
                    "Flashcard provider request failed.",
                    category="json_validate_failed",
                    status_code=400,
                )
            half_calls["count"] += 1
            start = (half_calls["count"] - 1) * 5 + 1
            cards = [
                {"question": f"Question {index}?", "answer": f"Answer {index}."}
                for index in range(start, start + batch_size)
            ]
            return json.dumps({"cards": cards})

        with patch("app.ai.flashcards.call_flashcard_batch", side_effect=provider_side_effect) as provider:
            cards = generate_flashcard_batch(
                self.source_notes,
                self.options,
                10,
                [f"Existing {index}?" for index in range(1, 11)],
                batch_index=2,
                operation_id="split-recover",
            )

        self.assertEqual(len(cards), 10)
        self.assertEqual(provider.call_count, 5)
        self.assertEqual({card["question"] for card in cards}, {f"Question {index}?" for index in range(1, 11)})

    def test_split_recovery_shares_provider_call_budget(self):
        from app.ai.client import AIProviderError, FlashcardProviderCallBudget

        budget = FlashcardProviderCallBudget(limit=8)
        half_calls = {"count": 0}

        def provider_side_effect(*_args, **kwargs):
            batch_size = kwargs["batch_size"]
            if batch_size == 10:
                raise AIProviderError(
                    "Flashcard provider request failed.",
                    category="json_validate_failed",
                    status_code=400,
                )
            half_calls["count"] += 1
            start = (half_calls["count"] - 1) * 5 + 1
            cards = [
                {"question": f"Question {index}?", "answer": f"Answer {index}."}
                for index in range(start, start + batch_size)
            ]
            return json.dumps({"cards": cards})

        with patch("app.ai.flashcards.call_flashcard_batch", side_effect=provider_side_effect):
            cards = generate_flashcard_batch(
                self.source_notes,
                self.options,
                10,
                [],
                batch_index=2,
                operation_id="budget-split",
                provider_budget=budget,
            )

        self.assertEqual(len(cards), 10)
        self.assertEqual(budget.used, 5)

    def test_json_validate_exhausted_retries_fail_without_partial_batch(self):
        from app.ai.client import AIProviderError, FlashcardProviderCallBudget

        budget = FlashcardProviderCallBudget(limit=8)

        def always_json_validate(**_kwargs):
            raise AIProviderError(
                "Flashcard provider request failed.",
                category="json_validate_failed",
                status_code=400,
            )

        with patch("app.ai.flashcards.call_flashcard_batch", side_effect=always_json_validate) as provider:
            with self.assertRaises(FlashcardGenerationError):
                generate_flashcard_batch(
                    self.source_notes,
                    self.options,
                    2,
                    [],
                    batch_index=1,
                    operation_id="exhausted",
                    provider_budget=budget,
                )
        self.assertEqual(provider.call_count, 8)
        self.assertEqual(budget.used, 8)

    def test_permanent_provider_error_does_not_retry(self):
        from app.ai.client import AIProviderError

        def permanent_failure(**_kwargs):
            raise AIProviderError(
                "Flashcard provider request failed.",
                category="http_error",
                status_code=401,
            )

        with patch("app.ai.flashcards.call_flashcard_batch", side_effect=permanent_failure) as provider:
            with self.assertRaises(FlashcardGenerationError):
                generate_flashcard_batch(
                    self.source_notes,
                    self.options,
                    2,
                    [],
                    batch_index=1,
                    operation_id="auth-fail",
                )
        self.assertEqual(provider.call_count, 1)

    def test_generic_provider_error_does_not_retry(self):
        from app.ai.client import AIProviderError

        def generic_failure(**_kwargs):
            raise AIProviderError(
                "Flashcard provider request failed.",
                category="provider_error",
            )

        with patch("app.ai.flashcards.call_flashcard_batch", side_effect=generic_failure) as provider:
            with self.assertRaises(FlashcardGenerationError):
                generate_flashcard_batch(
                    self.source_notes,
                    self.options,
                    2,
                    [],
                    batch_index=1,
                    operation_id="generic-fail",
                )
        self.assertEqual(provider.call_count, 1)


class FlashcardDuplicateRecoveryTests(unittest.TestCase):
    @staticmethod
    def _user_request_payload(messages):
        """Parse batch request JSON; repair suffixes are appended after the object."""
        content = messages[1]["content"]
        payload, _ = json.JSONDecoder().raw_decode(content)
        return payload

    def setUp(self):
        self.options = {
            "difficulty": "Mixed",
            "question_style": "Mixed",
            "language": "Same as notes",
            "additional_instructions": "",
        }
        self.source_notes = [{"title": "Biology", "content": "Cells have membranes."}]

    def test_parse_batch_response_rejects_duplicate_within_batch(self):
        payload = json.dumps(
            {
                "cards": [
                    {"question": "Same topic?", "answer": "A1."},
                    {"question": "Same topic?", "answer": "A2."},
                ]
            }
        )
        with self.assertRaises(FlashcardGenerationError) as ctx:
            _parse_batch_response(payload, 2, [])
        self.assertEqual(str(ctx.exception), FLASHCARD_DUPLICATE_QUESTIONS_ERROR)

    def test_duplicate_against_previous_batch_retries_then_succeeds(self):
        calls = {"count": 0}

        def provider_side_effect(*_args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return json.dumps(
                    {
                        "cards": [
                            {"question": "Prior?", "answer": "Old."},
                            {"question": "Another?", "answer": "Old2."},
                        ]
                    }
                )
            return json.dumps(
                {
                    "cards": [
                        {"question": "Fresh one?", "answer": "New."},
                        {"question": "Fresh two?", "answer": "New2."},
                    ]
                }
            )

        with patch("app.ai.flashcards.call_flashcard_batch", side_effect=provider_side_effect) as provider:
            cards = generate_flashcard_batch(
                self.source_notes,
                self.options,
                2,
                ["Prior?"],
                batch_index=2,
                operation_id="dup-retry",
            )

        self.assertEqual(len(cards), 2)
        self.assertEqual(provider.call_count, 2)

    def test_duplicate_within_batch_retries_with_duplicate_repair_prompt(self):
        calls = {"count": 0}

        def provider_side_effect(*_args, **kwargs):
            calls["count"] += 1
            messages = kwargs["messages"]
            user_content = messages[1]["content"]
            if calls["count"] == 1:
                return json.dumps(
                    {
                        "cards": [
                            {"question": "Repeat?", "answer": "A1."},
                            {"question": "Repeat?", "answer": "A2."},
                        ]
                    }
                )
            if calls["count"] == 2:
                self.assertIn("duplicated existing_questions", user_content)
                self.assertNotIn("not valid JSON with the required shape", user_content)
            return json.dumps(
                {
                    "cards": [
                        {"question": "Unique one?", "answer": "A1."},
                        {"question": "Unique two?", "answer": "A2."},
                    ]
                }
            )

        with patch("app.ai.flashcards.call_flashcard_batch", side_effect=provider_side_effect) as provider:
            cards = generate_flashcard_batch(
                self.source_notes,
                self.options,
                2,
                [],
                batch_index=1,
                operation_id="in-batch-dup",
            )

        self.assertEqual(len(cards), 2)
        self.assertEqual(provider.call_count, 2)

    def test_duplicate_exhausted_attempts_split_batch(self):
        from app.ai.client import FlashcardProviderCallBudget

        budget = FlashcardProviderCallBudget(limit=8)
        half_calls = {"count": 0}

        def provider_side_effect(*_args, **kwargs):
            batch_size = kwargs["batch_size"]
            if batch_size == 4:
                return json.dumps(
                    {
                        "cards": [
                            {"question": "Taken?", "answer": "A."},
                            {"question": "Alt two?", "answer": "B."},
                            {"question": "Alt three?", "answer": "C."},
                            {"question": "Alt four?", "answer": "D."},
                        ]
                    }
                )
            half_calls["count"] += 1
            start = (half_calls["count"] - 1) * 2 + 1
            cards = [
                {"question": f"Split {start}?", "answer": f"A{start}."},
                {"question": f"Split {start + 1}?", "answer": f"A{start + 1}."},
            ]
            return json.dumps({"cards": cards})

        with patch("app.ai.flashcards.call_flashcard_batch", side_effect=provider_side_effect) as provider:
            cards = generate_flashcard_batch(
                self.source_notes,
                self.options,
                4,
                ["Taken?"],
                batch_index=2,
                operation_id="dup-split",
                provider_budget=budget,
            )

        self.assertEqual(len(cards), 4)
        self.assertGreaterEqual(provider.call_count, 4)
        self.assertLessEqual(budget.used, 8)

    def test_split_right_batch_receives_left_generated_questions(self):
        seen_existing_lengths = []

        def provider_side_effect(*_args, **kwargs):
            messages = kwargs["messages"]
            payload = FlashcardDuplicateRecoveryTests._user_request_payload(messages)
            seen_existing_lengths.append(len(payload["existing_questions"]))
            batch_size = kwargs["batch_size"]
            if batch_size == 4:
                return json.dumps(
                    {
                        "cards": [
                            {"question": "Blocker?", "answer": "A."},
                            {"question": "Alt two?", "answer": "B."},
                            {"question": "Alt three?", "answer": "C."},
                            {"question": "Alt four?", "answer": "D."},
                        ]
                    }
                )
            if batch_size == 2 and len(seen_existing_lengths) <= 4:
                return json.dumps(
                    {
                        "cards": [
                            {"question": "Left one?", "answer": "L1."},
                            {"question": "Left two?", "answer": "L2."},
                        ]
                    }
                )
            if payload["existing_questions"] == ["Blocker?", "Left one?", "Left two?"]:
                return json.dumps(
                    {
                        "cards": [
                            {"question": "Right one?", "answer": "R1."},
                            {"question": "Right two?", "answer": "R2."},
                        ]
                    }
                )
            return json.dumps(
                {
                    "cards": [
                        {"question": "Blocker?", "answer": "Dup."},
                        {"question": "Blocker?", "answer": "Dup2."},
                    ]
                }
            )

        with patch("app.ai.flashcards.call_flashcard_batch", side_effect=provider_side_effect):
            cards = generate_flashcard_batch(
                self.source_notes,
                self.options,
                4,
                ["Blocker?"],
                batch_index=2,
                operation_id="split-existing",
            )

        self.assertEqual(len(cards), 4)
        self.assertIn(3, seen_existing_lengths)

    def test_permanent_duplicates_fail_after_bounded_budget(self):
        from app.ai.client import FlashcardProviderCallBudget

        budget = FlashcardProviderCallBudget(limit=8)

        def always_duplicate(**kwargs):
            batch_size = kwargs["batch_size"]
            cards = [{"question": "Taken?", "answer": "A."}]
            if batch_size > 1:
                cards.append({"question": "Another?", "answer": "B."})
            return json.dumps({"cards": cards})

        with patch("app.ai.flashcards.call_flashcard_batch", side_effect=always_duplicate) as provider:
            with self.assertRaises(FlashcardGenerationError) as ctx:
                generate_flashcard_batch(
                    self.source_notes,
                    self.options,
                    2,
                    ["Taken?"],
                    batch_index=2,
                    operation_id="dup-permanent",
                    provider_budget=budget,
                )

        self.assertEqual(str(ctx.exception), FLASHCARD_DUPLICATE_QUESTIONS_ERROR)
        self.assertEqual(budget.used, 8)
        self.assertGreaterEqual(provider.call_count, 1)


if __name__ == "__main__":
    unittest.main()
