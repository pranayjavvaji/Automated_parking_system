import sqlite3
import json

class DatabaseHelper:
    @staticmethod
    def init_db():
        conn = sqlite3.connect('parking_system.db')
        cursor = conn.cursor()
        
        # Create dvr_devices table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dvr_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dvr_name TEXT NOT NULL,
                stream_url TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(dvr_name)
            )
        ''')
        
        # Create camera_channels table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS camera_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dvr_device_id INTEGER NOT NULL,
                channel_number INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dvr_device_id) REFERENCES dvr_devices(id) ON DELETE CASCADE,
                UNIQUE(dvr_device_id, channel_number)
            )
        ''')
        
        # Create parking_spaces table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS parking_spaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_channel_id INTEGER NOT NULL,
                space_name TEXT DEFAULT 'Unnamed Space',
                x_min INTEGER NOT NULL,
                y_min INTEGER NOT NULL,
                x_max INTEGER NOT NULL,
                y_max INTEGER NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                area INTEGER NOT NULL,
                corners TEXT NOT NULL,
                color_hex TEXT DEFAULT '#2ed573',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (camera_channel_id) REFERENCES camera_channels(id) ON DELETE CASCADE,
                CHECK (x_max > x_min AND y_max > y_min)
            )
        ''')
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
        conn.close()
        print("Database initialized successfully!")
    
    @staticmethod
    def get_db_connection():
        conn = sqlite3.connect('parking_system.db')
        conn.row_factory = sqlite3.Row
        return conn
    
    @staticmethod
    def save_configuration(dvr_name, stream_url, username, password, channel, spaces):
        conn = DatabaseHelper.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Check if DVR device exists
            cursor.execute(
                'SELECT id FROM dvr_devices WHERE dvr_name = ?',
                (dvr_name,)
            )
            dvr_device = cursor.fetchone()
            
            if dvr_device:
                dvr_device_id = dvr_device['id']
                print(f"Existing DVR device found: {dvr_name}, ID={dvr_device_id}")
                
                # Update credentials if they changed
                cursor.execute(
                    'UPDATE dvr_devices SET stream_url = ?, username = ?, password = ? WHERE id = ?',
                    (stream_url, username, password, dvr_device_id)
                )
            else:
                # Create new DVR device
                cursor.execute(
                    'INSERT INTO dvr_devices (dvr_name, stream_url, username, password) VALUES (?, ?, ?, ?)',
                    (dvr_name, stream_url, username, password)
                )
                dvr_device_id = cursor.lastrowid
                print(f"New DVR device created: {dvr_name}, ID={dvr_device_id}")
            
            # Check if camera channel exists
            cursor.execute(
                'SELECT id FROM camera_channels WHERE dvr_device_id = ? AND channel_number = ?',
                (dvr_device_id, channel)
            )
            camera_channel = cursor.fetchone()
            
            if camera_channel:
                camera_channel_id = camera_channel['id']
                # Delete existing spaces for this channel
                cursor.execute(
                    'DELETE FROM parking_spaces WHERE camera_channel_id = ?',
                    (camera_channel_id,)
                )
                print(f"Existing camera channel found: ID={camera_channel_id}, deleting old spaces")
            else:
                # Create new camera channel
                cursor.execute(
                    'INSERT INTO camera_channels (dvr_device_id, channel_number) VALUES (?, ?)',
                    (dvr_device_id, channel)
                )
                camera_channel_id = cursor.lastrowid
                print(f"New camera channel created: ID={camera_channel_id}")
            
            # Save parking spaces
            for i, space in enumerate(spaces):
                space_name = space.get('spaceName', f'Space {i+1}')
                cursor.execute('''
                    INSERT INTO parking_spaces 
                    (camera_channel_id, space_name, x_min, y_min, x_max, y_max, 
                    width, height, area, corners, color_hex)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    camera_channel_id,
                    space_name,
                    space['boundingBox']['x_min'],
                    space['boundingBox']['y_min'],
                    space['boundingBox']['x_max'],
                    space['boundingBox']['y_max'],
                    space['boundingBox']['width'],
                    space['boundingBox']['height'],
                    space['boundingBox']['width'] * space['boundingBox']['height'],
                    json.dumps(space['corners']),
                    space.get('color', '#2ed573')
                ))
            
            conn.commit()
            return {
                'success': True,
                'dvr_device_id': dvr_device_id,
                'camera_channel_id': camera_channel_id,
                'spaces_saved': len(spaces)
            }
            
        except Exception as e:
            conn.rollback()
            print(f"Error saving to database: {str(e)}")
            return {'success': False, 'error': str(e)}
            
        finally:
            conn.close()
    
    @staticmethod
    def load_configuration(dvr_name, stream_url, username, password, channel):
        conn = DatabaseHelper.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Get DVR device by dvr_name
            cursor.execute(
                '''SELECT d.* FROM dvr_devices d 
                WHERE d.dvr_name = ?''',
                (dvr_name,)
            )
            dvr_device = cursor.fetchone()
            
            if not dvr_device:
                return {'success': False, 'error': f'DVR "{dvr_name}" not found'}
            
            # Get camera channel
            cursor.execute(
                '''SELECT c.* FROM camera_channels c 
                   WHERE c.dvr_device_id = ? AND c.channel_number = ?''',
                (dvr_device['id'], channel)
            )
            camera_channel = cursor.fetchone()
            
            if not camera_channel:
                return {'success': False, 'error': 'Camera channel not found'}
            
            # Get parking spaces
            cursor.execute(
                '''SELECT * FROM parking_spaces 
                   WHERE camera_channel_id = ? ORDER BY id''',
                (camera_channel['id'],)
            )
            spaces = cursor.fetchall()
            
            # Format response
            spaces_list = []
            for space in spaces:
                spaces_list.append({
                    'spaceId': space['id'],
                    'spaceName': space['space_name'],
                    'boundingBox': {
                        'x_min': space['x_min'],
                        'y_min': space['y_min'],
                        'x_max': space['x_max'],
                        'y_max': space['y_max'],
                        'width': space['width'],
                        'height': space['height']
                    },
                    'corners': json.loads(space['corners']),
                    'color': space['color_hex']
                })
            
            return {
                'success': True,
                'dvr_device': dict(dvr_device),
                'camera_channel': dict(camera_channel),
                'spaces': spaces_list
            }
            
        except Exception as e:
            print(f"Error loading from database: {str(e)}")
            return {'success': False, 'error': str(e)}
            
        finally:
            conn.close()
    
    @staticmethod
    def list_dvr_devices():
        conn = DatabaseHelper.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT d.*, 
                       COUNT(DISTINCT c.id) as channel_count,
                       COUNT(DISTINCT ps.id) as total_spaces
                FROM dvr_devices d
                LEFT JOIN camera_channels c ON d.id = c.dvr_device_id
                LEFT JOIN parking_spaces ps ON c.id = ps.camera_channel_id
                GROUP BY d.id
                ORDER BY d.created_at DESC
            ''')
            dvr_devices = cursor.fetchall()
            
            return [dict(device) for device in dvr_devices]
            
        except Exception as e:
            print(f"Error listing DVR devices: {str(e)}")
            return []
            
        finally:
            conn.close()
    
    @staticmethod
    def get_dvr_channels(dvr_device_id):
        conn = DatabaseHelper.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT c.*, 
                       COUNT(ps.id) as space_count
                FROM camera_channels c
                LEFT JOIN parking_spaces ps ON c.id = ps.camera_channel_id
                WHERE c.dvr_device_id = ?
                GROUP BY c.id
                ORDER BY c.channel_number
            ''', (dvr_device_id,))
            
            channels = cursor.fetchall()
            return [dict(channel) for channel in channels]
            
        except Exception as e:
            print(f"Error getting DVR channels: {str(e)}")
            return []
            
        finally:
            conn.close()