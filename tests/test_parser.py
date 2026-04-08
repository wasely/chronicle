from __future__ import annotations

import unittest
from datetime import UTC, datetime

from bot.parser import extract_duration_minutes, extract_future_offset, infer_category, infer_tags, parse_activity, strip_duration_phrases


NOW = datetime(2026, 4, 6, 18, 0, tzinfo=UTC)


class ParserTests(unittest.TestCase):
    def test_for_two_hours(self):
        self.assertEqual(extract_duration_minutes("coding for 2 hours"), 120)

    def test_short_h_format(self):
        self.assertEqual(extract_duration_minutes("deep work 2h"), 120)

    def test_minutes_format(self):
        self.assertEqual(extract_duration_minutes("walk 45 min"), 45)

    def test_tilde_hour(self):
        self.assertEqual(extract_duration_minutes("~1hr reading"), 60)

    def test_past_hour(self):
        self.assertEqual(extract_duration_minutes("past hour debugging"), 60)

    def test_last_thirty_minutes(self):
        self.assertEqual(extract_duration_minutes("last 30 minutes email"), 30)

    def test_fallback_duration(self):
        self.assertEqual(extract_duration_minutes("coding", 25), 25)

    def test_future_offset_not_treated_as_duration(self):
        self.assertEqual(extract_duration_minutes("in 20 minutes eat dinner for 30 min"), 30)

    def test_mixed_case_exercise(self):
        self.assertEqual(infer_category("Went for a RUN outside"), "Exercise")

    def test_meals_category(self):
        self.assertEqual(infer_category("Lunch with a client"), "Meals")

    def test_sleep_category(self):
        self.assertEqual(infer_category("Going to bed early"), "Sleep")

    def test_learning_category(self):
        self.assertEqual(infer_category("Watched tutorial and read book"), "Learning")

    def test_ambiguous_work_vs_meeting(self):
        self.assertEqual(infer_category("Client meeting and report writing"), "Work")

    def test_unrecognized_defaults_personal(self):
        self.assertEqual(infer_category("just vibing"), "Personal")

    def test_tags_detected(self):
        tags = infer_tags("Coding deployment after standup meeting")
        self.assertIn("coding", tags)
        self.assertIn("meeting", tags)

    def test_strip_duration(self):
        self.assertEqual(strip_duration_phrases("coding for 2 hours"), "coding")

    def test_parse_activity_fields(self):
        activity = parse_activity("writing report for 90 min", now=NOW)
        self.assertEqual(activity["duration"], 90)
        self.assertEqual(activity["category"], "Work")
        self.assertEqual(activity["title"], "writing report")

    def test_extract_future_offset(self):
        self.assertEqual(extract_future_offset("in 20 minutes eat dinner").total_seconds(), 20 * 60)

    def test_parse_future_activity(self):
        activity = parse_activity("in 20 minutes i have to go eat dinner for 30 minutes", now=NOW)
        self.assertEqual(activity["duration"], 30)
        self.assertEqual(activity["start"], datetime(2026, 4, 6, 18, 20, tzinfo=UTC))
        self.assertEqual(activity["end"], datetime(2026, 4, 6, 18, 50, tzinfo=UTC))
        self.assertEqual(activity["title"], "eat dinner")
        self.assertEqual(activity["category"], "Meals")

    def test_multi_activity_string_prefers_meals(self):
        activity = parse_activity("I had lunch then went for a walk", now=NOW)
        self.assertEqual(activity["category"], "Meals")

    def test_no_recognizable_content(self):
        activity = parse_activity("...", now=NOW)
        self.assertEqual(activity["category"], "Personal")
        self.assertEqual(activity["title"], "Activity log")

    def test_duration_capped_minimum(self):
        self.assertEqual(extract_duration_minutes("1m"), 5)

    def test_duration_capped_maximum(self):
        self.assertEqual(extract_duration_minutes("99h"), 16 * 60)


if __name__ == "__main__":
    unittest.main()
