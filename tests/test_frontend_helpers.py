"""
Frontend Helpers Unit Test Suite
================================
Validates frontend file icon resolution, status indicators, and fallback behavior.
"""

import unittest
from frontend.utils import get_file_icon, get_status_indicator, get_intent_badge, format_bytes

class TestFrontendHelpers(unittest.TestCase):
    """Test file format icon and status indicator helpers."""

    def test_file_format_icons(self):
        test_cases = [
            ("report.pdf", "📕"),
            ("notes.docx", "📝"),
            ("readme.txt", "📄"),
            ("guide.md", "📝"),
            ("document.markdown", "📝"),
            ("data.csv", "📊"),
            ("metrics.tsv", "📊"),
            ("sheet.xlsx", "📗"),
            ("legacy.xls", "📗"),
            ("payload.json", "🔢"),
            ("stream.jsonl", "🔢"),
            ("stream.ndjson", "🔢"),
            ("catalog.xml", "🧩"),
            ("index.html", "🌐"),
            ("page.htm", "🌐"),
            ("analytics.parquet", "⚡"),
            ("analytics.pq", "⚡"),
            ("data.feather", "🪶"),
            ("data.arrow", "🪶"),
            ("config.yaml", "⚙️"),
            ("config.yml", "⚙️"),
            ("schema.sql", "🗄️"),
            ("letter.rtf", "📄"),
            # Extensions directly
            (".pdf", "📕"),
            ("pdf", "📕"),
            (".csv", "📊"),
            (".xlsx", "📗"),
            # Unknown / Fallback
            ("unknown_file", "📄"),
            ("archive.zip", "📄"),
            ("", "📄"),
            (None, "📄"),
        ]

        for input_val, expected_icon in test_cases:
            icon = get_file_icon(input_val)
            self.assertEqual(icon, expected_icon, f"Failed for input '{input_val}': expected {expected_icon}, got {icon}")

    def test_status_indicators(self):
        self.assertIn("🟢", get_status_indicator("completed"))
        self.assertIn("🟢", get_status_indicator("COMPLETED"))
        self.assertIn("🟡", get_status_indicator("processing"))
        self.assertIn("🔴", get_status_indicator("failed"))
        self.assertIn("🔴", get_status_indicator("ERROR"))
        self.assertIn("🔵", get_status_indicator("uploaded"))
        self.assertIn("⚪", get_status_indicator("pending"))
        self.assertIn("⚪", get_status_indicator("unknown_status"))
        self.assertIn("⚪", get_status_indicator(None))

    def test_intent_badges(self):
        self.assertEqual(get_intent_badge("AUTHENTICATION"), "🔐 AUTHENTICATION")
        self.assertEqual(get_intent_badge("QueryIntent.AUTHENTICATION"), "🔐 AUTHENTICATION")
        self.assertEqual(get_intent_badge("DEPENDENCY"), "📦 DEPENDENCY")
        self.assertEqual(get_intent_badge("API_ROUTES"), "🌐 API_ROUTES")
        self.assertEqual(get_intent_badge("ARCHITECTURE"), "🏛️ ARCHITECTURE")
        self.assertEqual(get_intent_badge("SCHEMA"), "📊 SCHEMA")
        self.assertEqual(get_intent_badge("DATA_FLOW"), "⚡ DATA_FLOW")
        self.assertEqual(get_intent_badge("GENERAL"), "🔍 GENERAL")
        self.assertEqual(get_intent_badge(None), "🔍 GENERAL")

    def test_format_bytes(self):
        self.assertEqual(format_bytes(0), "0.0 KB")
        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(format_bytes(51200), "50.0 KB")
        self.assertEqual(format_bytes(1048576), "1.00 MB")
        self.assertEqual(format_bytes(2097152), "2.00 MB")
        self.assertEqual(format_bytes(None), "0 KB")


if __name__ == "__main__":
    unittest.main()
