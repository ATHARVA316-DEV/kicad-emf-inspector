"""
Entry point for the EMF Inspector package.
Allows launching via:
  python -m emf_inspector
  emf-inspector          (after pip install)
"""

import sys
from pathlib import Path

# Ensure the package root is on the path when run as a module
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    """Main entry point."""
    from main import main as _main
    _main()


if __name__ == "__main__":
    main()
