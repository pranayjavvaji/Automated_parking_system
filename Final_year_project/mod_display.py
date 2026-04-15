# this module is already working properly we just have to add the functions which we are going to use or plan to use in future. this module is mostly used to organize the code even better
import cv2
import numpy as np

# ==========================================
# INTERNAL HELPER (Don't call this directly)
# ==========================================
def _render(window_name, frame, text, color):
    """Handles the actual drawing so we don't repeat code."""
    # If no frame is provided, create a blank dark screen
    if frame is None:
        display_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        display_frame[:] = (30, 30, 30)
    else:
        display_frame = cv2.resize(frame.copy(), (1280, 720))
        
    # Draw top banner
    cv2.rectangle(display_frame, (0, 0), (1280, 120), (20, 20, 20), -1)
    
    # Draw Window Name & Instruction Text
    cv2.putText(display_frame, f"--- {window_name.upper()} ---", (30, 40), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (150, 150, 150), 2)
    cv2.putText(display_frame, text, (30, 95), 
                cv2.FONT_HERSHEY_SIMPLEX, 1.8, color, 4)

    # Draw alignment box if a live frame is passed
    if frame is not None:
        cv2.rectangle(display_frame, (400, 400), (880, 600), (0, 255, 255), 2)

    cv2.imshow(window_name, display_frame)
    cv2.waitKey(1)

# ==========================================
# YOUR PUBLIC FUNCTIONS (Call these from main_pipeline.py!)
# ==========================================

def show_idle(window_name="ENTRY GATE"):
    """Displays the welcome screen when no car is there."""
    _render(window_name, frame=None, text="WELCOME - PLEASE PULL FORWARD", color=(255, 255, 255))

def show_stop(window_name, frame):
    """Tells the driver to stop and align their plate."""
    _render(window_name, frame, text="🛑 STOP - ALIGN PLATE", color=(0, 0, 255)) # Red

def show_scanning(window_name, frame):
    """Tells the driver the AI is thinking."""
    _render(window_name, frame, text="⏳ SCANNING...", color=(0, 255, 255)) # Yellow

def show_assigned_spot(window_name, frame, spot_name):
    """Tells the driver where to park."""
    _render(window_name, frame, text=f"✅ SUCCESS - GO TO SPOT: {spot_name}", color=(0, 255, 0)) # Green

def show_lot_full(window_name, frame=None):
    """Tells the driver to leave."""
    _render(window_name, frame, text="❌ LOT FULL - PLEASE EXIT", color=(0, 0, 255)) # Red
    
def clear_screens():
    """Closes the windows if the system shuts down."""
    cv2.destroyAllWindows()

# --- QUICK TEST BLOCK ---
if __name__ == "__main__":
    import time
    print("📺 Testing Specific Functions...")
    
    show_idle("ENTRY GATE")
    time.sleep(2)
    
    # Create a fake blank frame to simulate a camera
    fake_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    
    show_stop("ENTRY GATE", fake_frame)
    time.sleep(2)
    
    show_scanning("ENTRY GATE", fake_frame)
    time.sleep(2)
    
    show_assigned_spot("ENTRY GATE", fake_frame, "A1")
    time.sleep(2)