"""A custom tool backed by a database.

Declaring ``source_type=SourceType.DATABASE`` makes every result a citable source with
provenance (tool name, arguments, timestamp, content hash). Agents can then quote
query results as verified evidence.
"""

import os
import sqlite3

from adversi import AdverSI, SourceType, Tool

db = sqlite3.connect(":memory:", check_same_thread=False)
db.executescript(
    """
    CREATE TABLE delays (month TEXT, airport TEXT, flights INT, delayed INT);
    INSERT INTO delays VALUES
      ('2025-06','ORD',41200,9900), ('2025-06','DEN',38900,7100),
      ('2025-07','ORD',42800,11600), ('2025-07','DEN',40100,7900);
    """
)


def delay_rate(airport: str, month: str) -> str:
    """Return flights, delayed flights and delay rate for an airport and month (YYYY-MM)."""
    row = db.execute(
        "SELECT flights, delayed FROM delays WHERE airport = ? AND month = ?",  # parameterised: no SQL injection
        (airport.upper(), month),
    ).fetchone()
    if row is None:
        return f"No data for {airport} {month}."
    flights, delayed = row
    return f"{airport.upper()} {month}: {flights} flights, {delayed} delayed, delay rate {delayed / flights:.3f}"


delay_tool = Tool(
    "delay_rate",
    "Look up monthly flight delay statistics for an airport.",
    delay_rate,
    source_type=SourceType.DATABASE,
    timeout_s=5,
)

ai = AdverSI(
    os.environ.get("ADVERSI_MODEL", "openai:gpt-4o-mini"),
    mode="adversarial",
    profile="fast",
    tools=[delay_tool, "calculator"],
)
result = ai.run_sync("Did ORD's delay rate get worse relative to DEN from June to July 2025?")
print(result.to_markdown())
