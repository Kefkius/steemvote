import unittest

from steemvote.config import get_decimal

class DecimalTest(unittest.TestCase):
    def test_float(self):
        for data, expected in [
            (0.5, 0.5),
        ]:
            self.assertEqual(expected, get_decimal(data))

    def test_string(self):
        for data, expected in [
            ('0.5', 0.5),
            ('50%', 0.5),
            ('100%', 1.0),
        ]:
            self.assertEqual(expected, get_decimal(data))
