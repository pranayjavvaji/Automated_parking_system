import cv2
import numpy as np
import time
import threading
import base64
from queue import Queue, LifoQueue

class SmartPSSViewer:
    # 🟢 THE CONSTRUCTOR FIX: It now only needs the glued RTSP string!
    def __init__(self, rtsp_url=None, **kwargs):
        self.rtsp_url = rtsp_url
        self.cap = None
        self.running = False
        self.thread = None
        
        # We keep your exact queue system so the live dashboard doesn't break
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

    # ==========================================
    # 1. THE SINGLE FRAME CAPTURE (For Plotting/Gates HTML)
    # ==========================================
    def capture_single_frame(self):
        """
        Grabs one frame and encodes it to base64.
        Matches exactly what app.py expects for the setup pages.
        """
        if not self.rtsp_url:
            return {"success": False, "error": "No RTSP URL provided"}

        try:
            print(f"📸 Snapping single frame from: {self.rtsp_url}")
            cap = cv2.VideoCapture(self.rtsp_url)
            
            # Read a few frames to clear the camera's internal buffer
            for _ in range(3):
                ret, frame = cap.read()
                
            cap.release()

            if not ret or frame is None:
                return {"success": False, "error": "Could not read frame from camera"}

            # Convert to base64 for the frontend
            _, buffer = cv2.imencode('.jpg', frame)
            base64_image = base64.b64encode(buffer).decode('utf-8')

            return {"success": True, "image": base64_image}

        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==========================================
    # 2. THE LIVE STREAM METHODS (For Dashboard HTML)
    # ==========================================
    def start_stream(self):
        if self.running:
            self.stop_stream()
            
        print(f"\n▶️ Starting live stream for: {self.rtsp_url}")
        self._clear_queues()
        
        # OpenCV connects directly to the IP camera
        self.cap = cv2.VideoCapture(self.rtsp_url)
        
        if not self.cap.isOpened():
            print("❌ Failed to open RTSP stream")
            return False
            
        self.running = True
        
        # Start background reading thread
        self.thread = threading.Thread(target=self.read_frames)
        self.thread.daemon = True
        self.thread.start()
        
        print("✅ Stream started successfully")
        return True

    def read_frames(self):
        """Background thread that continuously pulls frames from the camera."""
        while self.running and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
                
            self.frame_buffer = frame.copy()
            
            # Feed the display queue (for the web dashboard)
            if self.display_queue.full():
                try: self.display_queue.get_nowait()
                except: pass
            self.display_queue.put(frame.copy())
            
            # Feed the detection queue (for YOLO)
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