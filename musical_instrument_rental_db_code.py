# ============================================================
# MUSICAL INSTRUMENT RENTAL AND CONDITION TRACKING
# Original synthetic data using Python's standard library
# ============================================================

import sqlite3
import random
from datetime import date, timedelta
from pathlib import Path

rng = random.Random(3398)

DB_PATH = Path("musical_instrument_rental.db")
REFERENCE_DATE = date(2025, 10, 12)

# Rerunning replaces only this project's generated database.
if DB_PATH.exists():
    DB_PATH.unlink()

db = sqlite3.connect(DB_PATH)
db.execute("PRAGMA foreign_keys = ON")


# ============================================================
# 1. CREATE FIVE RELATED TABLES
# ============================================================

db.executescript("""
CREATE TABLE instruments (
    instrument_id INTEGER PRIMARY KEY,
    asset_code TEXT NOT NULL UNIQUE
        CHECK(length(trim(asset_code)) > 0),
    instrument_name TEXT NOT NULL
        CHECK(length(trim(instrument_name)) > 0),
    instrument_family TEXT NOT NULL
        CHECK(instrument_family IN (
            'String', 'Woodwind', 'Brass', 'Percussion', 'Keyboard'
        )),
    brand TEXT NOT NULL CHECK(length(trim(brand)) > 0),
    purchase_year INTEGER NOT NULL
        CHECK(typeof(purchase_year) = 'integer'
              AND purchase_year BETWEEN 2010 AND 2025),
    purchase_cost REAL NOT NULL CHECK(purchase_cost > 0),
    daily_fee REAL NOT NULL CHECK(daily_fee > 0)
);

CREATE TABLE rental_agreements (
    agreement_id INTEGER PRIMARY KEY,
    start_date TEXT NOT NULL
        CHECK(date(start_date) IS NOT NULL
              AND start_date = date(start_date)),
    planned_return_date TEXT NOT NULL
        CHECK(date(planned_return_date) IS NOT NULL
              AND planned_return_date = date(planned_return_date)),
    actual_return_date TEXT
        CHECK(actual_return_date IS NULL OR (
            date(actual_return_date) IS NOT NULL
            AND actual_return_date = date(actual_return_date)
        )),
    agreement_status TEXT NOT NULL
        CHECK(agreement_status IN ('Active', 'Returned')),
    deposit_amount REAL NOT NULL CHECK(deposit_amount >= 0),

    CHECK(planned_return_date > start_date),
    CHECK(actual_return_date IS NULL OR actual_return_date >= start_date),
    CHECK(
        (agreement_status = 'Active' AND actual_return_date IS NULL)
        OR
        (agreement_status = 'Returned' AND actual_return_date IS NOT NULL)
    )
);

CREATE TABLE agreement_instruments (
    agreement_id INTEGER NOT NULL
        REFERENCES rental_agreements(agreement_id) ON DELETE RESTRICT,
    instrument_id INTEGER NOT NULL
        REFERENCES instruments(instrument_id) ON DELETE RESTRICT,
    agreed_daily_fee REAL NOT NULL CHECK(agreed_daily_fee > 0),
    rental_days INTEGER NOT NULL
        CHECK(typeof(rental_days) = 'integer' AND rental_days > 0),

    PRIMARY KEY (agreement_id, instrument_id)
);

CREATE TABLE condition_inspections (
    agreement_id INTEGER NOT NULL,
    instrument_id INTEGER NOT NULL,
    inspection_stage TEXT NOT NULL
        CHECK(inspection_stage IN ('Checkout', 'Return')),
    inspected_at TEXT NOT NULL
        CHECK(datetime(inspected_at) IS NOT NULL
              AND inspected_at = datetime(inspected_at)),
    condition_grade TEXT NOT NULL
        CHECK(condition_grade IN ('Poor', 'Fair', 'Good', 'Excellent')),
    room_temperature_c REAL
        CHECK(room_temperature_c BETWEEN 10 AND 35),
    damage_notes TEXT,

    PRIMARY KEY (
        agreement_id, instrument_id, inspection_stage
    ),

    FOREIGN KEY (agreement_id, instrument_id)
        REFERENCES agreement_instruments(agreement_id, instrument_id)
        ON DELETE RESTRICT
);

CREATE TABLE maintenance_tasks (
    maintenance_id INTEGER PRIMARY KEY,
    instrument_id INTEGER NOT NULL
        REFERENCES instruments(instrument_id) ON DELETE RESTRICT,
    reported_date TEXT NOT NULL
        CHECK(date(reported_date) IS NOT NULL
              AND reported_date = date(reported_date)),
    started_date TEXT NOT NULL
        CHECK(date(started_date) IS NOT NULL
              AND started_date = date(started_date)),
    completed_date TEXT
        CHECK(completed_date IS NULL OR (
            date(completed_date) IS NOT NULL
            AND completed_date = date(completed_date)
        )),
    task_type TEXT NOT NULL
        CHECK(task_type IN (
            'Cleaning', 'Adjustment', 'Component replacement', 'Repair'
        )),
    maintenance_cost REAL NOT NULL CHECK(maintenance_cost >= 0),
    technician_notes TEXT,

    CHECK(started_date >= reported_date),
    CHECK(completed_date IS NULL OR completed_date >= started_date)
);

CREATE INDEX idx_rental_instrument
ON agreement_instruments(instrument_id);

CREATE INDEX idx_maintenance_instrument
ON maintenance_tasks(instrument_id);
""")


