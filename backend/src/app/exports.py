"""Tabular data ready to be written as CSV.

Kept apart from the report builders so a module that only needs the export
shape — such as staffing — can import it without pulling every report query
(and every model those queries touch) into the process.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExportTable:
    title: str
    headers: list[str]
    rows: list[list[str]]
