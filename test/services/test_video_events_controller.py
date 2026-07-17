from unittest.mock import Mock, patch
import unittest

from app.controllers.v1 import video as video_controller


class TestVideoRunEventsController(unittest.TestCase):
    def test_list_events_does_not_load_run_artifacts(self):
        events = [{"id": "event-2", "event_type": "script_completed"}]

        with (
            patch.object(video_controller.video_run_service, "get_run") as get_run,
            patch.object(
                video_controller.video_run_service,
                "list_run_events",
                return_value=events,
            ) as list_run_events,
        ):
            response = video_controller.list_video_run_events(
                Mock(),
                run_id="run-1",
                limit=25,
            )

        get_run.assert_not_called()
        list_run_events.assert_called_once_with(
            "run-1",
            limit=25,
        )
        self.assertEqual(response["status"], 200)
        self.assertEqual(response["data"]["events"], events)


if __name__ == "__main__":
    unittest.main()