# ============================================================
# 2. GENERATE INDIVIDUAL INSTRUMENTS
# ============================================================

# Prices and biological/environmental values are not downloaded.
# All numeric ranges below are illustrative simulation assumptions.
#
# Measurement types:
# Nominal: instrument_family, task_type
# Ordinal: Poor < Fair < Good < Excellent
# Interval: room_temperature_c
# Ratio: rental_days, daily_fee, maintenance_cost
#
# Monetary amounts are simulated GBP values.

catalogue = [
    ("Acoustic guitar", "String", 180, 650, 4, 10),
    ("Violin", "String", 250, 1200, 6, 16),
    ("Cello", "String", 700, 2500, 12, 28),
    ("Flute", "Woodwind", 250, 1000, 6, 14),
    ("Clarinet", "Woodwind", 300, 1100, 7, 16),
    ("Alto saxophone", "Woodwind", 650, 2200, 12, 26),
    ("Trumpet", "Brass", 300, 1300, 7, 17),
    ("Trombone", "Brass", 450, 1600, 9, 21),
    ("Digital keyboard", "Keyboard", 250, 1500, 8, 20),
    ("Snare drum", "Percussion", 150, 650, 4, 11)
]

brands = ["Aster", "Crescent", "Orion", "Silverwood"]
instruments = {}

for instrument_id in range(1, 121):
    item = rng.choices(
        catalogue,
        weights=[20, 16, 6, 10, 10, 7, 9, 5, 12, 5]
    )[0]

    name, family, low_cost, high_cost, low_fee, high_fee = item

    # A shared quality factor links purchase cost and standard fee.
    quality = rng.betavariate(2, 2)
    cost = round(low_cost + quality * (high_cost - low_cost), 2)
    fee = round(low_fee + quality * (high_fee - low_fee), 2)

    db.execute(
        "INSERT INTO instruments VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            instrument_id,
            f"INS-{instrument_id:04d}",
            name,
            family,
            rng.choice(brands),
            rng.randint(2016, 2023),
            cost,
            fee
        )
    )

    instruments[instrument_id] = {
        "cost": cost,
        "fee": fee,
        "condition": rng.choices(
            [2, 3], weights=[35, 65]
        )[0]
    }


# ============================================================
# 3. GENERATE RENTALS, INSPECTIONS AND MAINTENANCE
# ============================================================

grades = ["Poor", "Fair", "Good", "Excellent"]

# Instrument availability is updated after every rental and repair.
# Intervals include both their start and end dates.
available_from = {
    instrument_id: date(2024, 1, 1)
    for instrument_id in instruments
}

inspections = []
maintenance = []
item_number = 0

task_costs = {
    "Cleaning": (8, 30),
    "Adjustment": (20, 70),
    "Component replacement": (35, 140),
    "Repair": (60, 250)
}

