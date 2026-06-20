"""Module entry point: ``python -m aegis_swr.cli``.

Mirrors the ``aegis`` console-script entry point (``commands:app``) so the CLI
can also be launched by executing the package directly with ``-m``.
"""
from aegis_swr.cli.commands import app

if __name__ == "__main__":
    app()
