from flask import Flask, render_template, Response, jsonify, request, session
import cv2
import threading
import time
import secrets
import sqlite3
import numpy as np
import math
import cvzone
from ultralytics import YOLO
from final_cam_video import SmartPSSViewer  # Your existing class

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# --- GLOBAL VARIABLES ---
viewer = None
stream_active = False
current_channel = 1
camera_config = {}

# --- AI & TRACKING GLOBALS ---
print("⏳ Loading YOLO Model...")
model = YOLO("yolov8s.pt")  # Load model once at startup
print("✅ Model Loaded.")

active_gates = []       # Stores the lines you drew [[x1,y1,x2,y2, name], ...]
gate_counts = {}        # Stores counts per gate {'Entry': [id1, id2]}

def load_gates_from_db(stream_url):
    """
    Try to find gates in the DB associated with this camera URL.
    This links your 'Gate Setup' page to this Dashboard.
    """
    global active_gates, gate_counts
    active_gates = []
    gate_counts = {}
    
    try:
        conn = sqlite3.connect('parking_system.db')
        cursor = conn.cursor()
        
        # 1. Find which DVR has this URL (simple match)
        # Note: In production, URL matching might need to be fuzzy, but exact is safer
        cursor.execute("SELECT dvr_name FROM dvr_devices WHERE stream_url = ?", (stream_url,))
        row = cursor.fetchone()
        
        if row:
            dvr_name = row[0]
            print(f"✅ Found DVR in DB: {dvr_name}. Loading gates...")
            
            # 2. Get gates for this DVR
            cursor.execute("SELECT gate_name, x1, y1, x2, y2 FROM traffic_gates WHERE dvr_name = ?", (dvr_name,))
            rows = cursor.fetchall()
            
            for r in rows:
                name, x1, y1, x2, y2 = r
                active_gates.append({
                    'name': name,
                    'line': [x1, y1, x2, y2]
                })
                gate_counts[name] = [] # Initialize counter
                print(f"   -> Loaded Gate: {name} {x1},{y1} to {x2},{y2}")
        else:
            print("⚠️ Camera URL not found in DB. No gates loaded.")
            
        conn.close()
    except Exception as e:
        print(f"❌ Database Error loading gates: {e}")

def init_viewer(config):
    """Initialize the SmartPSS viewer"""
    global viewer, camera_config
    try:
        camera_config = config
        viewer = SmartPSSViewer(
            input_url=config.get('url', ''),
            channel=int(config.get('channel', 1)),
            user=config.get('username', 'admin'),
            password=config.get('password', 'admin@123')
        )
        return True
    except Exception as e:
        print(f"Error initializing viewer: {e}")
        return False

def start_stream_thread():
    """Start the stream"""
    global viewer, stream_active
    if viewer and not stream_active:
        stream_active = viewer.start_stream()
        return stream_active
    return False

