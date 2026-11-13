"""Run with Python 3.11 -S to guard the shared page generator's syntax floor."""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pysaiyanweboo


class PageHeadingCompatibilityTests(unittest.TestCase):
    def test_all_heading_levels_preserve_class_and_escape_text(self):
        for level in range(1, 7):
            with self.subTest(level=level):
                classes = ' class="ui-title"' if level == 1 else ''
                document = pysaiyanweboo.page_document({
                    'schema': 'web-ui-page/1', 'title': 'Test',
                    'blocks': [{'type': 'heading', 'level': level,
                                'text': '<日本語 & "title">'}],
                })
                expected = f'<h{level}{classes}>&lt;日本語 &amp; &quot;title&quot;&gt;</h{level}>'
                self.assertIn(expected, document)

    def test_invalid_heading_levels_still_fail(self):
        for level in (0, 7, True, '1'):
            with self.subTest(level=level), self.assertRaises(ValueError):
                pysaiyanweboo.page_document({'schema': 'web-ui-page/1', 'title': 'Test',
                                      'blocks': [{'type': 'heading', 'level': level, 'text': 'x'}]})


if __name__ == '__main__':
    unittest.main()