for agreement_id in range(1, 651):
    start = date(2024, 1, 1) + timedelta(days=agreement_id - 1)

    duration = rng.choices(
        [2, 3, 7, 14, 21, 28],
        weights=[12, 15, 35, 22, 10, 6]
    )[0]

    planned_return = start + timedelta(days=duration)

    # Early and late returns add realistic variation.
    actual_candidate = planned_return + timedelta(
        days=rng.choices([-1, 0, 1, 2], weights=[10, 70, 15, 5])[0]
    )

    returned = actual_candidate <= REFERENCE_DATE
    actual_return = actual_candidate if returned else None

    # 550 agreements contain two instruments; 100 contain one.
    # This creates exactly 1,200 agreement-instrument records.
    instrument_count = 2 if agreement_id <= 550 else 1

    eligible = [
        instrument_id
        for instrument_id, next_date in available_from.items()
        if next_date <= start
    ]

    assert len(eligible) >= instrument_count
    selected = rng.sample(eligible, instrument_count)

    deposit = round(
        sum(instruments[i]["cost"] for i in selected) * 0.15,
        2
    )

    db.execute(
        "INSERT INTO rental_agreements VALUES (?, ?, ?, ?, ?, ?)",
        (
            agreement_id,
            start.isoformat(),
            planned_return.isoformat(),
            actual_return.isoformat() if returned else None,
            "Returned" if returned else "Active",
            deposit
        )
    )

    for instrument_id in selected:
        item_number += 1
        instrument = instruments[instrument_id]

        # Preserve the contracted fee even if standard fees later change.
        agreed_fee = round(
            instrument["fee"] * rng.choice([0.90, 0.95, 1.00]),
            2
        )

        db.execute(
            "INSERT INTO agreement_instruments VALUES (?, ?, ?, ?)",
            (agreement_id, instrument_id, agreed_fee, duration)
        )

        checkout_grade = instrument["condition"]

        inspections.append([
            agreement_id,
            instrument_id,
            "Checkout",
            f"{start.isoformat()} 09:00:00",
            grades[checkout_grade],
            round(max(10, min(35, rng.gauss(21, 1.7))), 1),
            "Existing wear recorded" if checkout_grade < 3 else None
        ])

        if returned:
            # Condition either stays the same or falls by one grade.
            deterioration = int(rng.random() < 0.12)
            return_grade = max(0, checkout_grade - deterioration)

            inspections.append([
                agreement_id,
                instrument_id,
                "Return",
                f"{actual_return.isoformat()} 17:00:00",
                grades[return_grade],
                round(max(10, min(35, rng.gauss(21, 1.7))), 1),
                "Additional wear noted" if deterioration else None
            ])

            instrument["condition"] = return_grade
            available_from[instrument_id] = (
                actual_return + timedelta(days=1)
            )

            # Routine service is scheduled periodically.
            # Fair/Poor instruments are repaired before being rented again.
            if item_number % 4 == 0 or return_grade <= 1:
                task = (
                    "Repair"
                    if return_grade <= 1
                    else rng.choices(
                        ["Cleaning", "Adjustment", "Component replacement"],
                        weights=[55, 35, 10]
                    )[0]
                )

                reported = actual_return
                started = actual_return + timedelta(days=1)
                finish = started + timedelta(
                    days=rng.randint(0, 3 if task != "Repair" else 7)
                )

                complete = finish <= REFERENCE_DATE
                low, high = task_costs[task]

                maintenance.append([
                    len(maintenance) + 1,
                    instrument_id,
                    reported.isoformat(),
                    started.isoformat(),
                    finish.isoformat() if complete else None,
                    task,
                    round(rng.triangular(low, high, low), 2),
                    None
                ])

                if complete:
                    available_from[instrument_id] = finish + timedelta(days=1)

                    # Improvement is explained by completed maintenance.
                    if task in ("Repair", "Component replacement"):
                        instrument["condition"] = 3
                    elif task == "Adjustment":
                        instrument["condition"] = max(
                            instrument["condition"], 2
                        )
                else:
                    available_from[instrument_id] = date.max

        else:
            # An active rental blocks the instrument until it returns.
            available_from[instrument_id] = date.max


# ============================================================
# 4. DELIBERATELY INSERT MISSING SENSOR READINGS
# ============================================================

# Exactly approximately 3% are selected without replacement.
# Python None becomes SQL NULL.
missing_count = round(len(inspections) * 0.03)

for position in rng.sample(range(len(inspections)), missing_count):
    inspections[position][5] = None

db.executemany(
    "INSERT INTO condition_inspections VALUES (?, ?, ?, ?, ?, ?, ?)",
    inspections
)


# ============================================================
# 5. DELIBERATELY INSERT DUPLICATE BUSINESS RECORDS
# ============================================================

