# this module has to find the parking slot which is empty and return the image with box of parking slot which was found empty and name of the  parking slot so we can use that  to display in koisk
import cv2
import sqlite3
import os
from ultralytics import YOLO

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'parking_system.db')

print("⏳ Loading YOLOv8 Occupancy Module...")
model = YOLO('yolov8s.pt') # 🟢 Future Swap: Change to yolov11.pt next year without breaking anything!

def get_candidate_spots(vehicle_type):
    """Asks the database which spots we *think* are empty."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT ps.id, ps.space_name, ps.x_min, ps.y_min, ps.x_max, ps.y_max, 
               d.stream_url, cc.channel_number
        FROM parking_spaces ps
        JOIN camera_channels cc ON ps.camera_channel_id = cc.id
        JOIN dvr_devices d ON cc.dvr_device_id = d.id
        WHERE ps.space_type LIKE ? AND ps.is_empty = 1
        ORDER BY ps.id ASC
    ''', (f'%{vehicle_type}%',))
    
    spots = cursor.fetchall()
    conn.close()
    return [dict(s) for s in spots]

def find_empty_spot(vehicle_type="car"):
    """
    CONTRACT:
    INPUT: Vehicle type string (e.g., "car" or "bike").
    OUTPUT: A dictionary of the empty spot's info, OR None if lot is full.
    """
    candidate_spots = get_candidate_spots(vehicle_type)
    
    if not candidate_spots:
        return None # Database says lot is 100% full

    # Group spots by camera URL so we only open each camera stream ONCE
    cameras = {}
    for spot in candidate_spots:
        url = spot['stream_url']
        if url not in cameras:
            cameras[url] = []
        cameras[url].append(spot)

    # 🟢 Set AI target: 2 for Cars, 3 for Motorcycles (COCO Dataset)
    target_class = [2] if "car" in vehicle_type.lower() else [3]

    for cam_url, spots_in_cam in cameras.items():
        # 1. Grab exactly ONE frame from this camera
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "timeout;2000"
        cap = cv2.VideoCapture(cam_url, cv2.CAP_FFMPEG)
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            print(f"⚠️ Warning: Camera offline ({cam_url})")
            continue
            
        frame = cv2.resize(frame, (1280, 720))

        # 2. Check each spot in this camera's view
        for spot in spots_in_cam:
            x1, y1, x2, y2 = spot['x_min'], spot['y_min'], spot['x_max'], spot['y_max']
            crop = frame[max(0, y1):y2, max(0, x1):x2]

            # 3. Run YOLO inference on the tiny cropped image
            results = model(crop, classes=target_class, conf=0.4, verbose=False)

            if len(results[0].boxes) == 0:
                # 🟢 NO CAR DETECTED! The AI confirms the spot is actually empty!
                return spot

    # If we checked every camera and every spot had a car sitting in it
    return None

# --- QUICK TEST BLOCK ---
if __name__ == "__main__":
    print("🚀 Testing Occupancy Module...")
    spot = find_empty_spot("car")
    if spot:
        print(f"✅ Success! Found empty spot: {spot['space_name']}")
    else:
        print("❌ Lot Full or Cameras Offline.")