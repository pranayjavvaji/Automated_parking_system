import cv2
import numpy as np
import sqlite3
import json
from datetime import datetime
from flask import Flask, Response, request, jsonify, render_template, send_from_directory
import base64
import io
from PIL import Image
from final_cam_video import SmartPSSViewer

app = Flask(__name__, static_folder='static', template_folder='templates')

# Database setup
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
            corners TEXT NOT NULL,  -- JSON string of corners
            color_hex TEXT DEFAULT '#2ed573',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (camera_channel_id) REFERENCES camera_channels(id) ON DELETE CASCADE,
            CHECK (x_max > x_min AND y_max > y_min)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized successfully!")

# Initialize database
init_db()

# Database Helper Functions
class DatabaseHelper:
    @staticmethod
    def get_db_connection():
        conn = sqlite3.connect('parking_system.db')
        conn.row_factory = sqlite3.Row
        return conn
    
    @staticmethod
    def save_configuration(dvr_name, stream_url, username, password, channel, spaces, image_dimensions=None):  # <-- CHANGE 1: Add dvr_name parameter
        conn = DatabaseHelper.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Check if DVR device exists - CHANGE 2: Search by dvr_name instead of stream_url+username
            cursor.execute(
                'SELECT id FROM dvr_devices WHERE dvr_name = ?',  # <-- CHANGE THIS LINE
                (dvr_name,)  # <-- CHANGE THIS PARAMETER
            )
            dvr_device = cursor.fetchone()
            
            if dvr_device:
                dvr_device_id = dvr_device['id']
                print(f"Existing DVR device found: {dvr_name}, ID={dvr_device_id}")  # <-- UPDATE MESSAGE
                
                # CHANGE 3: Update credentials if they changed
                cursor.execute(
                    'UPDATE dvr_devices SET stream_url = ?, username = ?, password = ? WHERE id = ?',  # <-- ADD THIS UPDATE
                    (stream_url, username, password, dvr_device_id)  # <-- KEEP SAME
                )
            else:
                # Create new DVR device - CHANGE 4: Include dvr_name in INSERT
                cursor.execute(
                    'INSERT INTO dvr_devices (dvr_name, stream_url, username, password) VALUES (?, ?, ?, ?)',  # <-- CHANGE THIS LINE
                    (dvr_name, stream_url, username, password)  # <-- ADD dvr_name HERE
                )
                dvr_device_id = cursor.lastrowid
                print(f"New DVR device created: {dvr_name}, ID={dvr_device_id}")  # <-- UPDATE MESSAGE
            
            # The rest of the function remains EXACTLY THE SAME from here...
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

@app.route('/')
def index():
    # Return HTML directly from string (same as before, but with added database buttons)
    return render_template('index.html')

@app.route('/plotting')
def plotting_page():
    return render_template('plotting.html')
