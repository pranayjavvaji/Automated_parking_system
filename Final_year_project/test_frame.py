import cv2
import numpy as np
import easyocr
import re
from ultralytics import YOLO
import concurrent.futures # 🟢 THE MULTITHREADING LIBRARY

from mod_reid import VehicleFeatureExtractor

class VehicleProcessor:
    def __init__(self, plate_model_path="Number_plate_Detection.pt"):
        print("⏳ [Processor] Initializing AI Models. Please wait...")
        
        self.plate_detector = YOLO(plate_model_path)
        self.reader = easyocr.Reader(['en'], gpu=False) # Runs on CPU
        self.reid = VehicleFeatureExtractor()           # Runs on GPU
        
        # Create a thread pool for parallel tasks
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        
        print("✅ [Processor] All models loaded & Thread Pool ready!")

    def _threaded_ocr(self, plate_crop):
        """Helper function to run EasyOCR in a separate thread"""
        ocr_results = self.reader.readtext(plate_crop)
        highest_prob = 0
        best_text = None
        
        for (bbox, text, prob) in ocr_results:
            clean_text = re.sub(r'[^A-Za-z0-9]', '', text).upper()
            if len(clean_text) >= 4 and prob > highest_prob:
                highest_prob = prob
                best_text = clean_text
        return best_text

    def _threaded_vector(self, image_crop):
        """Helper function to run Re-ID in a separate thread"""
        return self.reid.get_vector(image_crop)

    def process_car(self, car_crop_img):
        """
        CONTRACT:
        INPUT: A cropped image of the CAR.
        OUTPUT: (plate_text, car_vector, plate_vector)
        """
        if car_crop_img is None or car_crop_img.size == 0:
            return None, None, None

        # --- 🚀 STAGE 1: PARALLEL GPU TASKS ---
        # Fire off the Car Vector generation to a background worker
        future_car_vector = self.thread_pool.submit(self._threaded_vector, car_crop_img)
        
        # While the background worker does the vector, the main thread runs YOLO
        results = self.plate_detector(car_crop_img, verbose=False)
        
        plate_text = None
        plate_vector = None

        # --- STAGE 2: CONDITIONAL PARALLEL TASKS ---
        if len(results[0].boxes) > 0:
            box = results[0].boxes[0].xyxy[0].cpu().numpy()
            x1, y1, x2, y2 = map(int, box)
            
            # Crop with padding
            h, w = car_crop_img.shape[:2]
            plate_crop = car_crop_img[max(0, y1-5):min(h, y2+5), max(0, x1-5):min(w, x2+5)]
            
            # Fire off the OCR (CPU) and Plate Vector (GPU) simultaneously
            future_ocr = self.thread_pool.submit(self._threaded_ocr, plate_crop)
            future_plate_vector = self.thread_pool.submit(self._threaded_vector, plate_crop)
            
            # Wait for Stage 2 tasks to finish
            plate_text = future_ocr.result()
            plate_vector = future_plate_vector.result()

        # --- THE SYNC POINT ---
        # Before we return, we MUST ensure the Stage 1 Car Vector is actually finished.
        # If YOLO was super fast, it might still be generating.
        car_vector = future_car_vector.result()

        return plate_text, car_vector, plate_vector

# ==========================================
# 🧪 ISOLATED UNIT TEST
# ==========================================
if __name__ == "__main__":
    import time
    import cv2
    import tkinter as tk
    from tkinter import filedialog

    print("\n" + "="*50)
    print("🚀 TESTING MULTITHREADED VEHICLE PROCESSOR")
    print("="*50)
    
    # 1. Initialize your AI Processor
    processor = VehicleProcessor(r"C:\Users\javva\Downloads\Final_project\Final_year_project\Number_plate_Detection.pt")
    
    print("\n📸 Opening file picker... Please select a car image.")
    
    # --- THE REUSABLE FILE PICKER SNIPPET ---
    root = tk.Tk()
    root.attributes('-topmost', True) # Forces the popup to appear in front of VS Code
    root.withdraw() # Hides the ugly default blank tkinter window
    
    # Open the dialog box asking for an image
    image_path = filedialog.askopenfilename(
        title="Select a Car Image to Test",
        filetypes=[("Image files", "*.jpg *.jpeg *.png")]
    )
    # ----------------------------------------
    
    # 2. Safety Check: Did the user hit "Cancel"?
    if not image_path:
        print("❌ No file selected. Exiting test.")
        exit()

    print(f"✅ Loading image from: {image_path}")
    
    # 3. Read the real image using OpenCV
    real_car_img = cv2.imread(image_path)
    
    # Safety Check: Is the image corrupted or missing?
    if real_car_img is None:
        print("❌ Error: OpenCV could not read the image file.")
        exit()
        
    print("⚙️ Processing real car (Timing the threaded execution)...")
    start_time = time.time()
    
    # 4. Feed the REAL image into our AI processor
    plate_result, car_vec, plate_vec = processor.process_car(real_car_img)
    
    end_time = time.time()
    
    # 5. Print out the results
    print("\n--- RESULTS ---")
    print(f"⏱️ Total Processing Time: {end_time - start_time:.3f} seconds")
    print(f"🚗 Car Vector: {'✅ Generated' if car_vec is not None else '❌ Failed'}")
    print(f"🪪 Plate Vector: {'✅ Generated' if plate_vec is not None else '⚠️ None (No plate found)'}")
    print(f"📝 Plate Text: {plate_result if plate_result else '⚠️ None (OCR failed or no plate)'}")