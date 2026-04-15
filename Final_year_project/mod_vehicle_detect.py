import cv2
from ultralytics import YOLO

print("⏳ Loading Vehicle Detection Module...")
# Using the fast nano model
model = YOLO('yolov8n.pt') 

# Map YOLO's internal ID numbers to simple words
VEHICLE_CLASSES = {
    2: "car",
    3: "bike",
    5: "bus",
    7: "truck"
}

def check_for_vehicle(camera_url):
    """
    CONTRACT:
    INPUT: The stream URL of the camera you want to check (Entry or Exit).
    OUTPUT: A dictionary containing if it was detected, what type it is, and the picture.
    """
    # 1. Open the camera and snap exactly one frame
    cap = cv2.VideoCapture(camera_url)
    ret, frame = cap.read()
    cap.release() # Immediately close connection to save memory
    
    if not ret or frame is None:
        print("⚠️ Warning: Camera offline or frame dropped.")
        return {"detected": False, "type": None, "frame": None}
        
    # 2. Ask YOLO to find cars, bikes, buses, or trucks (confidence > 50%)
    results = model(frame, classes=[2, 3, 5, 7], conf=0.5, verbose=False)
    
    # 3. Did it see anything?
    if len(results[0].boxes) > 0:
        # Get the highest-confidence vehicle it found
        best_box = results[0].boxes[0]
        class_id = int(best_box.cls[0].item())
        
        # Translate the ID (e.g., 2) into a word (e.g., "car")
        vehicle_type = VEHICLE_CLASSES.get(class_id, "unknown")
        
        return {
            "detected": True, 
            "type": vehicle_type, 
            "frame": frame 
        }
        
    # 4. If nothing was found
    return {
        "detected": False, 
        "type": None, 
        "frame": frame
    }



# --- QUICK TEST BLOCK ---
if __name__ == "__main__":
    print("🚀 Testing On-Demand Vehicle Detection...")
    
    # Passing 0 opens your laptop webcam for a quick test
    result = check_for_vehicle(0)
    
    if result["detected"]:
        print(f"✅ Found a {result['type'].upper()}!")
        # Show the picture it took
        cv2.imshow("Snapshot", result["frame"])
        cv2.waitKey(0)
    else:
        print("❌ No vehicle detected.")