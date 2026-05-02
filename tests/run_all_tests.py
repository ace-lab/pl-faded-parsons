import unittest
from pathlib import Path


def main() -> int:
    test_dir = Path.cwd().resolve() / "tests"
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(test_dir),
        pattern="test*.py",
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
