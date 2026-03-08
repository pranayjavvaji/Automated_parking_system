import glob
import cv2
import os
from ultralytics import YOLO

# ----------------------------------------------------
# Load your model
# ----------------------------------------------------
model = YOLO("best.pt")    # or "yolov8n.pt"

# ----------------------------------------------------
# Input + Output folders
# ----------------------------------------------------
input_folder = "Images/"        # folder containing input images
output_folder = "results/"      # folder to save output images

os.makedirs(output_folder, exist_ok=True)

# ----------------------------------------------------
# Get all image files
# ----------------------------------------------------
image_paths = glob.glob(input_folder + "/*.jpg") + \
              glob.glob(input_folder + "/*.jpeg") + \
              glob.glob(input_folder + "/*.png")

print(f"Found {len(image_paths)} images.")

# ----------------------------------------------------
# Run detection on each image
# ----------------------------------------------------
for img_path in image_paths:
    print("\nProcessing:", img_path)

    # read image
    img = cv2.imread(img_path)
    if img is None:
        print("❌ Failed to read image:", img_path)
        continue

    # run YOLO
    results = model(img, verbose=False)[0]

    # print console detections
    for box in results.boxes:
        cls = int(box.cls[0])
        conf = float(box.conf[0])
        print(f" → Class: {cls}, Confidence: {conf:.2f}")

    # plot and save output
    plotted = results.plot()

    filename = os.path.basename(img_path)
    save_path = os.path.join(output_folder, filename)
    cv2.imwrite(save_path, plotted)

    print("✔ Saved:", save_path)

print("\nDone!")