def generate_frames():
    """
    Generator: Captures frame -> Runs YOLO -> Draws Lines -> Yields JPEG
    """
    global viewer, stream_active, model, active_gates, gate_counts
    
    while stream_active:
        if viewer:
            # 1. Get raw frame
            frame = viewer.get_frame_for_display(timeout=0.1)
            
            if frame is not None:
                # ---------------------------------------------------------
                # START AI DETECTION LOGIC
                # ---------------------------------------------------------
                
                # 2. Run YOLO Tracking
                # persist=True keeps the ID same for the same car across frames
                results = model.track(frame, persist=True, verbose=False)
                
                # 3. Draw Gates (Lines)
                for gate in active_gates:
                    x1, y1, x2, y2 = gate['line']
                    name = gate['name']
                    count = len(gate_counts.get(name, []))
                    
                    # Draw Line (Red)
                    cv2.line(frame, (x1, y1), (x2, y2), (0, 0, 255), 4)
                    # Draw Text
                    cvzone.putTextRect(frame, f"{name}: {count}", (x1, y1 - 20), scale=1, thickness=2)

                # 4. Process Detected Objects
                if results[0].boxes.id is not None: # Only if objects detected
                    boxes = results[0].boxes.xyxy.int().cpu().tolist()
                    track_ids = results[0].boxes.id.int().cpu().tolist()
                    classes = results[0].boxes.cls.int().cpu().tolist()
                    
                    for box, track_id, cls in zip(boxes, track_ids, classes):
                        # Filter: 2=Car, 3=Motorcycle, 5=Bus, 7=Truck (COCO indices)
                        if cls in [2, 3, 5, 7]: 
                            x1, y1, x2, y2 = box
                            w, h = x2 - x1, y2 - y1
                            
                            # Draw Bounding Box
                            cvzone.cornerRect(frame, (x1, y1, w, h), l=9, rt=2, colorR=(255, 0, 255))
                            
                            # Calculate Center Point
                            cx, cy = x1 + w // 2, y1 + h // 2
                            cv2.circle(frame, (cx, cy), 5, (255, 0, 255), cv2.FILLED)
                            
                            # 5. Check Line Crossing
                            for gate in active_gates:
                                gx1, gy1, gx2, gy2 = gate['line']
                                name = gate['name']
                                
                                # Logic: Check if point is inside the X-range AND close to Y-line
                                # (Works best for horizontal-ish lines)
                                if (min(gx1, gx2) < cx < max(gx1, gx2)) and (min(gy1, gy2) - 20 < cy < max(gy1, gy2) + 20):
                                    
                                    # If this car ID hasn't been counted for this gate yet
                                    if track_id not in gate_counts[name]:
                                        gate_counts[name].append(track_id)
                                        # Flash line Green for visual feedback
                                        cv2.line(frame, (gx1, gy1), (gx2, gy2), (0, 255, 0), 4)

                # ---------------------------------------------------------
                # END AI LOGIC
                # ---------------------------------------------------------

                # Encode to JPEG for browser
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            else:
                time.sleep(0.01)
        else:
            time.sleep(0.1)

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/connect_camera', methods=['POST'])
def connect_camera():
    global viewer, stream_active, current_channel
    data = request.get_json()
    
    config = {
        'url': data.get('url', ''),
        'username': data.get('username', 'admin'),
        'password': data.get('password', 'admin@123'),
        'channel': int(data.get('channel', 1))
    }
    
    if not config['url']:
        return jsonify({'status': 'error', 'message': 'URL is required'})
    
    if viewer and stream_active:
        viewer.stop_stream()
        stream_active = False
        time.sleep(1)
    
    # NEW: Load gates from DB before starting stream
    load_gates_from_db(config['url'])

    if init_viewer(config):
        current_channel = config['channel']
        if start_stream_thread():
            return jsonify({
                'status': 'success', 
                'message': f'Connected on Ch {config["channel"]}. Gates Loaded: {len(active_gates)}',
                'config': {'channel': config['channel'], 'url': config['url']}
            })
        else:
            return jsonify({'status': 'error', 'message': 'Failed to start stream'})
    else:
        return jsonify({'status': 'error', 'message': 'Failed to initialize camera'})

@app.route('/disconnect_camera', methods=['POST'])
def disconnect_camera():
    global viewer, stream_active
    if viewer:
        stream_active = False
        viewer.stop_stream()
        return jsonify({'status': 'success', 'message': 'Disconnected'})
    return jsonify({'status': 'error', 'message': 'No connection'})

@app.route('/switch_channel', methods=['POST'])
def switch_channel():
    global viewer, current_channel, camera_config
    data = request.get_json()
    channel = int(data.get('channel', 1))
    
    if viewer:
        current_channel = channel
        camera_config['channel'] = channel
        viewer.current_channel = channel
        viewer.stop_stream()
        time.sleep(1)
        viewer.start_stream()
        return jsonify({'status': 'success', 'message': f'Switched to Ch {channel}'})
    return jsonify({'status': 'error', 'message': 'No active connection'})

@app.route('/get_status')
def get_status():
    global viewer, stream_active, current_channel, camera_config
    return jsonify({
        'stream_active': stream_active,
        'current_channel': current_channel,
        'ffmpeg_ok': viewer.check_ffmpeg() if viewer else False,
        'connected': viewer is not None and stream_active,
        'camera_url': camera_config.get('url', ''),
        'active_gates': len(active_gates) # Show how many lines are loaded
    })

if __name__ == '__main__':
    # threaded=True is crucial for video streaming
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)