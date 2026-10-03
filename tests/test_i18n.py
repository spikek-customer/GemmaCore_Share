"""
tests/test_i18n.py - Automated Test Suite for Enterprise Multi-language (i18n) & Readability (TEST-053)
Verifies dictionary integrity across Japanese, English, and Traditional Chinese, DOM binding attributes, and static asset serving.
"""

import json
import os
import re
import shutil
import subprocess
import unittest
from src.web.app import KnowledgeWebApp


class TestEnterpriseI18n(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.web_app = KnowledgeWebApp()
        cls.static_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "src", "web", "static")
        )
        cls.i18n_path = os.path.join(cls.static_dir, "i18n.js")
        cls.html_path = os.path.join(cls.static_dir, "index.html")
        cls.css_path = os.path.join(cls.static_dir, "style.css")

    def test_i18n_file_existence_and_structure(self) -> None:
        """TEST-053-01: Verify i18n.js exists and contains dictionary objects for ja, en, zh-TW."""
        self.assertTrue(os.path.exists(self.i18n_path), "i18n.js file must exist")
        with open(self.i18n_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("ja:", content, "Japanese dictionary must be present")
        self.assertIn("en:", content, "English dictionary must be present")
        self.assertIn("'zh-TW':", content, "Traditional Chinese dictionary must be present")
        self.assertIn("setLanguage", content, "setLanguage method must exist")
        self.assertIn("updateDOM", content, "updateDOM method must exist")

    def test_i18n_dictionary_completeness(self) -> None:
        """TEST-053-02: Verify translation keys completeness between ja, en, and zh-TW."""
        with open(self.i18n_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract keys inside translations.ja block using regex
        ja_match = re.search(r"ja:\s*\{([^}]+)\}", content)
        en_match = re.search(r"en:\s*\{([^}]+)\}", content)
        zh_match = re.search(r"'zh-TW':\s*\{([^}]+)\}", content)

        self.assertIsNotNone(ja_match, "ja dictionary block found")
        self.assertIsNotNone(en_match, "en dictionary block found")
        self.assertIsNotNone(zh_match, "zh-TW dictionary block found")

        ja_keys = set(re.findall(r"([a-zA-Z0-9_]+)\s*:", ja_match.group(1)))
        en_keys = set(re.findall(r"([a-zA-Z0-9_]+)\s*:", en_match.group(1)))
        zh_keys = set(re.findall(r"([a-zA-Z0-9_]+)\s*:", zh_match.group(1)))

        self.assertTrue(len(ja_keys) > 30, f"ja dict should have >30 keys, got {len(ja_keys)}")
        missing_in_en = ja_keys - en_keys
        missing_in_zh = ja_keys - zh_keys

        self.assertEqual(missing_in_en, set(), f"Keys missing in English dict: {missing_in_en}")
        self.assertEqual(missing_in_zh, set(), f"Keys missing in Traditional Chinese dict: {missing_in_zh}")

    def test_index_html_i18n_annotations(self) -> None:
        """TEST-053-03: Verify index.html includes i18n.js, lang selector, and data-i18n attributes."""
        with open(self.html_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('<script src="i18n.js"></script>', content, "index.html must include i18n.js script tag")
        self.assertIn('id="lang-selector"', content, "index.html must contain language selector dropdown")
        self.assertIn('data-i18n=', content, "index.html must contain data-i18n attributes")
        self.assertIn('value="zh-TW"', content, "Language selector must include Traditional Chinese option")

    def test_style_css_multilingual_typography(self) -> None:
        """TEST-053-04: Verify style.css includes typography and text-wrap optimization rules."""
        with open(self.css_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn(".lang-select", content, "style.css must contain .lang-select styling")
        self.assertIn(":lang(zh-TW)", content, "style.css must contain Traditional Chinese font styling")
        self.assertIn("word-break", content, "style.css must contain word-break rules for text overflow prevention")

    def test_web_static_asset_serving(self) -> None:
        """TEST-053-05: Verify static i18n.js file content is accessible and valid."""
        with open(self.i18n_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("I18nEngine", content, "i18n.js content must define I18nEngine")

    def test_i18n_assets_public_before_login(self) -> None:
        """TEST-053-09: i18n assets must be served without auth (login screen needs them)."""
        start_web = os.path.join(os.path.dirname(__file__), "..", "scripts", "start_web.py")
        with open(start_web, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn('"/i18n.js"', src)
        self.assertIn('"/i18n_phrases.js"', src)

    def test_phrase_table_included_before_engine(self) -> None:
        """TEST-053-06: index.html loads i18n_phrases.js before i18n.js and the phrase file exists."""
        phrases = os.path.join(self.static_dir, "i18n_phrases.js")
        self.assertTrue(os.path.exists(phrases), "i18n_phrases.js must exist")
        with open(self.html_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertLess(html.index("i18n_phrases.js"), html.index('src="i18n.js"'))
        self.assertLess(html.index('src="i18n.js"'), html.index('src="app.js"'))

    def test_engine_behavior_via_node(self) -> None:
        """TEST-053-07: Run engine in Node: key parity, phrase validity, tr() translation, placeholders."""
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        script = os.path.join(os.path.dirname(__file__), "i18n_check.js")
        res = subprocess.run(
            [node, script, self.static_dir], capture_output=True, text=True, timeout=30
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout.strip().splitlines()[-1])
        self.assertEqual(data["errors"], [], f"i18n errors: {data['errors']}")
        self.assertGreater(data["phraseCount"], 200)

    def test_layout_safety_css(self) -> None:
        """TEST-053-08: style.css contains the overflow-safety rules for long EN/zh-TW strings."""
        with open(self.css_path, "r", encoding="utf-8") as f:
            css = f.read()
        for token in ("i18n Layout Safety", ".modal-buttons { flex-wrap: wrap", "overflow-wrap: anywhere"):
            self.assertIn(token, css)


if __name__ == "__main__":
    unittest.main()
