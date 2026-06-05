from __future__ import annotations

import argparse

from wincrash_analyzer.config import CONFIG_DEFAULT_PATH, get_option
from wincrash_analyzer.core.crash_app import CrashApp


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def _validate_dump_path(path: str) -> str:
    """
    Ensure *path* ends with '.dmp'; raise :class:`argparse.ArgumentTypeError` otherwise.

    @param path: The file path to validate.
    @return: The validated path string.
    @raises argparse.ArgumentTypeError: If the path does not end with '.dmp'.
    """
    if not path.lower().endswith(".dmp"):
        raise argparse.ArgumentTypeError(
            f"Invalid dump file '{path}': expected a '.dmp' extension."
        )
    return path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def create_parser() -> tuple[argparse.ArgumentParser, argparse.ArgumentParser, argparse.ArgumentParser]:
    """
    Create and configure the main argument parser and its subparsers.

    @return: A tuple containing the main parser, analyze subparser, and export subparser.
    """
    parser = argparse.ArgumentParser(
        description="WinCrash AI Analyzer – automated crash dump Root Cause Analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  wincrash-analyzer analyze --dump crash.dmp --sym C:\\Symbols\n"
            "  wincrash-analyzer export --to-store sqlite --to-store-config data.sqlite\n"
        ),
    )

    # Common options
    opt_severity = get_option("report_severity")
    parser.add_argument(
        opt_severity.cli_name,
        default=opt_severity.default,
        choices=opt_severity.choices,
        help=opt_severity.help,
    )
    parser.add_argument(
        "--config-file",
        nargs='?',
        const=CONFIG_DEFAULT_PATH,
        help=f"Path to JSON config file (default: {CONFIG_DEFAULT_PATH}). If used, other CLI options are ignored.",
    )
    parser.add_argument(
        "--save-config",
        action="store_true",
        help="Save current configuration to default config file and exit.",
    )

    subparsers = parser.add_subparsers(dest="action", help="Actions")

    # Analyze subparser
    analyze_parser = subparsers.add_parser(
        "analyze", 
        help="Analyze crash dump",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Analyze crash dump and generate a root cause report."
    )
    
    opt_dump = get_option("dump")
    analyze_parser.add_argument(
        opt_dump.cli_name,
        required=False,
        type=_validate_dump_path,
        help=opt_dump.help,
    )
    
    opt_sym = get_option("sym")
    analyze_parser.add_argument(
        opt_sym.cli_name,
        required=False,
        help=opt_sym.help
    )
    
    opt_log = get_option("log_source")
    analyze_parser.add_argument(
        opt_log.cli_name,
        required=False,
        help=opt_log.help
    )
    
    opt_engine = get_option("engine")
    analyze_parser.add_argument(
        opt_engine.cli_name,
        default=opt_engine.default,
        choices=opt_engine.choices,
        help=opt_engine.help,
    )
    
    opt_ai = get_option("ai")
    analyze_parser.add_argument(
        opt_ai.cli_name,
        default=opt_ai.default,
        choices=opt_ai.choices,
        help=opt_ai.help,
    )
    
    opt_cdb = get_option("cdb_path")
    analyze_parser.add_argument(
        opt_cdb.cli_name,
        default=opt_cdb.default,
        help=opt_cdb.help,
    )
    
    opt_hist = get_option("analyze_history")
    analyze_parser.add_argument(
        opt_hist.cli_name,
        action="store_true",
        help=opt_hist.help,
    )
    
    opt_store = get_option("store")
    analyze_parser.add_argument(
        opt_store.cli_name,
        default=opt_store.default,
        choices=opt_store.choices,
        help=opt_store.help,
    )
    
    opt_store_cfg = get_option("store_config")
    analyze_parser.add_argument(
        opt_store_cfg.cli_name,
        required=False,
        default=opt_store_cfg.default,
        help=opt_store_cfg.help
    )

    opt_assumption = get_option("assumption")
    analyze_parser.add_argument(
        opt_assumption.cli_name,
        required=False,
        default=opt_assumption.default,
        help=opt_assumption.help,
    )

    # Export subparser
    export_parser = subparsers.add_parser(
        "export", 
        help="Export analysis records",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Export analysis records between different storage backends."
    )
    
    # Source store for export
    export_parser.add_argument(
        opt_store.cli_name,
        default=opt_store.default,
        choices=opt_store.choices,
        help="Source storage backend (default: filesystem)",
    )
    export_parser.add_argument(
        opt_store_cfg.cli_name,
        required=False,
        default=opt_store_cfg.default,
        help="Source store configuration"
    )
    
    # Destination store for export
    opt_to_store = get_option("to_store")
    export_parser.add_argument(
        opt_to_store.cli_name,
        required=True,
        choices=opt_to_store.choices,
        help=opt_to_store.help,
    )
    
    opt_to_store_cfg = get_option("to_store_config")
    export_parser.add_argument(
        opt_to_store_cfg.cli_name,
        help=opt_to_store_cfg.help,
    )

    # Collect subparser help messages
    subparsers_help = ""
    for name, subparser in [("analyze", analyze_parser), ("export", export_parser)]:
        subparsers_help += f"\n{'-'*80}\n"
        subparsers_help += f"Help for '{name}' action:\n"
        
        # We want to skip the usage line(s) but keep the description and options.
        # format_help() returns something like:
        # usage: cli.py analyze [-h] ...
        #
        # description
        #
        # options:
        #   ...
        help_text = subparser.format_help()
        parts = help_text.split('\n\n', 1)
        if len(parts) > 1:
            body = parts[1]
            subparsers_help += "\n".join("  " + line for line in body.splitlines())
        else:
            subparsers_help += "\n".join("  " + line for line in help_text.splitlines()[2:])
        subparsers_help += "\n"

    parser.epilog = (
        "Examples:\n"
        "  wincrash-analyzer analyze --dump crash.dmp --sym C:\\Symbols\n"
        "  wincrash-analyzer export --to-store sqlite --to-store-config data.sqlite\n"
        f"{subparsers_help}"
    )

    return parser, analyze_parser, export_parser


def main():
    """
    The main entry point for the CLI application.
    """
    parser, analyze_parser, export_parser = create_parser()
    app = CrashApp(parser, analyze_parser, export_parser)
    app.run()


if __name__ == "__main__":
    main()
