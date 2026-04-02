import os
import cv2
import numpy as np
import sqlite3
import json
import threading
from datetime import datetime
from flask import Flask, Response, request, jsonify, render_template
import base64
import io

# Import your unified database and camera modules
from database import initialize_database, DatabaseHelper
from final_cam_video import SmartPSSViewer

app = Flask(__name__, static_folder='static', template_folder='templates')

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'parking_system.db')

# ==========================================
# 🌐 HTML PAGE ROUTES
# ==========================================
@app.route('/')
def index(): return render_template('index.html')

@app.route('/plotting')
def plotting_page(): return render_template('plotting.html')

@app.route('/cameras')
def cameras_list(): return render_template('camera_list.html')

@app.route('/camera_edit/<int:camera_channel_id>')
def camera_edit(camera_channel_id): return render_template('camera_edit.html')

@app.route('/plots_edit/<int:camera_channel_id>')
def plots_edit(camera_channel_id): return render_template('plots_camera_edit.html')

@app.route('/gates')
def gates_page(): return render_template('gates.html')

@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html')

@app.route('/setup')
def setup_page(): return render_template('setup_system.html')


# ==========================================
# 🛠️ API ROUTES (The New Unified Architecture)
# ==========================================

@app.route('/api/list-cameras', methods=['GET'])
def api_list_cameras():
    try:
        cameras = DatabaseHelper.list_cameras()
        return jsonify({'success': True, 'cameras': cameras})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get-camera-channel/<int:camera_channel_id>')
