"""Allow ``python -m whisper_free`` execution."""

import sys

from whisper_free.main import main

if __name__ == "__main__":
    sys.exit(main())
