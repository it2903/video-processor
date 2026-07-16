from types import SimpleNamespace
from unittest.mock import patch
import unittest

from app.models import const
from app.models.schema import TaskVideoRequest
from app.services import video_runs


class TestVideoRuns(unittest.TestCase):
    def test_video_run_payload_contains_scope_and_generation_snapshot(self):
        params = TaskVideoRequest(
            video_subject="Nuevo producto",
            video_language="es",
            video_aspect="9:16",
            video_source="pexels",
            voice_name="es-CO-SalomeNeural-Female",
        )

        payload = video_runs.build_run_insert_payload(
            workspace_id="11111111-1111-1111-1111-111111111111",
            user_id="22222222-2222-2222-2222-222222222222",
            created_by="22222222-2222-2222-2222-222222222222",
            title="Lanzamiento",
            request_id="request-1",
            task_id="task-1",
            params=params,
            parent_run_id=None,
        )

        self.assertEqual(payload["workspace_id"], "11111111-1111-1111-1111-111111111111")
        self.assertEqual(payload["user_id"], "22222222-2222-2222-2222-222222222222")
        self.assertEqual(payload["mpt_task_id"], "task-1")
        self.assertEqual(payload["video_subject"], "Nuevo producto")
        self.assertEqual(payload["request_payload"]["video_count"], 1)
        self.assertEqual(payload["effective_params"]["video_aspect"], "9:16")

    def test_sync_completed_task_records_artifacts_and_updates_run(self):
        run = {
            "id": "33333333-3333-3333-3333-333333333333",
            "workspace_id": "11111111-1111-1111-1111-111111111111",
            "user_id": "22222222-2222-2222-2222-222222222222",
            "mpt_task_id": "task-1",
            "status": "running",
        }
        task = {
            "state": const.TASK_STATE_COMPLETE,
            "progress": 100,
            "script": "Este es el guion",
            "terms": ["launch", "product"],
            "storage_results": [
                {
                    "bucket": "mpt-videos",
                    "object_path": "11111111-1111-1111-1111-111111111111/22222222-2222-2222-2222-222222222222/33333333-3333-3333-3333-333333333333/videos/final-1.mp4",
                    "size": 1234,
                    "content_type": "video/mp4",
                }
            ],
        }

        with (
            patch.object(video_runs.supabase_domain, "update_row", return_value={}) as update_row,
            patch.object(video_runs.supabase_domain, "upsert_row", return_value={}) as upsert_row,
            patch.object(video_runs.supabase_domain, "insert_row", return_value={}) as insert_row,
        ):
            result = video_runs.sync_task_to_run(run, task)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(update_row.call_args.args[0], "mpt_video_runs")
        updated_payload = update_row.call_args.args[2]
        self.assertEqual(updated_payload["generated_script"], "Este es el guion")
        self.assertEqual(updated_payload["generated_terms"], ["launch", "product"])
        artifact_payload = upsert_row.call_args.args[1]
        self.assertEqual(artifact_payload["artifact_type"], "video")
        self.assertEqual(artifact_payload["workspace_id"], run["workspace_id"])
        self.assertTrue(artifact_payload["storage_path"].startswith(run["workspace_id"]))
        inserted_tables = [call.args[0] for call in insert_row.call_args_list]
        self.assertIn("mpt_generation_events", inserted_tables)
        self.assertIn("mpt_usage_records", inserted_tables)

    def test_record_llm_generation_records_event_and_usage(self):
        with patch.object(video_runs.supabase_domain, "insert_row", return_value={}) as insert_row:
            video_runs.record_llm_generation(
                workspace_id="11111111-1111-1111-1111-111111111111",
                user_id="22222222-2222-2222-2222-222222222222",
                run_id=None,
                operation="script_generation",
                event_type="script_generated",
                input_summary={"video_subject": "Nuevo producto"},
                output_summary={"script_length": 42},
                input_characters=14,
                output_characters=42,
            )

        event_payload = insert_row.call_args_list[0].args[1]
        usage_payload = insert_row.call_args_list[1].args[1]
        self.assertEqual(event_payload["event_type"], "script_generated")
        self.assertEqual(event_payload["workspace_id"], "11111111-1111-1111-1111-111111111111")
        self.assertEqual(usage_payload["operation"], "script_generation")
        self.assertEqual(usage_payload["usage_source"], "estimated")

    def test_get_run_attaches_signed_video_artifacts(self):
        run = {
            "id": "33333333-3333-3333-3333-333333333333",
            "workspace_id": "11111111-1111-1111-1111-111111111111",
            "status": "completed",
        }
        artifact = {
            "id": "artifact-1",
            "run_id": run["id"],
            "storage_bucket": "mpt-videos",
            "storage_path": f"{run['workspace_id']}/user/{run['id']}/videos/final-1.mp4",
            "original_url": "",
            "file_name": "final-1.mp4",
        }

        with (
            patch.object(video_runs.supabase_domain, "select_row", return_value=run),
            patch.object(video_runs.supabase_domain, "select_rows", return_value=[artifact]),
            patch.object(
                video_runs.supabase_storage,
                "create_signed_url",
                return_value="https://signed.example/final-1.mp4",
            ),
        ):
            result = video_runs.get_run(run["id"])

        self.assertIsNotNone(result)
        self.assertEqual(result["artifacts"][0]["file_name"], "final-1.mp4")
        self.assertEqual(
            result["artifacts"][0]["signed_url"],
            "https://signed.example/final-1.mp4",
        )