def api_get_camera_channel(camera_channel_id):
    """Fetches a single camera and counts its active zones"""
    try:
        conn = DatabaseHelper.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM camera_channels WHERE id = ?', (camera_channel_id,))
        camera = cursor.fetchone()
        
        if not camera: 
            return jsonify({'success': False, 'error': 'Not found'}), 404
        
        cursor.execute('SELECT COUNT(*) as zones_count FROM detection_zones WHERE camera_channel_id = ?', (camera_channel_id,))
        zones_count = cursor.fetchone()['zones_count']
        
        return jsonify({
            'success': True, 
            'camera_channel': dict(camera), 
            'spaces_count': zones_count
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()
@app.route('/api/update-camera', methods=['POST'])
def api_update_camera():
    """Updates ONLY the camera hardware info without deleting its drawn zones."""
    data = request.json
    cam_id = data.get('camera_channel_id')
    
    if not cam_id:
        return jsonify({'success': False, 'error': 'Camera ID is required'}), 400
        
    conn = DatabaseHelper.get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE camera_channels 
            SET camera_name=?, camera_role=?, camera_brand=?, ip_address=?, rtsp_port=?, channel=?, username=?, password=?, stream_url=? 
            WHERE id=?
        ''', (
            data.get('camera_name'), data.get('camera_role'), data.get('camera_brand'), 
            data.get('ip_address'), data.get('rtsp_port'), data.get('channel'), 
            data.get('username'), data.get('password'), data.get('stream_url'), 
            cam_id
        ))
        conn.commit()
        return jsonify({'success': True, 'message': 'Camera updated successfully'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/get-camera-channel-with-zones/<int:camera_channel_id>')
def api_get_camera_channel_with_zones(camera_channel_id):
    """Loads a camera and ALL its drawn zones for the Edit Zones page."""
    try:
        conn = DatabaseHelper.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM camera_channels WHERE id = ?', (camera_channel_id,))
        camera = cursor.fetchone()
        
        if not camera:
            return jsonify({'success': False, 'error': 'Camera not found'}), 404
            
        cursor.execute('SELECT * FROM detection_zones WHERE camera_channel_id = ?', (camera_channel_id,))
        zones = cursor.fetchall()
        
        formatted_zones = []
        for z in zones:
            formatted_zones.append({
                'id': z['id'],
                'zoneName': z['zone_name'],
                'shapeType': z['shape_type'],
                'coordinates': json.loads(z['coordinates']),
                'isEmpty': z['is_empty']
            })
            
        return jsonify({
            'success': True,
            'camera': dict(camera),
            'zones': formatted_zones
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()
@app.route('/api/save-config', methods=['POST'])
def save_config():
    """THE MASTER SAVE FUNCTION: Handles both Parking Spaces AND Gates!"""
    data = request.json
    conn = DatabaseHelper.get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Update or Insert the Camera Hardware Info
        cursor.execute('SELECT id FROM camera_channels WHERE camera_name = ?', (data.get('camera_name'),))
        cam = cursor.fetchone()
        
        if cam:
            cam_id = cam['id']
            cursor.execute('''
                UPDATE camera_channels 
                SET camera_role=?, camera_brand=?, ip_address=?, rtsp_port=?, channel=?, username=?, password=?, stream_url=? 
                WHERE id=?
            ''', (
                data.get('camera_role'), data.get('camera_brand'), data.get('ip_address'), 
                data.get('rtsp_port'), data.get('channel'), data.get('username'), 
                data.get('password'), data.get('stream_url'), cam_id
            ))
            # Delete old zones so we can cleanly replace them
            cursor.execute('DELETE FROM detection_zones WHERE camera_channel_id = ?', (cam_id,))
        else:
            cursor.execute('''
                INSERT INTO camera_channels 
                (camera_name, camera_role, camera_brand, ip_address, rtsp_port, channel, username, password, stream_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data.get('camera_name'), data.get('camera_role', 'parking_lot'), data.get('camera_brand'), 
                data.get('ip_address'), data.get('rtsp_port'), data.get('channel'), 
                data.get('username'), data.get('password'), data.get('stream_url')
            ))
            cam_id = cursor.lastrowid

        # 2. Insert the Zones (Looks for 'spaces' array OR 'gates' array in the JSON)
        zones = data.get('spaces', []) + data.get('gates', [])
        
        for zone in zones:
            zone_name = zone.get('spaceName') or zone.get('name') or 'Unnamed Zone'
            
            # Auto-detect if this is a Box (Parking) or a Line (Gate)
            if 'boundingBox' in zone:
                shape_type = 'box'
                coords = json.dumps(zone['corners'])
            else:
                shape_type = 'line'
                coords = json.dumps(zone['line'])

            cursor.execute('''
                INSERT INTO detection_zones (camera_channel_id, zone_name, shape_type, coordinates, is_empty)
                VALUES (?, ?, ?, ?, ?)
            ''', (cam_id, zone_name, shape_type, coords, 1))
            
        conn.commit()
        return jsonify({'success': True, 'zones_saved': len(zones)})
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/load-config', methods=['POST'])
def load_config():
    data = request.json
    cam_name = data.get('camera_name')
    
    conn = DatabaseHelper.get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM camera_channels WHERE camera_name = ?', (cam_name,))
        cam = cursor.fetchone()
        if not cam: return jsonify({'success': False, 'error': 'Camera not found'})

        cursor.execute('SELECT * FROM detection_zones WHERE camera_channel_id = ?', (cam['id'],))
        zones = cursor.fetchall()
        
        formatted_zones = []
        for z in zones:
            formatted_zones.append({
                'id': z['id'], 
                'zoneName': z['zone_name'], 
                'shapeType': z['shape_type'],
                'coordinates': json.loads(z['coordinates']), 
                'isEmpty': z['is_empty']
            })
            
        return jsonify({'success': True, 'camera': dict(cam), 'zones': formatted_zones})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/delete-camera/<int:cam_id>', methods=['DELETE'])
def api_delete_camera(cam_id):
    """Replaces delete_channel. Safely deletes the camera and cascades to delete its zones."""
    conn = DatabaseHelper.get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM camera_channels WHERE id = ?', (cam_id,))
        conn.commit()
        return jsonify({'success': True, 'message': 'Camera deleted successfully'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/dashboard-stats', methods=['GET'])
def api_dashboard_stats():
    """Generates the stats for your Live HTML Dashboard"""
    conn = DatabaseHelper.get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) as total_spaces, SUM(CASE WHEN is_empty = 1 THEN 1 ELSE 0 END) as empty_spaces FROM detection_zones WHERE shape_type = 'box'")
        spaces_data = cursor.fetchone()
        
        # Wrapped in a try/except in case is_active hasn't been added to the schema yet
        try:
            cursor.execute("SELECT COUNT(*) as total_cameras, SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as online_cameras FROM camera_channels")
            cameras_data = cursor.fetchone()
        except sqlite3.OperationalError:
            cursor.execute("SELECT COUNT(*) as total_cameras, 0 as online_cameras FROM camera_channels")
            cameras_data = cursor.fetchone()
        
        return jsonify({
            'success': True,
            'total_spaces': spaces_data['total_spaces'] or 0,
            'empty_spaces': spaces_data['empty_spaces'] or 0,
            'total_cameras': cameras_data['total_cameras'] or 0,
            'online_cameras': cameras_data['online_cameras'] or 0
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/capture-frame', methods=['POST'])
def capture_frame():
    """The ultra-simplified capture route that relies on our new SmartPSSViewer class"""
    try:
        data = request.json
        url = data.get('url') 
        
        if not url: return jsonify({'success': False, 'error': 'URL is required'}), 400
        
        viewer = SmartPSSViewer(rtsp_url=url)
        result = viewer.capture_single_frame()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==========================================
# 🚀 BACKGROUND THREAD: HARDWARE CHECK
# ==========================================
def verify_all_cameras():
    print("\n" + "="*50)
    print("🔍 RUNNING STARTUP CAMERA HEALTH CHECK...")
    print("="*50)
    conn = DatabaseHelper.get_db_connection()
    cursor = conn.cursor()
    try:
        # SILENT FIX: Automatically adds the is_active column if it doesn't exist
        try:
            cursor.execute("ALTER TABLE camera_channels ADD COLUMN is_active INTEGER DEFAULT 0")
            conn.commit()
        except:
            pass 
            
        cursor.execute('SELECT id, camera_name, stream_url FROM camera_channels')
        cameras = cursor.fetchall()
        for cam in cameras:
            print(f"Testing {cam['camera_name']}...")
            viewer = SmartPSSViewer(rtsp_url=cam['stream_url'])
            frame = viewer.capture_single_frame()
            
            is_active = 1 if frame.get('success') else 0
            cursor.execute('UPDATE camera_channels SET is_active = ? WHERE id = ?', (is_active, cam['id']))
            print(f"Result: {'✅ LIVE' if is_active else '❌ OFFLINE'}")
            
        conn.commit()
        print("✅ Camera Health Check Complete!\n")
    except Exception as e:
        print(f"❌ Error during health check: {str(e)}")
    finally:
        conn.close()

if __name__ == '__main__':
    initialize_database()
    health_thread = threading.Thread(target=verify_all_cameras, daemon=True)
    health_thread.start()
    app.run(host="0.0.0.0", debug=True, port=5000)