from unittest.mock import Mock, patch
import unittest

from app.config import config
from app.services import supabase_domain


class TestSupabaseDomainClient(unittest.TestCase):
    def setUp(self):
        self.original_app = dict(config.app)

    def tearDown(self):
        config.app.clear()
        config.app.update(self.original_app)

    def test_supabase_domain_is_disabled_without_service_role_key(self):
        config.app["supabase_url"] = "https://example.supabase.co"
        config.app["supabase_service_role_key"] = ""

        self.assertFalse(supabase_domain.is_configured())
        self.assertEqual(
            supabase_domain.insert_row("mpt_video_runs", {"status": "queued"}), {}
        )

    def test_insert_row_uses_postgrest_service_role_headers(self):
        config.app["supabase_url"] = "https://example.supabase.co/"
        config.app["supabase_service_role_key"] = "service-secret"
        response = Mock(status_code=201)
        response.json.return_value = [{"id": "run-1"}]

        with patch.object(supabase_domain.requests, "request", return_value=response) as request:
            result = supabase_domain.insert_row("mpt_video_runs", {"status": "queued"})

        self.assertEqual(result, {"id": "run-1"})
        method, url = request.call_args.args[:2]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://example.supabase.co/rest/v1/mpt_video_runs")
        headers = request.call_args.kwargs["headers"]
        self.assertEqual(headers["apikey"], "service-secret")
        self.assertEqual(headers["Authorization"], "Bearer service-secret")
        self.assertEqual(headers["Prefer"], "return=representation")

    def test_upsert_row_sets_on_conflict_and_merge_preference(self):
        config.app["supabase_url"] = "https://example.supabase.co"
        config.app["supabase_service_role_key"] = "service-secret"
        response = Mock(status_code=200)
        response.json.return_value = [{"id": "artifact-1"}]

        with patch.object(supabase_domain.requests, "request", return_value=response) as request:
            result = supabase_domain.upsert_row(
                "mpt_video_artifacts",
                {"storage_path": "workspace/run/final.mp4"},
                on_conflict="storage_bucket,storage_path",
            )

        self.assertEqual(result, {"id": "artifact-1"})
        self.assertEqual(
            request.call_args.kwargs["params"],
            {"on_conflict": "storage_bucket,storage_path"},
        )
        self.assertEqual(
            request.call_args.kwargs["headers"]["Prefer"],
            "resolution=merge-duplicates,return=representation",
        )
