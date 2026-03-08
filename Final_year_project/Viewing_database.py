# import sqlite3
# import json

# def view_database_simple():
#     # Connect to database
#     conn = sqlite3.connect('parking_system.db')
#     conn.row_factory = sqlite3.Row
#     cursor = conn.cursor()
    
#     print("=" * 80)
#     print("DATABASE CONTENT VIEWER")
#     print("=" * 80)
    
#     print("\n1. DVR DEVICES:")
#     print("-" * 40)
#     cursor.execute("SELECT * FROM dvr_devices ORDER BY id")
#     dvr_devices = cursor.fetchall()
    
#     for device in dvr_devices:
#         print(f"ID: {device['id']}")
#         print(f"  Name: {device['dvr_name']}")
#         print(f"  URL: {device['stream_url']}")
#         print(f"  Username: {device['username']}")
#         print(f"  Password: {device['password']}")
#         print(f"  Created: {device['created_at']}")
#         print()
    
#     print("\n2. CAMERA CHANNELS:")
#     print("-" * 40)
#     cursor.execute("""
#         SELECT cc.*, d.stream_url 
#         FROM camera_channels cc
#         LEFT JOIN dvr_devices d ON cc.dvr_device_id = d.id
#         ORDER BY cc.dvr_device_id, cc.channel_number
#     """)
#     channels = cursor.fetchall()
    
#     for channel in channels:
#         print(f"Channel ID: {channel['id']}")
#         print(f"  DVR ID: {channel['dvr_device_id']}")
#         print(f"  DVR URL: {channel['stream_url']}")
#         print(f"  Channel #: {channel['channel_number']}")
#         print(f"  Created: {channel['created_at']}")
#         print()
    
#     print("\n3. PARKING SPACES:")
#     print("-" * 40)
#     cursor.execute("""
#         SELECT ps.*, cc.channel_number 
#         FROM parking_spaces ps
#         LEFT JOIN camera_channels cc ON ps.camera_channel_id = cc.id
#         ORDER BY ps.camera_channel_id, ps.id
#     """)
#     spaces = cursor.fetchall()
    
#     for space in spaces:
#         print(f"Space ID: {space['id']}")
#         print(f"  Channel ID: {space['camera_channel_id']} (Channel {space['channel_number']})")
#         print(f"  Name: {space['space_name']}")
#         print(f"  Coordinates: ({space['x_min']},{space['y_min']}) to ({space['x_max']},{space['y_max']})")
#         print(f"  Size: {space['width']}x{space['height']} (Area: {space['area']}px²)")
#         print(f"  Color: {space['color_hex']}")
#         print(f"  Created: {space['created_at']}")
#         print()
    
#     print("\n4. SUMMARY:")
#     print("-" * 40)
    
#     cursor.execute("SELECT COUNT(*) as count FROM dvr_devices")
#     dvr_count = cursor.fetchone()['count']
#     print(f"Total DVR Devices: {dvr_count}")
    
#     cursor.execute("SELECT COUNT(*) as count FROM camera_channels")
#     channel_count = cursor.fetchone()['count']
#     print(f"Total Camera Channels: {channel_count}")
    
#     cursor.execute("SELECT COUNT(*) as count FROM parking_spaces")
#     space_count = cursor.fetchone()['count']
#     print(f"Total Parking Spaces: {space_count}")
    
#     conn.close()
#     print("\n" + "=" * 80)
#     print("Database viewing complete!")
#     print("=" * 80)

# if __name__ == "__main__":
#     view_database_simple()


import sqlite3

conn = sqlite3.connect('parking_system.db')
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='traffic_gates'")
result = cursor.fetchone()

if result:
    print("✅ SUCCESS: Table 'traffic_gates' exists!")
    cursor.execute("PRAGMA table_info(traffic_gates)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"   - Column: {col[1]} ({col[2]})")
else:
    print("❌ ERROR: Table 'traffic_gates' was NOT found.")

conn.close()