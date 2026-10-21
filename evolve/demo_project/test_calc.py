import unittest
from calc import add, mul, avg, discount, compound

class TestCalc(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)

    def test_mul(self):
        self.assertEqual(mul(4, 5), 20)

    def test_avg(self):
        self.assertAlmostEqual(avg([1, 2, 3]), 2.0)

    def test_discount_normal(self):
        self.assertAlmostEqual(discount(100, 20), 80.0)

    def test_discount_zero(self):
        self.assertAlmostEqual(discount(50, 0), 50.0)

    def test_discount_full(self):
        self.assertAlmostEqual(discount(99, 100), 0.0)

    def test_discount_float(self):
        self.assertAlmostEqual(discount(200, 15), 170.0)

    def test_discount_negative_pct(self):
        self.assertAlmostEqual(discount(100, -10), 110.0)

    def test_compound(self):
        self.assertAlmostEqual(compound(100, 0.05, 10), 162.89, places=2)

if __name__ == "__main__":
    unittest.main()
