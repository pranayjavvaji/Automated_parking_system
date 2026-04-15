import sqlite3
import pandas as pd
from pathlib import Path

# ========== CONFIGURATION ==========
DB_PATH = r"C:\Users\javva\Downloads\Final_project\Final_year_project\parking_system.db"          # Change to your actual .db file
EXCEL_PATH = "database_export.xlsx"   # Output Excel file
PRINT_SUMMARY = True                  # Print row counts to console
# ===================================

def export_db_to_excel(db_path, excel_path):
    """Export all tables from SQLite to Excel, each table as a separate sheet."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all table names (excluding sqlite_ internal tables)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in cursor.fetchall()]

    if not tables:
        print("No tables found in the database.")
        conn.close()
        return

    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        for table in tables:
            df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
            df.to_excel(writer, sheet_name=table[:31], index=False)  # Excel sheet name max 31 chars
            if PRINT_SUMMARY:
                print(f"📄 {table}: {len(df)} rows exported")

    conn.close()
    print(f"\n✅ Export complete. Data saved to: {excel_path}")

def print_console_summary(db_path):
    """Quick console summary: show first few rows of each table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in cursor.fetchall()]

    for table in tables:
        print(f"\n📌 TABLE: {table}")
        df = pd.read_sql_query(f"SELECT * FROM {table} LIMIT 10", conn)  # Show only 10 rows
        if df.empty:
            print("   (empty)")
        else:
            print(df.to_string(index=False))
        print("-" * 80)

    conn.close()

if __name__ == "__main__":
    # Check if database file exists
    if not Path(DB_PATH).exists():
        print(f"❌ Database not found at {DB_PATH}")
        print("Please update DB_PATH variable with the correct path.")
    else:
        export_db_to_excel(DB_PATH, EXCEL_PATH)
        if PRINT_SUMMARY:
            print("\n" + "=" * 60)
            print("CONSOLE PREVIEW (first 10 rows per table):")
            print_console_summary(DB_PATH)