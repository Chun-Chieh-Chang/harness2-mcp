import unittest

suite = unittest.defaultTestLoader.discover('.', pattern='test_*.py')
r = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if r.wasSuccessful() else 1)