# Duplicate definition:
# Same instrument, report date, start date, completion date,
# task type and cost. Maintenance ID is excluded.
#
# Only completed tasks are copied, avoiding ambiguity with NULL dates.
# Unique IDs preserve primary-key constraints.

original_maintenance_count = len(maintenance)

completed_positions = [
    position for position, row in enumerate(maintenance)
    if row[4] is not None
]

duplicate_count = max(1, round(original_maintenance_count * 0.02))

for position in rng.sample(completed_positions, duplicate_count):
    copied = maintenance[position].copy()
    copied[0] = len(maintenance) + 1
    maintenance.append(copied)

db.executemany(
    "INSERT INTO maintenance_tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
    maintenance
)

db.commit()


# ============================================================
# 6. VALIDATE CROSS-TABLE BUSINESS RULES
# ============================================================

# These rules are validated across the complete generated data.
# They are not all enforced by ordinary CHECK constraints.
checks = {
    "Agreements without instruments": """
        SELECT COUNT(*) FROM rental_agreements a
        WHERE NOT EXISTS (
            SELECT 1 FROM agreement_instruments x
            WHERE x.agreement_id = a.agreement_id
        )
    """,

    "Incorrect planned rental duration": """
        SELECT COUNT(*)
        FROM agreement_instruments x
        JOIN rental_agreements a USING (agreement_id)
        WHERE x.rental_days !=
            CAST(julianday(a.planned_return_date)
                 - julianday(a.start_date) AS INTEGER)
    """,

    "Incorrect inspection timing": """
        SELECT COUNT(*)
        FROM condition_inspections i
        JOIN rental_agreements a USING (agreement_id)
        WHERE
            (i.inspection_stage = 'Checkout'
             AND date(i.inspected_at) != a.start_date)
            OR
            (i.inspection_stage = 'Return'
             AND (
                 a.agreement_status != 'Returned'
                 OR date(i.inspected_at) != a.actual_return_date
             ))
    """,

    "Missing required inspections": """
        SELECT COUNT(*)
        FROM agreement_instruments x
        JOIN rental_agreements a USING (agreement_id)
        WHERE NOT EXISTS (
            SELECT 1 FROM condition_inspections i
            WHERE i.agreement_id = x.agreement_id
              AND i.instrument_id = x.instrument_id
              AND i.inspection_stage = 'Checkout'
        )
        OR (
            a.agreement_status = 'Returned'
            AND NOT EXISTS (
                SELECT 1 FROM condition_inspections i
                WHERE i.agreement_id = x.agreement_id
                  AND i.instrument_id = x.instrument_id
                  AND i.inspection_stage = 'Return'
            )
        )
    """,

    "Overlapping rentals": """
        SELECT COUNT(*)
        FROM agreement_instruments x
        JOIN rental_agreements a ON a.agreement_id = x.agreement_id
        JOIN agreement_instruments y
          ON x.instrument_id = y.instrument_id
         AND x.agreement_id < y.agreement_id
        JOIN rental_agreements b ON b.agreement_id = y.agreement_id
        WHERE a.start_date <= COALESCE(b.actual_return_date, '9999-12-31')
          AND b.start_date <= COALESCE(a.actual_return_date, '9999-12-31')
    """,

    "Rentals overlapping maintenance": """
        SELECT COUNT(*)
        FROM agreement_instruments x
        JOIN rental_agreements a USING (agreement_id)
        JOIN maintenance_tasks m USING (instrument_id)
        WHERE a.start_date <= COALESCE(m.completed_date, '9999-12-31')
          AND m.started_date <= COALESCE(a.actual_return_date, '9999-12-31')
    """
}

print("BUSINESS RULE CHECKS")

for description, query in checks.items():
    violations = db.execute(query).fetchone()[0]
    print(f"{description}: {violations}")
    assert violations == 0, description

assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
assert db.execute("PRAGMA foreign_key_check").fetchall() == []


# ============================================================
# 7. TEST CONSTRAINTS WITHOUT CHANGING FINAL RECORDS
# ============================================================

def must_reject(sql, parameters=()):
    db.execute("SAVEPOINT test")

    try:
        db.execute(sql, parameters)
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("Invalid write was accepted.")
    finally:
        db.execute("ROLLBACK TO test")
        db.execute("RELEASE test")


must_reject(
    "UPDATE instruments SET daily_fee = -1 WHERE instrument_id = 1"
)

