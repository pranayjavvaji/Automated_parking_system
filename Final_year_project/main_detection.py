import cv2
import numpy as np
import subprocess
import sqlite3
import re
from ultralytics import YOLO
import cvzone

class VideoCamera:
    def __init__(self):
        self.is_running = True
        self.model = YOLO("yolov8n.pt")
        
        # Dictionary to store counts for EACH gate separately
        # Example: {'Entry': [id1, id2], 'Exit': [id3]}
        self.gate_counts = {} 
        self.process = None
        
        # 1. HARDCODED FFMPEG PATH
        self.ffmpeg_path = r"C:\Users\javva\Downloads\Final_year_project\ffmpeg\bin\ffmpeg.exe"
        
        # 2. Load Configuration (URL + GATES) from Database
        self.rtsp_url, self.gates = self.load_config_from_db()
        
        # Initialize counts for each loaded gate
        for gate in self.gates:
            self.gate_counts[gate['name']] = []

        if not self.rtsp_url:
            print("❌ Error: No Camera/DVR found in DB.")
        else:
            print(f"✅ Loaded {len(self.gates)} gates from database.")
            print(f"✅ Connecting to: {self.rtsp_url}")
            self.start_ffmpeg_stream()

    def load_config_from_db(self):
        """Fetch connection info AND traffic gates from the database"""
        try:
            conn = sqlite3.connect('parking_system.db')
            cursor = conn.cursor()
            
            # A. Get the DVR connection info
            cursor.execute("SELECT dvr_name, stream_url, username, password FROM dvr_devices LIMIT 1")
            dvr = cursor.fetchone()
            
            if not dvr:
                conn.close()
                return None, []
            
            dvr_name, raw_url, user, pwd = dvr
            
            # A.1 Construct the RTSP Link (using your working logic)
            final_url = self.construct_rtsp_url(raw_url, user, pwd)

            # B. Get the Gates for this DVR
            cursor.execute("SELECT gate_name, x1, y1, x2, y2 FROM traffic_gates WHERE dvr_name = ?", (dvr_name,))
            rows = cursor.fetchall()
            
            gates = []
            for r in rows:
                gates.append({
                    'name': r[0],
                    'line': [r[1], r[2], r[3], r[4]] # [x1, y1, x2, y2]
                })
            
            conn.close()
            return final_url, gates
            
        except Exception as e:
            print(f"❌ Database Error: {e}")
            return None, []

    def construct_rtsp_url(self, input_url, user, pwd):
        """Helper to build the RTSP string correctly"""
        if "rtsp://" in input_url:
            if "@" not in input_url:
                return input_url.replace("rtsp://", f"rtsp://{user}:{pwd}@")
            return input_url
            
        # Parse ports from SmartPSS URL
        rtsp_match = re.search(r'rtspport=(\d+)', input_url)
        if rtsp_match:
            rtsp_port = rtsp_match.group(1)
        else:
            http_match = re.search(r':(\d+)/', input_url)
            rtsp_port = int(http_match.group(1)) + 4 if http_match else 554
        
        ip = "127.0.0.1" # Localhost tunnel
        return f"rtsp://{user}:{pwd}@{ip}:{rtsp_port}/cam/realmonitor?channel=1&subtype=0"

    def start_ffmpeg_stream(self):
        """Starts FFmpeg to pipe video"""
        if not self.rtsp_url: return

        cmd = [
            self.ffmpeg_path,
            '-rtsp_transport', 'tcp',
            '-i', self.rtsp_url,
            '-f', 'image2pipe',
            '-pix_fmt', 'bgr24',
            '-vcodec', 'rawvideo',
            '-an',
            '-r', '15',
            '-s', '1280x720',
            '-'
        ]
        
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=10**7,
                startupinfo=startupinfo
            )
        except Exception as e:
            print(f"❌ FFmpeg failed: {e}")

    def get_frame(self):
        if not self.process: return None

        width, height = 1280, 720
        frame_size = width * height * 3

        try:
            # 1. Read raw frame
            raw_frame = self.process.stdout.read(frame_size)
            if len(raw_frame) != frame_size: return None

            # 2. Convert to Numpy Image
            frame = np.frombuffer(raw_frame, dtype=np.uint8)
            frame = frame.reshape((height, width, 3))

            # 3. RUN YOLO TRACKING
            # persist=True maintains IDs (ID 1, ID 2, etc.)
            results = self.model.track(frame, persist=True, stream=True, verbose=False)

            # 4. Loop through results
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    # Only process if we have a valid ID
                    if box.id is None: continue

                    # Box Coordinates
                    x1, y1, x2, y2 = box.xyxy[0]
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                    w, h = x2 - x1, y2 - y1
                    
                    # Class Name
                    cls = int(box.cls[0])
                    currentClass = self.model.names[cls]

                    # Filter for vehicles only
                    if currentClass in ["car", "bus", "truck", "motorbike"]:
                        
                        # Calculate Center Point
                        cx, cy = x1 + w // 2, y1 + h // 2
                        
                        # Draw Visuals
                        cvzone.cornerRect(frame, (x1, y1, w, h), l=9, rt=2, colorR=(255, 0, 255))
                        cv2.circle(frame, (cx, cy), 5, (255, 0, 255), cv2.FILLED)

                        # 5. CHECK GATES (The core logic)
                        # We loop through EVERY gate loaded from the DB
                        for gate in self.gates:
                            gate_name = gate['name']
                            gx1, gy1, gx2, gy2 = gate['line']
                            
                            # Check if car center is crossing this specific line
                            # Condition: Within X range AND within small Y distance
                            if (min(gx1, gx2) < cx < max(gx1, gx2)) and (min(gy1, gy2) - 20 < cy < max(gy1, gy2) + 20):
                                
                                obj_id = int(box.id[0])
                                
                                # Check if this specific car ID has been counted for this gate
                                if self.gate_counts.get(gate_name) is None:
                                    self.gate_counts[gate_name] = []

                                if obj_id not in self.gate_counts[gate_name]:
                                    self.gate_counts[gate_name].append(obj_id)
                                    
                                    # Visual Feedback: Flash Line Green
                                    cv2.line(frame, (gx1, gy1), (gx2, gy2), (0, 255, 0), 5)
            
            # 6. Draw All Gates & Counts on Screen
            y_offset = 50
            for gate in self.gates:
                name = gate['name']
                gx1, gy1, gx2, gy2 = gate['line']
                count = len(self.gate_counts.get(name, []))
                
                # Draw the line (Red by default)
                cv2.line(frame, (gx1, gy1), (gx2, gy2), (0, 0, 255), 3)
                
                # Draw the Label on the line
                cv2.putText(frame, f"{name}", (gx1, gy1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
                
                # Draw the Counter in the corner
                cvzone.putTextRect(frame, f'{name}: {count}', (50, y_offset), scale=1.5, thickness=2, offset=10)
                y_offset += 50

            # 7. Encode for Web
            ret, jpeg = cv2.imencode('.jpg', frame)
            return jpeg.tobytes()

        except Exception as e:
            return None

    def stop(self):
        self.is_running = False
        if self.process:
            self.process.terminate()
            self.process = None