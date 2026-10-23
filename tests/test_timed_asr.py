"""ASR timing is never fabricated from text-only responses."""
import unittest

from video_clips.timed_asr import TimedASRError, captions_from_step_file


class TimedASRTests(unittest.TestCase):
    def setUp(self):
        self.result = {"duration": 2.4, "result": [{"text": "你好。再次见面。", "utterances": [
            {"text": "你好。", "start_time": 0, "end_time": 800,
             "words": [{"text": "你", "start_time": 0, "end_time": 200}]},
            {"text": "再次见面。", "start_time": 1200, "end_time": 2400},
        ]}]}

    def test_conversion_preserves_milliseconds(self):
        captions = captions_from_step_file(self.result)
        self.assertEqual([(c.text, c.start_ms, c.end_ms) for c in captions], [
            ("你好。", 0, 800), ("再次见面。", 1200, 2400)])

    def test_text_only_response_is_rejected(self):
        with self.assertRaisesRegex(TimedASRError, "result"):
            captions_from_step_file({"text": "你好"})
        with self.assertRaisesRegex(TimedASRError, "utterances"):
            captions_from_step_file({"result": [{"text": "你好"}]})

    def test_missing_timestamp_is_rejected(self):
        self.result["result"][0]["utterances"][0].pop("end_time")
        with self.assertRaises(TimedASRError):
            captions_from_step_file(self.result)

    def test_boolean_timestamp_is_rejected(self):
        self.result["result"][0]["utterances"][0]["start_time"] = True
        with self.assertRaises(TimedASRError):
            captions_from_step_file(self.result)

    def test_overlap_is_rejected(self):
        self.result["result"][0]["utterances"][1]["start_time"] = 500
        with self.assertRaisesRegex(TimedASRError, "overlap"):
            captions_from_step_file(self.result)

    def test_multi_channel_selection(self):
        self.result["result"].append({"text": "第二条轨道", "utterances": [
            {"text": "第二条轨道", "start_time": 100, "end_time": 900}]})
        with self.assertRaisesRegex(TimedASRError, "multiple ASR channels"):
            captions_from_step_file(self.result)
        self.assertEqual(captions_from_step_file(self.result, channel=1)[0].text, "第二条轨道")
        with self.assertRaisesRegex(TimedASRError, "out of range"):
            captions_from_step_file(self.result, channel=2)

    def test_pending_result_is_rejected(self):
        self.result["status"] = "RUNNING"
        with self.assertRaisesRegex(TimedASRError, "not completed"):
            captions_from_step_file(self.result)

    def test_zero_duration_is_rejected(self):
        self.result["result"][0]["utterances"][0]["end_time"] = 0
        with self.assertRaises(TimedASRError):
            captions_from_step_file(self.result)


if __name__ == "__main__":
    unittest.main()