must_reject(
    "UPDATE instruments SET asset_code = '' WHERE instrument_id = 1"
)

must_reject(
    """
    UPDATE instruments
    SET asset_code = (SELECT asset_code FROM instruments WHERE instrument_id = 2)
    WHERE instrument_id = 1
    """
)

must_reject(
    """
    UPDATE agreement_instruments
    SET rental_days = 2.5
    WHERE agreement_id = 1
    """
)

must_reject(
    """
    UPDATE agreement_instruments
    SET instrument_id = 9999
    WHERE agreement_id = 1
    """
)

must_reject(
    """
    UPDATE condition_inspections
    SET condition_grade = 'Perfect'
    WHERE agreement_id = 1
    """
)

must_reject(
    """
    UPDATE condition_inspections
    SET room_temperature_c = 100
    WHERE agreement_id = 1
    """
)

must_reject(
    """
    UPDATE rental_agreements
    SET planned_return_date = start_date
    WHERE agreement_id = 1
    """
)

must_reject(
    """
    UPDATE maintenance_tasks
    SET maintenance_cost = -10
    WHERE maintenance_id = 1
    """
)

must_reject(
    """
    INSERT INTO agreement_instruments
    SELECT * FROM agreement_instruments LIMIT 1
    """
)

print("\nConstraint tests passed: 10")


# ============================================================
# 8. DISPLAY ACTUAL TABLE SIZES AND STRUCTURE
# ============================================================

tables = [
    "instruments",
    "rental_agreements",
    "agreement_instruments",
    "condition_inspections",
    "maintenance_tasks"
]

print("\nTABLE COUNTS AND STRUCTURE")

for table in tables:
    count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    columns = db.execute(f"PRAGMA table_info({table})").fetchall()

    print(f"\n{table}: {count} rows, {len(columns)} columns")

    for column in columns:
        print(
            column[1],
            column[2],
            f"PK position={column[5]}",
            f"NOT NULL={bool(column[3])}"
        )

assert db.execute(
    "SELECT COUNT(*) FROM agreement_instruments"
).fetchone()[0] == 1200


# ============================================================
# 9. DISPLAY MISSING AND DUPLICATE STATISTICS
# ============================================================

actual_missing = db.execute("""
SELECT COUNT(*) FROM condition_inspections
WHERE room_temperature_c IS NULL
""").fetchone()[0]

groups = db.execute("""
SELECT COUNT(*)
FROM maintenance_tasks
GROUP BY
    instrument_id,
    reported_date,
    started_date,
    completed_date,
    task_type,
    maintenance_cost
HAVING COUNT(*) > 1
""").fetchall()

extra_copies = sum(group_size - 1 for (group_size,) in groups)
duplicate_rows = sum(group_size for (group_size,) in groups)

assert actual_missing == missing_count
assert extra_copies == duplicate_count

print("\nDELIBERATE MISSING AND DUPLICATE DATA")

print(
    f"Missing temperatures: {actual_missing}/{len(inspections)} "
    f"({100 * actual_missing / len(inspections):.2f}%)"
)

print(
    f"Duplicate extra maintenance copies: "
    f"{extra_copies}/{len(maintenance)} "
    f"({100 * extra_copies / len(maintenance):.2f}%)"
)

print(f"Duplicate groups: {len(groups)}")
print(f"Rows participating in duplicate groups: {duplicate_rows}")

# Display other missing values separately.
# Missing return/completion dates mean events have not finished.
for table, column in [
    ("rental_agreements", "actual_return_date"),
    ("maintenance_tasks", "completed_date"),
    ("condition_inspections", "damage_notes"),
    ("maintenance_tasks", "technician_notes")
]:
    total = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    missing = db.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL"
    ).fetchone()[0]

    print(
        f"{table}.{column}: {missing}/{total} NULL "
        f"({100 * missing / total:.2f}%)"
    )

db.close()

print("\nDatabase integrity: OK")
print("Foreign-key violations: 0")
print("All business-rule checks passed.")
print("Simulation reference date:", REFERENCE_DATE)
print("Database created:", DB_PATH.resolve())


# ============================================================
# 10. DOWNLOAD IN GOOGLE COLAB
# ============================================================

try:
    from google.colab import files
except ImportError:
    print("Outside Colab: use the database path printed above.")
else:
    files.download(str(DB_PATH))