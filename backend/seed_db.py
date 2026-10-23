"""Create deterministic sample data; application execution never uses this writer."""

import argparse
import sqlite3
from pathlib import Path

DDL = """
CREATE TABLE Users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE Products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0)
);
CREATE TABLE Orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES Users(id),
    ordered_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('paid', 'shipped', 'cancelled'))
);
CREATE TABLE OrderItems (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES Orders(id),
    product_id INTEGER NOT NULL REFERENCES Products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0)
);
CREATE INDEX idx_orders_user_id ON Orders(user_id);
CREATE INDEX idx_order_items_order_id ON OrderItems(order_id);
CREATE INDEX idx_order_items_product_id ON OrderItems(product_id);
"""


def seed_database(database_path: Path) -> bool:
    """Initialize an empty database with 28 related, deterministic sample rows.

    Args:
        database_path: Destination SQLite file; existing populated files are preserved.

    Returns:
        True if created, False if the expected tables already exist.

    Raises:
        ValueError: Existing database contains an unexpected or incomplete schema.

    Side Effects:
        Creates parent directories and writes sample data in a single transaction.
    """
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if tables:
            if tables == {"Users", "Orders", "Products", "OrderItems"}:
                return False
            raise ValueError("Existing database has an unexpected schema; no data was changed.")
        connection.executescript("BEGIN;\n" + DDL)
        connection.executemany(
            "INSERT INTO Users VALUES (?, ?, ?, ?, ?)",
            [
                (1, "Maya Chen", "maya@example.com", "California", "2024-01-12"),
                (2, "Noah Williams", "noah@example.com", "New York", "2024-02-03"),
                (3, "Ava Patel", "ava@example.com", "California", "2024-03-18"),
                (4, "Leo Garcia", "leo@example.com", "Texas", "2024-04-09"),
                (5, "Isla Kim", "isla@example.com", "Washington", "2024-05-21"),
                (6, "Owen Davis", "owen@example.com", "California", "2024-06-02"),
            ],
        )
        connection.executemany(
            "INSERT INTO Products VALUES (?, ?, ?, ?)",
            [
                (1, "Canvas backpack", "Accessories", 6900),
                (2, "Desk lamp", "Home", 4500),
                (3, "Wireless keyboard", "Electronics", 8900),
                (4, "Ceramic mug", "Home", 1800),
                (5, "Notebook", "Stationery", 1200),
                (6, "USB-C hub", "Electronics", 5900),
            ],
        )
        connection.executemany(
            "INSERT INTO Orders VALUES (?, ?, ?, ?)",
            [
                (1, 1, "2025-01-08", "shipped"),
                (2, 2, "2025-01-15", "shipped"),
                (3, 1, "2025-02-02", "paid"),
                (4, 3, "2025-02-14", "paid"),
                (5, 4, "2025-03-01", "cancelled"),
                (6, 5, "2025-03-08", "shipped"),
            ],
        )
        connection.executemany(
            "INSERT INTO OrderItems VALUES (?, ?, ?, ?, ?)",
            [
                (1, 1, 1, 1, 6900),
                (2, 1, 5, 2, 1200),
                (3, 2, 3, 1, 8900),
                (4, 2, 6, 1, 5900),
                (5, 3, 4, 3, 1800),
                (6, 4, 2, 1, 4500),
                (7, 4, 4, 2, 1800),
                (8, 5, 1, 1, 6900),
                (9, 6, 5, 4, 1200),
                (10, 6, 6, 1, 5900),
            ],
        )
        connection.commit()
        return True
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> None:
    """Parse the destination argument and seed a database on disk."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=Path("ecommerce.db"))
    arguments = parser.parse_args()
    created = seed_database(arguments.path)
    print(f"{'Created' if created else 'Preserved'} {arguments.path.resolve()}")


if __name__ == "__main__":
    main()
