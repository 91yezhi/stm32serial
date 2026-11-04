"""Entry point for ``python -m stm32serial``."""

from .cli import main

if __name__ == "__main__":  # pragma: no cover - exercised through the console script
    raise SystemExit(main())