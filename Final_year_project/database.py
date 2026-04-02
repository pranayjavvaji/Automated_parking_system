import os
import sqlite3
import json

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'parking_system.db')

def initialize_database():
    """Master Database schema. Centralized here to keep app.py clean."""
    print("⏳ Syncing Database Schema...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Hardware Table (Cameras)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS camera_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_name TEXT NOT NULL,
            camera_role TEXT NOT NULL,  
            camera_brand TEXT,
            ip_address TEXT,
            rtsp_port TEXT,
            channel INTEGER,
            username TEXT,
            password TEXT,
            stream_url TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 2. Logic Table (Spaces & Tripwires combined!)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS detection_zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_channel_id INTEGER NOT NULL,
            zone_name TEXT NOT NULL,     
            shape_type TEXT DEFAULT 'box',
            coordinates TEXT NOT NULL,     
            is_empty INTEGER DEFAULT 1,    
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (camera_channel_id) REFERENCES camera_channels(id) ON DELETE CASCADE
        )
    ''')

    # 3. Billing & Tracking Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parking_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_number TEXT NOT NULL,
            plate_vector TEXT,
            vehicle_type TEXT,
            vehicle_feature_vector TEXT,
            assigned_zone_id INTEGER,
            entry_time TIMESTAMP,
            exit_time TIMESTAMP,  
            total_fare REAL,      
            FOREIGN KEY (assigned_zone_id) REFERENCES detection_zones (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Master Database Schema Synced!")

# ==========================================
# DATABASE HELPER FUNCTIONS
# ==========================================
class DatabaseHelper:
    @staticmethod
    def get_db_connection():
        conn = sqlite3.connect(
            DB_PATH, 
            check_same_thread=False, 
            timeout=20
        )
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def list_cameras():
        """Replaces list_dvr_devices to fetch our new camera structure."""
        conn = DatabaseHelper.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT c.*, COUNT(dz.id) as total_zones
                FROM camera_channels c
                LEFT JOIN detection_zones dz ON c.id = dz.camera_channel_id
                GROUP BY c.id ORDER BY c.created_at DESC
            ''')
            return [dict(cam) for cam in cursor.fetchall()]
        finally:
            conn.close()

def display_db_structure():
    print(f"🔍 Inspecting Database: {os.path.basename(DB_PATH)}\n")
    print("=" * 60)
    
    if not os.path.exists(DB_PATH):
        print("❌ Database file not found! Please run your database setup script first.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    if not tables:
        print("⚠️ Database exists, but it is completely empty.")
        return

    for table_name in tables:
        table = table_name[0]
        if table.startswith('sqlite_'): continue
            
        print(f"📦 TABLE: {table.upper()}")
        print("-" * 60)
        
        cursor.execute(f"PRAGMA table_info({table});")
        columns = cursor.fetchall()
        
        for col in columns:
            col_id, col_name, col_type, not_null, default_val, is_pk = col
            pk_marker = "🔑 PRIMARY KEY" if is_pk else ""
            print(f"  🔹 {col_name:<20} | {col_type:<10} {pk_marker}")
        print("\n")

    conn.close()
    print("✅ Inspection Complete.")
    print("=" * 60)

if __name__ == '__main__':
    # Initialize the database to ensure tables exist
    initialize_database()
    # Then display the structure
    display_db_structure()