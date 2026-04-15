import time
from database import DatabaseHelper
from final_cam_video import SmartPSSViewer

def verify_gate_cameras(required_roles):
    """
    Checks if the specific cameras needed for a gate are online.
    Example: required_roles = ['entry_overview', 'entry_lpr']
    """
    print("\n" + "="*50)
    print("🛡️ RUNNING PRE-FLIGHT SYSTEM CHECK...")
    print("="*50)
    
    conn = DatabaseHelper.get_db_connection()
    cursor = conn.cursor()
    
    active_urls = {}

    try:
        for role in required_roles:
            print(f"🔍 Searching database for '{role}' camera...")
            cursor.execute('SELECT camera_name, stream_url FROM camera_channels WHERE camera_role = ?', (role,))
            cam = cursor.fetchone()
            
            if not cam:
                print(f"❌ FATAL ERROR: No camera assigned to role '{role}' in Database!")
                print("👉 Fix: Go to the Admin Dashboard (Gates Setup) and assign this camera.")
                return False, {}

            print(f"📡 Found '{cam['camera_name']}'. Testing network connection...")
            
            # Use our lightweight single-frame capture to test the connection
            viewer = SmartPSSViewer(rtsp_url=cam['stream_url'])
            test_result = viewer.capture_single_frame()
            
            if test_result.get('success'):
                print(f"✅ '{cam['camera_name']}' is ONLINE and passing frames.")
                active_urls[role] = cam['stream_url']
            else:
                print(f"❌ FATAL ERROR: '{cam['camera_name']}' is offline or unreachable!")
                print(f"Reason: {test_result.get('error')}")
                return False, {}
                
        print("\n✅ ALL SYSTEMS GO! Handing over to AI Pipeline...")
        print("="*50 + "\n")
        return True, active_urls
        
    except Exception as e:
        print(f"❌ Database/System Error during check: {str(e)}")
        return False, {}
        
    finally:
        conn.close()

# --- QUICK TEST BLOCK ---
if __name__ == "__main__":
    # Test checking for the entry cameras
    # (Make sure you have assigned these roles in your gates.html first!)
    success, urls = verify_gate_cameras(['entry_overview'])
    
    if success:
        print(f"URLs retrieved for pipeline: {urls}")
    else:
        print("Pipeline blocked from starting.")