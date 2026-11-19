"""Import a polling-unit register from the command line (large files, scripted setups).

    .venv/bin/python -m app.directory.import_csv register.csv --source "INEC polling units, 2023"

Add --dry-run to validate without writing. The import is recorded in the audit log
as a system action."""

import argparse
import sys
from pathlib import Path

from app.directory.importer import import_register
from app.evidence.db import evidence_session_factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", type=Path)
    parser.add_argument("--source", required=True, help="Where the register came from")
    parser.add_argument("--reference", help="Document reference or URL")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    with evidence_session_factory()() as db:
        report = import_register(
            db,
            args.file.read_bytes(),
            source_name=args.source,
            source_reference=args.reference,
            actor_id=None,
            filename=args.file.name,
            dry_run=args.dry_run,
        )
    if report.error_count:
        print(f"Rejected: {report.error_count} problem(s). Nothing was written.", file=sys.stderr)
        for error in report.errors:
            print(f"  row {error.row}: {error.message}", file=sys.stderr)
        return 1
    print(
        f"{'Validated' if args.dry_run else 'Imported'} {report.rows} rows: "
        f"{report.states_created} states, {report.lgas_created} LGAs, "
        f"{report.wards_created} wards and {report.units_created} polling units created; "
        f"{report.units_updated} updated, {report.units_unchanged} unchanged."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
