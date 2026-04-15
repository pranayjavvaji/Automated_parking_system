# have to think of either having two separate files or have a single file and using multiple processing to analyse two different camears for entry and exit at the same time.
# have to think of either having two separate files or have a single file and using multiple processing to analyse two different camears for entry and exit at the same time.
import cv2
import time
import math
from datetime import datetime
from database import DatabaseHelper
import mod_display
import mod_vehicle_detect
import mod_plate_reader
import mod_occupancy

# Our "In-Memory JSON" to hold the camera data
GATE_CONFIG = {}

def load_gates_from_database():
    print("⚙️ Fetching Gate and Camera configurations...")
    conn = DatabaseHelper.get_db_connection()
    cursor = conn.cursor()
    
    # Use a JOIN to grab the Gate logic AND the Camera credentials in one lightning-fast query
    cursor.execute('''
        SELECT 
            tg.gate_role, tg.points, tg.shape_type, tg.entry_vector,
            cc.ip_address, cc.rtsp_port, cc.channel, cc.username, cc.password
        FROM traffic_gates tg
        JOIN camera_channels cc ON tg.camera_channel_id = cc.id
    ''')
    gates = cursor.fetchall()
    conn.close()
    
    for gate in gates:
        gate_role = gate['gate_role'] # 'entry' or 'exit'
        
        # ---------------------------------------------------------
        # THE GLUE: Reconstruct the RTSP link with the CHANNEL!
        # ---------------------------------------------------------
        ip = gate['ip_address']
        port = gate['rtsp_port']
        ch = gate['channel']
        user = gate['username']
        pwd = gate['password']
        
        # Format for Dahua/CP Plus/Hikvision
        full_rtsp_url = f"rtsp://{user}:{pwd}@{ip}:{port}/cam/realmonitor?channel={ch}&subtype=1"
        
        # Save it to our fast RAM dictionary
        GATE_CONFIG[gate_role] = {
            "camera_url": full_rtsp_url,
            "shape_type": gate['shape_type'],
            "points": gate['points'],          # e.g., "[[300, 400], [980, 720]]"
            "entry_vector": gate['entry_vector']
        }
    
    print(f"✅ Loaded {len(GATE_CONFIG)} gates into memory!")