# Add new API endpoint to get camera channel details
@app.route('/api/get-camera-channel/<int:camera_channel_id>')
def api_get_camera_channel(camera_channel_id):
    try:
        conn = DatabaseHelper.get_db_connection()
        cursor = conn.cursor()
        
        # Get camera channel with DVR information
        cursor.execute('''
            SELECT c.*, d.dvr_name, d.stream_url, d.username, d.password
            FROM camera_channels c
            JOIN dvr_devices d ON c.dvr_device_id = d.id
            WHERE c.id = ?
        ''', (camera_channel_id,))
        
        camera_channel = cursor.fetchone()
        
        if not camera_channel:
            return jsonify({
                'success': False,
                'error': 'Camera channel not found'
            }), 404
        
        # Count parking spaces
        cursor.execute('''
            SELECT COUNT(*) as spaces_count 
            FROM parking_spaces 
            WHERE camera_channel_id = ?
        ''', (camera_channel_id,))
        
        spaces_count = cursor.fetchone()['spaces_count']
        
        return jsonify({
            'success': True,
            'camera_channel': dict(camera_channel),
            'spaces_count': spaces_count
        })
        
    except Exception as e:
        print(f"Error getting camera channel: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        conn.close()

# Add new API endpoint to update camera information
@app.route('/api/update-camera', methods=['POST'])
def api_update_camera():
    try:
        data = request.json
        camera_channel_id = data.get('camera_channel_id')
        dvr_name = data.get('dvr_name')
        stream_url = data.get('stream_url')
        username = data.get('username')
        password = data.get('password')
        channel_number = data.get('channel_number')
        
        if not all([camera_channel_id, dvr_name, stream_url, username, password, channel_number]):
            return jsonify({
                'success': False,
                'error': 'All fields are required'
            }), 400
        
        conn = DatabaseHelper.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Get current DVR device ID from camera channel
            cursor.execute('''
                SELECT dvr_device_id FROM camera_channels WHERE id = ?
            ''', (camera_channel_id,))
            
            result = cursor.fetchone()
            if not result:
                return jsonify({
                    'success': False,
                    'error': 'Camera channel not found'
                }), 404
            
            dvr_device_id = result['dvr_device_id']
            
            # Check if DVR name already exists (for other DVRs)
            cursor.execute('''
                SELECT id FROM dvr_devices 
                WHERE dvr_name = ? AND id != ?
            ''', (dvr_name, dvr_device_id))
            
            existing_dvr = cursor.fetchone()
            if existing_dvr:
                return jsonify({
                    'success': False,
                    'error': f'DVR name "{dvr_name}" already exists'
                }), 400
            
            # Check if channel number already exists in this DVR
            cursor.execute('''
                SELECT id FROM camera_channels 
                WHERE dvr_device_id = ? AND channel_number = ? AND id != ?
            ''', (dvr_device_id, channel_number, camera_channel_id))
            
            existing_channel = cursor.fetchone()
            if existing_channel:
                return jsonify({
                    'success': False,
                    'error': f'Channel {channel_number} already exists in this DVR'
                }), 400
            
            # Update DVR device
            cursor.execute('''
                UPDATE dvr_devices 
                SET dvr_name = ?, stream_url = ?, username = ?, password = ?
                WHERE id = ?
            ''', (dvr_name, stream_url, username, password, dvr_device_id))
            
            # Update camera channel
            cursor.execute('''
                UPDATE camera_channels 
                SET channel_number = ?
                WHERE id = ?
            ''', (channel_number, camera_channel_id))
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': 'Camera information updated successfully'
            })
            
        except sqlite3.IntegrityError as e:
            conn.rollback()
            return jsonify({
                'success': False,
                'error': 'Database integrity error. Please check your data.'
            }), 400
            
    except Exception as e:
        print(f"Error updating camera: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        conn.close()

# Add route for camera listing page
@app.route('/cameras')
def cameras_list():
    return render_template('camera_list.html')

# Add route for camera edit page
@app.route('/camera_edit/<int:camera_channel_id>')
def camera_edit(camera_channel_id):
    return render_template('camera_edit.html')

# New route for camera edit with plotting
@app.route('/plots_edit/<int:camera_channel_id>')
def plots_edit(camera_channel_id):
    return render_template('plots_camera_edit.html')

# New API endpoint to get camera channel with spaces
@app.route('/api/get-camera-channel-with-spaces/<int:camera_channel_id>')
def api_get_camera_channel_with_spaces(camera_channel_id):
    try:
        conn = DatabaseHelper.get_db_connection()
        cursor = conn.cursor()
        
        # Get camera channel with DVR information
        cursor.execute('''
            SELECT c.*, d.dvr_name, d.stream_url, d.username, d.password
            FROM camera_channels c
            JOIN dvr_devices d ON c.dvr_device_id = d.id
            WHERE c.id = ?
        ''', (camera_channel_id,))
        
        camera_channel = cursor.fetchone()
        
        if not camera_channel:
            return jsonify({
                'success': False,
                'error': 'Camera channel not found'
            }), 404
        
        # Get parking spaces for this channel
        cursor.execute('''
            SELECT * FROM parking_spaces 
            WHERE camera_channel_id = ? 
            ORDER BY id
        ''', (camera_channel_id,))
        
        spaces = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'dvr_name': camera_channel['dvr_name'],
            'stream_url': camera_channel['stream_url'],
            'channel_number': camera_channel['channel_number'],
            'username': camera_channel['username'],
            'password': camera_channel['password'],
            'spaces': [
                {
                    'id': space['id'],
                    'space_name': space['space_name'],
                    'x_min': space['x_min'],
                    'y_min': space['y_min'],
                    'x_max': space['x_max'],
                    'y_max': space['y_max'],
                    'width': space['width'],
                    'height': space['height'],
                    'color_hex': space['color_hex'],
                    'corners': space['corners']
                }
                for space in spaces
            ]
        })
        
    except Exception as e:
        print(f"Error getting camera channel with spaces: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        conn.close()

# New API endpoint to update camera with spaces
@app.route('/api/update-camera-with-spaces', methods=['POST'])
def api_update_camera_with_spaces():
    try:
        data = request.json
        camera_channel_id = data.get('camera_channel_id')
        dvr_name = data.get('dvr_name')
        stream_url = data.get('stream_url')
        username = data.get('username')
        password = data.get('password')
        channel = data.get('channel')
        spaces = data.get('spaces', [])
        
        if not all([camera_channel_id, dvr_name, stream_url, username, password, channel]):
            return jsonify({
                'success': False,
                'error': 'All fields are required'
            }), 400
        
        conn = DatabaseHelper.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Get current DVR device ID
            cursor.execute('''
                SELECT dvr_device_id FROM camera_channels WHERE id = ?
            ''', (camera_channel_id,))
            
            result = cursor.fetchone()
            if not result:
                return jsonify({
                    'success': False,
                    'error': 'Camera channel not found'
                }), 404
            
            dvr_device_id = result['dvr_device_id']
            
            # Check if DVR name already exists for other DVRs
            cursor.execute('''
                SELECT id FROM dvr_devices 
                WHERE dvr_name = ? AND id != ?
            ''', (dvr_name, dvr_device_id))
            
            existing_dvr = cursor.fetchone()
            if existing_dvr:
                return jsonify({
                    'success': False,
                    'error': f'DVR name "{dvr_name}" already exists'
                }), 400
            
            # Check if channel number already exists in this DVR
            cursor.execute('''
                SELECT id FROM camera_channels 
                WHERE dvr_device_id = ? AND channel_number = ? AND id != ?
            ''', (dvr_device_id, channel, camera_channel_id))
            
            existing_channel = cursor.fetchone()
            if existing_channel:
                return jsonify({
                    'success': False,
                    'error': f'Channel {channel} already exists in this DVR'
                }), 400
            
            # Update DVR device
            cursor.execute('''
                UPDATE dvr_devices 
                SET dvr_name = ?, stream_url = ?, username = ?, password = ?
                WHERE id = ?
            ''', (dvr_name, stream_url, username, password, dvr_device_id))
            
            # Update camera channel
            cursor.execute('''
                UPDATE camera_channels 
                SET channel_number = ?
                WHERE id = ?
            ''', (channel, camera_channel_id))
            
            # Delete existing spaces
            cursor.execute('''
                DELETE FROM parking_spaces WHERE camera_channel_id = ?
            ''', (camera_channel_id,))
            
            # Save new spaces
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
            
            return jsonify({
                'success': True,
                'message': 'Camera configuration updated successfully',
                'spaces_saved': len(spaces)
            })
            
        except sqlite3.IntegrityError as e:
            conn.rollback()
            return jsonify({
                'success': False,
                'error': 'Database integrity error. Please check your data.'
            }), 400
            
    except Exception as e:
        print(f"Error updating camera with spaces: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        conn.close()


# API Routes for Database Operations
@app.route('/api/save-config', methods=['POST'])
def api_save_config():
    try:
        data = request.json
        dvr_name = data.get('dvr_name')  # <-- Get DVR name
        stream_url = data.get('stream_url')
        username = data.get('username')
        password = data.get('password')
        channel = data.get('channel')
        spaces = data.get('spaces', [])
        
        if not dvr_name:  # <-- Check DVR name
            return jsonify({
                'success': False,
                'error': 'DVR name is required'
            }), 400
        
        # Pass dvr_name to save_configuration
        result = DatabaseHelper.save_configuration(
            dvr_name, stream_url, username, password, channel, spaces
        )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/load-config', methods=['POST'])
def api_load_config():
    try:
        data = request.json
        dvr_name = data.get('dvr_name')  # <-- Get DVR name
        stream_url = data.get('stream_url')
        username = data.get('username')
        password = data.get('password')
        channel = data.get('channel')
        
        if not dvr_name or not channel:  # <-- Check DVR name
            return jsonify({
                'success': False,
                'error': 'DVR name and channel are required'
            }), 400
        
        # Update the load_configuration method to accept dvr_name
        result = DatabaseHelper.load_configuration(
            dvr_name, stream_url, username, password, channel
        )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/list-dvrs', methods=['GET'])
def api_list_dvrs():
    try:
        dvr_devices = DatabaseHelper.list_dvr_devices()
        return jsonify({
            'success': True,
            'dvr_devices': dvr_devices
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/dvr-channels/<int:dvr_id>', methods=['GET'])
def api_dvr_channels(dvr_id):
    try:
        channels = DatabaseHelper.get_dvr_channels(dvr_id)
        return jsonify({
            'success': True,
            'channels': channels
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/capture-frame', methods=['POST'])
def capture_frame():
    try:
        data = request.json
        url = data.get('url')
        channel = data.get('channel', 1)
        username = data.get('username', 'admin')
        password = data.get('password', 'admin@123')
        
        if not url:
            return jsonify({
                'success': False,
                'error': 'URL is required'
            }), 400
        
        print(f"Attempting to capture frame for URL: {url}, Channel: {channel}")
        
        # Try to capture from RTSP
        viewer = SmartPSSViewer(url, channel, username, password)
        frame, error = viewer.capture_single_frame()
        
        if frame is not None:
            # Encode frame as JPEG
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            
            print(f"Frame captured successfully: {frame.shape[1]}x{frame.shape[0]}")
            
            return jsonify({
                'success': True,
                'image': frame_base64,
                'dimensions': {
                    'width': frame.shape[1],
                    'height': frame.shape[0]
                }
            })
        else:
            print(f"RTSP capture failed: {error}")
            print("Returning test image...")
            
            # Create a test image
            img = Image.new('RGB', (1280, 720), color='#2c3e50')
            
            # Add some text and shapes
            draw = ImageDraw.Draw(img)
            draw.text((400, 300), "RTSP Capture Failed", fill='white', font=None)
            draw.text((350, 350), "Using test image - SmartPSS might not be running", fill='white', font=None)
            draw.text((450, 400), "You can still practice drawing rectangles", fill='white', font=None)
            
            # Draw some sample rectangles
            draw.rectangle([200, 500, 400, 600], outline='red', width=3)
            draw.rectangle([500, 500, 700, 600], outline='blue', width=3)
            draw.rectangle([800, 500, 1000, 600], outline='green', width=3)
            
            # Convert to base64
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            frame_base64 = base64.b64encode(buffered.getvalue()).decode()
            
            return jsonify({
                'success': True,
                'image': frame_base64,
                'dimensions': {
                    'width': 1280,
                    'height': 720
                },
                'note': 'Test image - RTSP capture failed'
            })
            
    except Exception as e:
        print(f"Exception in capture-frame: {str(e)}")
        
        # Return a simple error image
        img = Image.new('RGB', (1280, 720), color='#2c3e50')
        draw = ImageDraw.Draw(img)
        draw.text((400, 300), f"Error: {str(e)[:50]}", fill='white', font=None)
        
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG")
        frame_base64 = base64.b64encode(buffered.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'image': frame_base64,
            'dimensions': {
                'width': 1280,
                'height': 720
            },
            'note': 'Error image'
        })
# ==========================================
# ADD THIS NEW ROUTE TO app.py
# ==========================================

@app.route('/api/delete-channel/<int:channel_id>', methods=['DELETE'])
def api_delete_channel(channel_id):
    conn = DatabaseHelper.get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Find the DVR ID associated with this channel before deleting
        cursor.execute('SELECT dvr_device_id FROM camera_channels WHERE id = ?', (channel_id,))
        row = cursor.fetchone()
        
        if not row:
            return jsonify({'success': False, 'error': 'Channel not found'}), 404
            
        dvr_id = row['dvr_device_id']
        
        # 2. Delete the Channel
        # (Parking spaces will auto-delete because of ON DELETE CASCADE in your init_db)
        cursor.execute('DELETE FROM camera_channels WHERE id = ?', (channel_id,))
        
        # 3. CRITICAL STEP: Check if the DVR has any other channels left
        cursor.execute('SELECT COUNT(*) FROM camera_channels WHERE dvr_device_id = ?', (dvr_id,))
        remaining_channels = cursor.fetchone()[0]
        
        dvr_deleted = False
        if remaining_channels == 0:
            # If no channels left, delete the DVR as well
            cursor.execute('DELETE FROM dvr_devices WHERE id = ?', (dvr_id,))
            dvr_deleted = True
            print(f"DVR {dvr_id} was empty and has been deleted.")
            
        conn.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Channel and linked data deleted',
            'dvr_deleted': dvr_deleted
        })
        
    except Exception as e:
        conn.rollback()
        print(f"Error deleting channel: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/gates')
def gates_page():
    return render_template('gates.html')

@app.route('/api/save-gates', methods=['POST'])
def save_gates():
    try:
        data = request.json
        dvr_name = data.get('dvr_name')
        gates = data.get('gates', [])
        
        if not dvr_name:
            return jsonify({'success': False, 'error': 'DVR Name is required'})

        conn = sqlite3.connect('parking_system.db')
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM traffic_gates WHERE dvr_name = ?", (dvr_name,))
        
        for g in gates:
            line = g['line']
            cursor.execute("""
                INSERT INTO traffic_gates (dvr_name, gate_name, x1, y1, x2, y2, direction)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (dvr_name, g['name'], line[0], line[1], line[2], line[3], g['direction']))
            
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Saved {len(gates)} gates'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/load-gates', methods=['POST'])
def load_gates():
    try:
        dvr_name = request.json.get('dvr_name')
        conn = sqlite3.connect('parking_system.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM traffic_gates WHERE dvr_name = ?", (dvr_name,))
        rows = cursor.fetchall()
        conn.close()
        
        gates = []
        for r in rows:
            gates.append({
                'id': r['id'],
                'name': r['gate_name'],
                'line': [r['x1'], r['y1'], r['x2'], r['y2']], # Format for frontend
                'direction': r['direction']
            })
            
        return jsonify({'success': True, 'gates': gates})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ==========================================
# DASHBOARD & STREAMING ROUTES
# ==========================================
import threading
from main_detection import VideoCamera

# Global variable for the camera
video_system = None

def gen(camera):
    """Video streaming generator function."""
    while True:
        frame = camera.get_frame()
        if frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        else:
            # If camera disconnects, send empty byte to prevent crash
            pass

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/video_feed')
def video_feed():
    global video_system
    if video_system is None:
        video_system = VideoCamera() # Starts the camera when page loads
    
    return Response(gen(video_system),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/stop-stream')
def stop_stream():
    global video_system
    if video_system:
        video_system.stop()
        video_system = None
    return jsonify({'success': True})

if __name__ == '__main__':
    # Import PIL here to avoid dependency issues
    from PIL import Image, ImageDraw
    
    print("=" * 70)
    print("VEHICLE SPACE SELECTOR - RTSP STREAM INTEGRATION WITH DATABASE")
    print("=" * 70)
    print("Starting server...")
    print("Open your browser and go to: http://localhost:5000")
    print("\nDatabase: parking_system.db")
    print("Tables created: dvr_devices, camera_channels, parking_spaces")
    print("\nMake sure:")
    print("1. SmartPSS is running (for real RTSP capture)")
    print(f"2. FFmpeg path is correct: C:\\Users\\javva\\Downloads\\Final_year_project\\ffmpeg\\bin\\ffmpeg.exe")
    print("=" * 70)
    
    app.run(debug=True, port=5000)


