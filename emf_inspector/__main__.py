"""
Entry point for: python -m emf_inspector

Launches the EMF Inspector GUI application.
"""

import sys
from pathlib import Path


def main():
    """Launch the EMF Inspector GUI."""
    # Ensure the project root is importable so that 'main' module
    # can be found both when running from source and when pip-installed.
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from main import main as _main
        _main()
    except ImportError:
        # Fallback: if main.py is not at project root (e.g. pip install),
        # try to import from emf_inspector.ui if it exists, otherwise
        # print a helpful error message.
        print(
            "Error: Could not find the GUI module.\n"
            "If you installed via pip, please run from the project directory:\n"
            "  cd <project-root> && python -m emf_inspector\n"
            "Or run directly:\n"
            "  python main.py",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
