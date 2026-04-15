import os


# 🟢 CRITICAL FIX: You MUST put this line before importing cv2!
# This forces OpenCV to speak TCP, which is required for SmartPSS tunnels.
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

import cv2
import numpy as np
import time
import threading
import base64
from queue import Queue, LifoQueue

class SmartPSSViewer:
    def __init__(self, rtsp_url=None, **kwargs):
        self.rtsp_url = rtsp_url
        self.cap = None
        self.running = False
        self.thread = None
        
        self.display_queue = Queue(maxsize=2)      
        self.detection_queue = LifoQueue(maxsize=5)  
        self.frame_buffer = None  
        self.lock = threading.Lock()

    def _clear_queues(self):
        while not self.display_queue.empty():
            try: self.display_queue.get_nowait()
            except: pass
        while not self.detection_queue.empty():
            try: self.detection_queue.get_nowait()
            except: pass
        self.frame_buffer = None

    # # ==========================================
    # # 1. THE SINGLE FRAME CAPTURE
    # # ==========================================
    # def capture_single_frame(self):
    #     if not self.rtsp_url:
    #         return {"success": False, "error": "No RTSP URL provided"}

    #     try:
    #         print(f"📸 Snapping single frame from: {self.rtsp_url}")
            
    #         # 🟢 CRITICAL FIX: Added cv2.CAP_FFMPEG to ensure it reads the TCP environment variable!
    #         cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            
    #         ret = False
    #         frame = None
            
    #         # Read a few frames to clear the camera's internal buffer
    #         for _ in range(5):
    #             ret, frame = cap.read()
    #             if ret: break
    #             time.sleep(0.1)
                
    #         cap.release()

    #         if not ret or frame is None:
    #             return {"success": False, "error": "Could not read frame from camera"}

    #         # Convert to base64 for the frontend
    #         _, buffer = cv2.imencode('.jpg', frame)
    #         base64_image = base64.b64encode(buffer).decode('utf-8')

    #         return {"success": True, "image": base64_image}

    #     except Exception as e:
    #         return {"success": False, "error": str(e)}
    # ==========================================
    # 1. THE SINGLE FRAME CAPTURE
    # ==========================================
    def capture_single_frame(self):
        if not self.rtsp_url:
            return {"success": False, "error": "No RTSP URL provided"}

        try:
            print(f"\n📸 Snapping single frame from: {self.rtsp_url}")
            
            # Open the connection
            cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            
            if not cap.isOpened():
                print("❌ VideoCapture failed to open stream.")
                return {"success": False, "error": "Camera port blocked. Close the Dashboard tab and try again."}

            ret = False
            frame = None
            
            # Wait up to 3 seconds for the first frame to travel through the tunnel
            print("⏳ TCP connection opened! Waiting for frame data...")
            for attempt in range(30):
                ret, frame = cap.read()
                if ret and frame is not None:
                    print(f"✅ Frame successfully received on attempt {attempt+1}!")
                    break
                time.sleep(0.1)
                
            cap.release()

            if not ret or frame is None:
                print("❌ Connected, but no frame was delivered by the camera buffer.")
                return {"success": False, "error": "Stream opened, but frame buffer was empty."}

            # Convert the raw NumPy array to Base64 for the HTML canvas
            _, buffer = cv2.imencode('.jpg', frame)
            base64_image = base64.b64encode(buffer).decode('utf-8')

            print("✅ Base64 Image generated and sent to frontend!")
            return {"success": True, "image": base64_image}

        except Exception as e:
            print(f"❌ Exception in capture: {e}")
            return {"success": False, "error": str(e)}

    # ==========================================
    # 2. THE LIVE STREAM METHODS
    # ==========================================
    def start_stream(self):
        if self.running:
            self.stop_stream()
            
        print(f"\n▶️ Starting live stream for: {self.rtsp_url}")
        self._clear_queues()
        
        # 🟢 CRITICAL FIX: Ensure the live stream also uses FFMPEG/TCP
        self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        
        if not self.cap.isOpened():
            print("❌ Failed to open RTSP stream")
            return False
            
        self.running = True
        
        self.thread = threading.Thread(target=self.read_frames)
        self.thread.daemon = True
        self.thread.start()
        
        print("✅ Stream started successfully")
        return True

    def read_frames(self):
        while self.running and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
                
            self.frame_buffer = frame.copy()
            
            if self.display_queue.full():
                try: self.display_queue.get_nowait()
                except: pass
            self.display_queue.put(frame.copy())
            
            if self.detection_queue.full():
                try: self.detection_queue.get_nowait()
                except: pass
            self.detection_queue.put(frame.copy())

    def get_frame_for_display(self, timeout=0.1):
        try: return self.display_queue.get(timeout=timeout)
        except: return None
    
    def get_latest_frame_for_detection(self):
        try: return self.detection_queue.get_nowait()
        except: return self.frame_buffer.copy() if self.frame_buffer is not None else None

    def stop_stream(self):
        self.running = False
        if hasattr(self, 'thread') and self.thread:
            self.thread.join(timeout=1)
        if self.cap:
            self.cap.release()


# ==========================================
# 🧪 ISOLATED UNIT TEST
# ==========================================
if __name__ == "__main__":
    import urllib.parse
    
    print("\n" + "="*50)
    print("📹 RTSP TCP STREAM TESTER")
    print("="*50)
    
    # 1. Prompt for connection details
    ip = input("Enter IP (default: 127.0.0.1): ").strip() or "127.0.0.1"
    port = input("Enter RTSP Port (e.g., 47005): ").strip()
    channel = input("Enter Channel (default: 1): ").strip() or "1"
    user = input("Enter Username (default: admin): ").strip() or "admin"
    password = input("Enter Password: ").strip()
    
    if not port or not password:
        print("❌ Error: Port and Password are required to test!")
        exit()

    # 2. Safely construct the URL (handles @ in passwords)
    safe_password = urllib.parse.quote(password)
    test_url = f"rtsp://{user}:{safe_password}@{ip}:{port}/cam/realmonitor?channel={channel}&subtype=0"
    
    print(f"\n🔗 Attempting to connect to: {test_url}\n")
    
    # 3. Initialize the class
    viewer = SmartPSSViewer(rtsp_url=test_url)
    
    # 4. Test Route A: Single Frame Capture (What your HTML Setup pages use)
    print("📸 Test 1: Single Frame Capture...")
    result = viewer.capture_single_frame()
    if result.get("success"):
        print("✅ Single frame captured successfully! (Base64 data generated)")
    else:
        print(f"❌ Single frame capture failed: {result.get('error')}")

    # 5. Test Route B: Live Video Stream (What your Dashboard uses)
    print("\n▶️ Test 2: Live Video Stream...")
    if viewer.start_stream():
        print("⏳ Waiting for FFMPEG/TCP frames... (Press 'q' in the video window to quit)")
        
        try:
            print("⏳ Waiting for FFMPEG/TCP frames... (Press 'q' in the video window to quit)")
            while True:
                # Pull the frame from the queue
                frame = viewer.get_frame_for_display(timeout=0.1)
                
                if frame is not None:
                    # Display the frame using OpenCV
                    cv2.imshow(f"Live Stream - Channel {channel}", frame)
                    
                # Listen for the 'q' key to stop the test
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("\n⏹️ 'q' pressed. Stopping stream.")
                    break
                    
        except KeyboardInterrupt:
            print("\n⏹️ Force stopped by user.")
            
        finally:
            # Clean up memory and destroy windows
            viewer.stop_stream()
            cv2.destroyAllWindows()
            print("\n✅ Video test concluded. Memory released.")
    else:
        print("❌ Live stream failed to start.")