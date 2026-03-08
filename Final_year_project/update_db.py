import sqlite3

def create_missing_table():
    print("Connecting to database...")
    try:
        conn = sqlite3.connect('parking_system.db')
        cursor = conn.cursor()
        
        print("Creating 'traffic_gates' table...")
        # Force create the table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS traffic_gates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dvr_name TEXT NOT NULL,
                gate_name TEXT NOT NULL,
                x1 INTEGER NOT NULL,
                y1 INTEGER NOT NULL,
                x2 INTEGER NOT NULL,
                y2 INTEGER NOT NULL,
                direction TEXT DEFAULT 'both',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        print("✅ SUCCESS: Table 'traffic_gates' created successfully.")
        
        # Verify it exists now
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='traffic_gates'")
        if cursor.fetchone():
            print("Verified: Table exists.")
        else:
            print("❌ Error: Table still not found after creation attempt.")
            
        conn.close()
        
    except Exception as e:
        print(f"❌ Database Error: {e}")

if __name__ == "__main__":
    create_missing_table()