def run_entry_pipeline():
    print("🚀 STARTING ENTRY GATE PIPELINE...")
    
    # 1. Look up the Entry camera from our cached JSON!
    if 'entry' not in GATE_CONFIG:
        print("❌ CRITICAL ERROR: No entry gate found in the database. Shutting down.")
        return
        
    cam_url = GATE_CONFIG['entry']['camera_url']
    target_zone = GATE_CONFIG['entry']['target_zone']
    
    # 2. Start the camera using the cached URL
    cap = cv2.VideoCapture(cam_url)
    while True:
        # ---------------------------------------------------------
        # PHASE 1: THE IDLE STATE (Waiting for a car)
        # ---------------------------------------------------------
        mod_display.show_idle("ENTRY GATE")
        history = [] # To track car movement
        
        while True:
            ret, frame = cap.read()
            if not ret: continue

            # Change TARGET_ZONE to target_zone
            vision = mod_vehicle_detect.check_trigger_zone(frame, target_zone)
            
            if not vision["detected"]:
                history = [] # Reset history if the car backs up or leaves
                mod_display.show_idle("ENTRY GATE")
                cv2.waitKey(1)
                continue

            # ---------------------------------------------------------
            # PHASE 2: THE APPROACH & ZERO-VELOCITY TRIGGER
            # ---------------------------------------------------------
            # The car is in the box! Tell them to stop.
            mod_display.show_stop("ENTRY GATE", frame)
            
            current_center = vision["centroid"]
            history.append(current_center)
            
            # Keep only the last 5 frames of movement history
            if len(history) > 5:
                history.pop(0)
                
                # Calculate how far the car moved between the 1st and 5th frame
                old_x, old_y = history[0]
                new_x, new_y = history[-1]
                distance_moved = math.hypot(new_x - old_x, new_y - old_y)
                
                if distance_moved < 3.0: 
                    # THE CAR HAS COMPLETELY STOPPED!
                    print("\n🛑 Zero-Velocity Triggered! Car has stopped.")
                    break # Break out of the waiting loop!
                    
        # ---------------------------------------------------------
        # PHASE 3: THE SNAP & OCR
        # ---------------------------------------------------------
        mod_display.show_scanning("ENTRY GATE", frame)
        
        # We grab one fresh, perfectly still frame right after they stop
        ret, clean_frame = cap.read() 
        print("📸 Snapped crystal-clear photo. Running OCR...")
        
        plate_text = mod_plate_reader.read_plate(clean_frame)
        
        if not plate_text:
            print("❌ OCR Failed. Could not read plate.")
            # In real life, maybe print a manual ticket here, but for now we reset
            time.sleep(3)
            continue
            
        print(f"✅ Plate Read: {plate_text}")

        # ---------------------------------------------------------
        # PHASE 4: SPOT ALLOCATION & DATABASE LOGGING
        # ---------------------------------------------------------
        print("🔍 Searching for an empty spot...")
        assigned_spot = mod_occupancy.find_empty_spot("car")
        
        if not assigned_spot:
            print("❌ LOT FULL.")
            mod_display.show_lot_full("ENTRY GATE", clean_frame)
            time.sleep(5) # Wait for them to read it and drive away
            continue
            
        print(f"✅ Found Spot: {assigned_spot['space_name']}")
        
        # Log it to the database
        conn = DatabaseHelper.get_db_connection()
        cursor = conn.cursor()
        try:
            # Mark spot as taken so no one else gets it
            cursor.execute('UPDATE parking_spaces SET is_empty = 0 WHERE id = ?', (assigned_spot['id'],))
            
            # Create the billing log
            plate_vector = ",".join([str(ord(c)) for c in plate_text])
            cursor.execute('''
                INSERT INTO parking_logs (plate_number, plate_vector, vehicle_type, assigned_space_id, entry_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (plate_text, plate_vector, "car", assigned_spot['id'], datetime.now()))
            
            conn.commit()
            print("💾 Database updated successfully.")
        except Exception as e:
            print(f"❌ Database Error: {e}")
        finally:
            conn.close()

        # ---------------------------------------------------------
        # PHASE 5: DRIVER SUCCESS
        # ---------------------------------------------------------
        # ---------------------------------------------------------
        # PHASE 5: DRIVER SUCCESS & GATE CLEAR CHECK
        # ---------------------------------------------------------
        mod_display.show_assigned_spot("ENTRY GATE", clean_frame, assigned_spot['space_name'])
        print("🏁 Transaction Complete. Waiting for car to clear the gate...")

        # Extract the boundaries of our box for easy math
        rx1, ry1, rx2, ry2 = target_zone

        while True:
            ret, check_frame = cap.read()
            if not ret: continue

            vision_check = mod_vehicle_detect.check_trigger_zone(check_frame, target_zone)

            # Scenario A: The car drove so fast it completely left the camera frame
            if not vision_check["detected"]:
                print("✅ Gate is clear (Car left frame). Ready for next vehicle!")
                time.sleep(1)
                break

            # Scenario B: (YOUR LOGIC) YOLO still sees a car, but did its centroid cross the line?
            cx, cy = vision_check["centroid"]
            
            # If the center of the car is outside the Left, Right, Top, or Bottom of the box
            if cx < rx1 or cx > rx2 or cy < ry1 or cy > ry2:
                print("✅ Gate is clear (Centroid crossed the boundary). Ready for next vehicle!")
                time.sleep(1) # Tiny buffer before flashing the welcome screen
                break

if __name__ == "__main__":
    load_gates_from_database()
    run_entry_pipeline()