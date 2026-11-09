"""Permite correr: python -m osuctools limpios RUTA"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
