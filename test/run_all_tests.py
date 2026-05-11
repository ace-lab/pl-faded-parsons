import subprocess
import sys
import os
import unittest
from pathlib import Path


ELEMENT_DIR = Path(__file__).resolve().parent.parent
TEST_DIR = ELEMENT_DIR / "test"


def run_python_tests() -> bool:
    os.chdir(ELEMENT_DIR)
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(TEST_DIR),
        pattern="test*.py",
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return result.wasSuccessful()


def run_browser_tests() -> bool:
    if not (ELEMENT_DIR / "node_modules").exists() and not (ELEMENT_DIR / ".pnp.cjs").exists():
        print(
            "Install browser test dependencies with `yarn install` in pl-faded-parsons.",
            file=sys.stderr,
        )
        return False

    try:
        browser_env = os.environ.copy()
        browser_env.setdefault("COREPACK_HOME", str(ELEMENT_DIR / ".cache" / "corepack"))
        browser_env.setdefault("XDG_CACHE_HOME", str(ELEMENT_DIR / ".cache"))
        completed = subprocess.run(
            ["yarn", "test:browser"],
            cwd=str(ELEMENT_DIR),
            env=browser_env,
            check=False,
        )
    except FileNotFoundError:
        print("yarn is required to run the browser test suite.", file=sys.stderr)
        return False
    return completed.returncode == 0


def main() -> int:
    python_ok = run_python_tests()
    browser_ok = run_browser_tests()
    return 0 if python_ok and browser_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
