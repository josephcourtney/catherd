from __future__ import annotations

import grimp


def main() -> int:
    g = grimp.build_graph("borh")

    for importer in sorted(g.modules):
        imported = sorted(g.find_modules_directly_imported_by(importer))
        for imp in imported:
            details = g.get_import_details(importer=importer, imported=imp)
            for d in details:
                ln = d.get("line_number")
                src = d.get("line_contents")
                if ln is not None:
                    print(f"{importer} -> {imp} @ l.{ln}: {src}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
