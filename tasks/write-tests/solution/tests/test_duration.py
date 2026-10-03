import unittest

from duration import parse_duration


class ParseDurationTest(unittest.TestCase):
    def test_single_units(self):
        self.assertEqual(parse_duration("45s"), 45)
        self.assertEqual(parse_duration("3m"), 180)
        self.assertEqual(parse_duration("2h"), 7200)

    def test_combined(self):
        self.assertEqual(parse_duration("1h30m"), 5400)
        self.assertEqual(parse_duration("2h5s"), 7205)
        self.assertEqual(parse_duration("1h1m1s"), 3661)

    def test_whitespace(self):
        self.assertEqual(parse_duration("  10m  "), 600)

    def test_invalid(self):
        for bad in ["", "   ", "5", "1x", "30m1h", "-5s", "h"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_duration(bad)


if __name__ == "__main__":
    unittest.main()
