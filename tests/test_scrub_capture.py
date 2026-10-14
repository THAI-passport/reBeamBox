import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import scrub_capture  # noqa: E402


class Scrub(unittest.TestCase):
    def test_macs_stable_and_length_kept(self):
        src = "conn A1:B2:C3:D4:E5:F6 then a1:b2:c3:d4:e5:f6 and 11-22-33-44-55-66"
        out, n, _ = scrub_capture.scrub(src)
        self.assertEqual(n, 2)
        self.assertEqual(len(out), len(src))
        self.assertEqual(out.count("02:00:00:00:00:01"), 2)
        self.assertIn("02-00-00-00-00-02", out)
        self.assertNotIn("A1:B2", out)

    def test_tokens(self):
        out, _, _ = scrub_capture.scrub('Authorization: Bearer abc.DEF-123 {"token": "zzzz9999"}')
        self.assertNotIn("abc.DEF-123", out)
        self.assertNotIn("zzzz9999", out)
        self.assertIn("Bearer xxxxxxxxxxx", out)

    def test_mask_in_hex_payload(self):
        src = '{"handle": 14, "value": "fedcba' + b"SN42".hex() + 'ef"} SN42'
        out, _, hits = scrub_capture.scrub(src, ["SN42"])
        self.assertEqual(hits, 1)
        self.assertIn('"value": "fedcba00000000ef"', out)
        self.assertTrue(out.endswith("xxxx"))
        self.assertIn('"handle": 14', out)


if __name__ == "__main__":
    unittest.main()
