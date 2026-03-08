import os
import subprocess
import cv2
import numpy as np
import time
import threading
import re
from queue import Queue, LifoQueue

class SmartPSSViewer:
    def __init__(self, input_url=None, channel=1, user="admin", password="admin@123"):
        # YOUR CORRECT FFMPEG PATH
        self.ffmpeg_path = r"C:\Users\javva\Downloads\Final_year_project\ffmpeg\bin\ffmpeg.exe"
        if input_url:
            http_port, rtsp_port, tcp_port = self.parse_smartpss_url(input_url)
            print(f"Parsed ports: HTTP={http_port}, RTSP={rtsp_port}, TCP={tcp_port}")
        else:
            # Default ports if no input
            http_port, rtsp_port, tcp_port = 45132, 45136, 45128
        
        # Your RTSP base URL (will use parsed RTSP port)
        self.rtsp_base = f"rtsp://{user}:{password}@127.0.0.1:{rtsp_port}/cam/realmonitor"
        
        # Channel names - Updated for 9 channels
        self.channel_names = {
            1: "outside+road",
            2: "outside", 
            3: "Channel3",
            4: "top",
            5: "Channel5",
            6: "Channel6",
            7: "Channel7",
            8: "Channel8",
            9: "Channel9"
        }
        
        self.current_channel = channel
        self.process = None
        
        # Separate queues for different purposes
        self.display_queue = Queue(maxsize=2)      # For display in run_viewer
        self.detection_queue = LifoQueue(maxsize=5)  # For object detection (LIFO gives latest frame)
        self.frame_buffer = None  # Latest frame for quick access
        
        self.running = False
        self.lock = threading.Lock()
    def parse_smartpss_url(self, input_url):
        """
        Parse SmartPSS URL like: http://127.0.0.1:28731/?rtspport=28735&tcpport=28727
        Returns: (http_port, rtsp_port, tcp_port)
        """
        # Extract HTTP port
        http_match = re.search(r':(\d+)/', input_url)
        http_port = int(http_match.group(1)) if http_match else 28731
        
        # Extract RTSP port
        rtsp_match = re.search(r'rtspport=(\d+)', input_url)
        rtsp_port = int(rtsp_match.group(1)) if rtsp_match else (http_port + 4)
        
        # Extract TCP port
        tcp_match = re.search(r'tcpport=(\d+)', input_url)
        tcp_port = int(tcp_match.group(1)) if tcp_match else (http_port - 4)
        
        return http_port, rtsp_port, tcp_port

    def get_rtsp_url(self, channel):
        """Get RTSP URL for specific channel"""
        return f"{self.rtsp_base}?channel={channel}&subtype=0"
    
    def check_ffmpeg(self):
        """Verify FFmpeg is accessible"""
        print(f"Checking FFmpeg at: {self.ffmpeg_path}")
        
        if not os.path.exists(self.ffmpeg_path):
            print(f"❌ FFmpeg not found at: {self.ffmpeg_path}")
            print("\nPlease check the path is correct.")
            print(r"Your FFmpeg should be at: C:\ffmpeg\ffmpeg\bin\ffmpeg.exe")
            return False
        
        try:
            result = subprocess.run(
                [self.ffmpeg_path, '-version'],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0:
                print("✅ FFmpeg is working!")
                return True
            else:
                print("❌ FFmpeg test failed")
                return False
                
        except Exception as e:
            print(f"❌ Error testing FFmpeg: {e}")
            return False
    def capture_single_frame(self):
        """Capture a single frame from the RTSP stream"""
        if not self.check_ffmpeg():
            return None, "FFmpeg not found or not working"
        
        rtsp_url = self.get_rtsp_url(self.current_channel)
        print(f"Capturing frame from: {rtsp_url}")
        
        # FFmpeg command
        cmd = [
            self.ffmpeg_path,
            '-rtsp_transport', 'tcp',      # Use TCP for stability
            '-i', rtsp_url,                # Input URL
            '-f', 'image2pipe',            # Pipe output
            '-pix_fmt', 'bgr24',           # BGR format for OpenCV
            '-vcodec', 'rawvideo',         # Raw video
            '-an',                         # No audio
            '-r', '15',                    # 15 FPS
            '-s', '1280x720',              # Resolution
            '-'
        ]
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=10**7,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            width, height = 1280, 720
            frame_size = width * height * 3
            raw_frame = self.process.stdout.read(frame_size)
            
            if len(raw_frame) == frame_size:
                frame = np.frombuffer(raw_frame, dtype=np.uint8)
                frame = frame.reshape((height, width, 3))
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                return frame_rgb, None
            else:
                return None, "Failed to capture frame"
                
        except Exception as e:
            return None, f"Error: {str(e)}"
            
        finally:
            if self.process:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except:
                    self.process.kill()
    def start_stream(self):
        """Start FFmpeg stream for specific channel"""
        if self.process:
            self.stop_stream()
        
        rtsp_url = self.get_rtsp_url(self.current_channel)
        
        print(f"\nStarting stream for Channel {self.current_channel}: {self.channel_names[self.current_channel]}")
        print(f"RTSP URL: {rtsp_url}")
        
        # Clear queues
        self._clear_queues()
        
        # FFmpeg command
        cmd = [
            self.ffmpeg_path,
            '-rtsp_transport', 'tcp',      # Use TCP for stability
            '-i', rtsp_url,                # Input URL
            '-f', 'image2pipe',            # Pipe output
            '-pix_fmt', 'bgr24',           # BGR format for OpenCV
            '-vcodec', 'rawvideo',         # Raw video
            '-an',                         # No audio
            '-r', '15',                    # 15 FPS
            '-s', '1280x720',              # Resolution
            '-'
        ]
        
        print(f"FFmpeg command: {' '.join(cmd[:5])}...")
        
        try:
            # Start FFmpeg
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=10**7,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            self.running = True
            
            # Start frame reading thread
            self.thread = threading.Thread(target=self.read_frames)
            self.thread.daemon = True
            self.thread.start()
            
            # Start error reading thread
            self.error_thread = threading.Thread(target=self.read_errors)
            self.error_thread.daemon = True
            self.error_thread.start()
            
            print("✅ Stream started successfully")
            return True
            
        except Exception as e:
            print(f"❌ Failed to start stream: {e}")
            return False
    
    def _clear_queues(self):
        """Clear all frame queues"""
        while not self.display_queue.empty():
            try:
                self.display_queue.get_nowait()
            except:
                pass
        
        while not self.detection_queue.empty():
            try:
                self.detection_queue.get_nowait()
            except:
                pass
        
        self.frame_buffer = None
    
    def read_frames(self):
        """Read frames from FFmpeg output and distribute to queues"""
        width, height = 1280, 720
        frame_size = width * height * 3
        
        while self.running and self.process:
            try:
                # Read raw frame data
                raw_frame = self.process.stdout.read(frame_size)
                
                if len(raw_frame) == frame_size:
                    # Convert to numpy
                    frame = np.frombuffer(raw_frame, dtype=np.uint8)
                    frame = frame.reshape((height, width, 3)).copy()  # Make a copy
                    
                    # Store in frame buffer (latest frame)
                    self.frame_buffer = frame.copy()
                    
                    # Put in display queue (for viewer)
                    if self.display_queue.full():
                        try:
                            self.display_queue.get_nowait()
                        except:
                            pass
                    self.display_queue.put(frame.copy())
                    
                    # Put in detection queue (for object detection)
                    if self.detection_queue.full():
                        try:
                            self.detection_queue.get_nowait()
                        except:
                            pass
                    self.detection_queue.put(frame.copy())
                    
                else:
                    # Incomplete frame
                    time.sleep(0.001)
                    
            except Exception as e:
                # print(f"Frame read error: {e}")
                time.sleep(0.01)
    
    def read_errors(self):
        """Read FFmpeg error output"""
        if self.process and self.process.stderr:
            try:
                for line in iter(self.process.stderr.readline, b''):
                    if line and self.running:
                        line_str = line.decode('utf-8', errors='ignore').strip()
                        if 'error' in line_str.lower():
                            print(f"FFmpeg error: {line_str[:100]}")
            except:
                pass
    
    def get_frame_for_display(self, timeout=0.1):
        """Get frame for display (used by run_viewer)"""
        try:
            return self.display_queue.get(timeout=timeout)
        except:
            return None
    
    def get_latest_frame_for_detection(self):
        """
        Get the latest frame for object detection
        Returns: frame or None if no frame available
        """
        # Try to get from LIFO queue (latest frame)
        try:
            return self.detection_queue.get_nowait()
        except:
            # If queue is empty, return frame buffer
            return self.frame_buffer.copy() if self.frame_buffer is not None else None
    
    def open_one_frame(self, window_name="SingleFrame", do_detection=False):
        """
        Take ONE frame and display it.
        
        Args:
            window_name: Name of the display window
            do_detection: If True, will also return the frame for detection
        
        Returns:
            frame or None
        """
        frame = self.get_latest_frame_for_detection()
        
        if frame is None:
            print("No frame available for detection.")
            return None
        
        # Show the frame
        cv2.imshow(window_name, frame)
        cv2.waitKey(1)  # Brief wait to display
        
        if do_detection:
            return frame.copy()  # Return copy for detection
        
        return None
    
    def capture_frame_for_detection(self):
        """
        Capture a frame for object detection without displaying it.
        This is what you'd use in your detection loop.
        
        Returns:
            frame or None
        """
        return self.get_latest_frame_for_detection()
    
    def stop_stream(self):
        """Stop FFmpeg stream"""
        self.running = False
        
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except:
                self.process.kill()
        
        if hasattr(self, 'thread'):
            self.thread.join(timeout=1)
        
        if hasattr(self, 'error_thread'):
            self.error_thread.join(timeout=1)
        
        print("Stream stopped")
    
    def run_viewer(self):
        """Main viewer function"""
        print("=" * 70)
        print("SMART PSS FFMPEG VIEWER")
        print("=" * 70)
        print(f"FFmpeg path: {self.ffmpeg_path}")
        print("\nChannel Configuration:")
        for ch_num, ch_name in self.channel_names.items():
            print(f"  Channel {ch_num}: {ch_name}")
        print("=" * 70)
        print("\n📸 Press 'c' to capture a frame for object detection")
        print("=" * 70)
        
        # Check FFmpeg
        if not self.check_ffmpeg():
            print("\n❌ Cannot proceed without FFmpeg")
            input("Press Enter to exit...")
            return
        
        # Start stream
        if not self.start_stream():
            print("\n❌ Failed to start stream")
            return
        
        print("\n✅ Waiting for first frame...")
        
        # Wait for first frame
        frame = None
        for i in range(50):
            frame = self.get_frame_for_display(timeout=0.5)
            if frame is not None:
                print(f"✅ First frame received after {i*0.5:.1f}s")
                break
            print(f"Waiting... {i*0.5:.1f}s", end='\r')
        
        if frame is None:
            print("\n❌ No frames received")
            self.stop_stream()
            return
        
        print("\n🎉 VIDEO IS WORKING!")
        print("\nControls:")
        print("  q = Quit")
        print("  s = Save screenshot")
        print("  1-9 = Switch channel (1-9)")
        print("  f = Toggle fullscreen")
        print("  r = Restart stream")
        print("  c = Capture frame for object detection")
        print("=" * 70)
        
        frame_count = 0
        fps_time = time.time()
        
        try:
            while True:
                frame = self.get_frame_for_display(timeout=0.1)
                
                if frame is not None:
                    frame_count += 1
                    
                    # Calculate FPS
                    current_time = time.time()
                    if current_time - fps_time >= 1.0:
                        fps = frame_count
                        frame_count = 0
                        fps_time = current_time
                        print(f"FPS: {fps} - Ch: {self.current_channel}", end='\r')
                    
                    # Create display
                    display = frame.copy()
                    height, width = display.shape[:2]
                    
                    # Show frame
                    cv2.imshow(f"{self.current_channel}", display)
                    
                    # Handle keyboard
                    key = cv2.waitKey(1) & 0xFF
                    
                    if key == ord('q'):
                        break
                    elif key == ord('s'):
                        filename = f"channel{self.current_channel}_{int(time.time())}.jpg"
                        cv2.imwrite(filename, frame)
                        print(f"\n💾 Saved: {filename}")
                    elif ord('1') <= key <= ord('9'):  # Updated to handle 1-9
                        new_channel = key - ord('0')
                        if new_channel != self.current_channel and new_channel in self.channel_names:
                            print(f"\n🔄 Switching to channel {new_channel}...")
                            self.current_channel = new_channel
                            self.start_stream()
                    elif key == ord('f'):
                        # Toggle fullscreen
                        current = cv2.getWindowProperty(f"{self.current_channel}", cv2.WND_PROP_FULLSCREEN)
                        new = cv2.WINDOW_NORMAL if current == cv2.WINDOW_FULLSCREEN else cv2.WINDOW_FULLSCREEN
                        cv2.setWindowProperty(f"{self.current_channel}", cv2.WND_PROP_FULLSCREEN, new)
                    elif key == ord('r'):
                        print("\n🔄 Restarting stream...")
                        self.start_stream()
                    elif key == ord('c'):
                        # Capture frame for object detection
                        detection_frame = self.capture_frame_for_detection()
                        if detection_frame is not None:
                            print(f"\n📸 Captured frame for detection")
                            print(f"   Frame shape: {detection_frame.shape}")
                            print(f"   Channel: {self.current_channel}")
                            
                            # Show it in a separate window
                            cv2.imshow('Detection Frame', detection_frame)
                            cv2.waitKey(1)  # Brief display
                
                else:
                    # No frame - show waiting
                    waiting = np.zeros((720, 1280, 3), dtype=np.uint8)
                    cv2.putText(waiting, "Waiting for frame...", (400, 360),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                    cv2.imshow(f"{self.current_channel}", waiting)
        
        except KeyboardInterrupt:
            print("\n\nStopping...")
        
        finally:
            self.stop_stream()
            cv2.destroyAllWindows()
            print("\nViewer closed.")


# Example of how to use the detection feature:
def run_with_detection():
    """Example of running viewer with object detection integration"""
    url = input("Enter SmartPSS URL (or press Enter for default): ").strip()
    viewer = SmartPSSViewer(url) if url else SmartPSSViewer()
    
    # Start viewer in a separate thread
    viewer_thread = threading.Thread(target=viewer.run_viewer)
    viewer_thread.daemon = True
    viewer_thread.start()
    
    # Give time for stream to start
    time.sleep(3)
    
    # Your object detection loop
    print("\n🎯 Starting object detection loop...")
    while True:
        # Capture frame for detection
        frame = viewer.capture_frame_for_detection()
        
        if frame is not None:
            # Perform your object detection here
            # For example:
            # detections = your_detector.detect(frame)
            
            print(f"Frame captured: {frame.shape}")
            # Add your detection logic here
        
        time.sleep(0.1)  # Adjust as needed


# Run it
if __name__ == "__main__":
    # Run the regular viewer
    url = input("Enter SmartPSS URL (or press Enter for default): ").strip()
    viewer = SmartPSSViewer(url, channel=2) if url else SmartPSSViewer()
    viewer.run_viewer()
