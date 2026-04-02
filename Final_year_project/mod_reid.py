import cv2
import numpy as np
import torch
import torchvision.transforms as transforms
from torchvision.models import resnet18, ResNet18_Weights
from scipy.spatial.distance import cosine

class VehicleFeatureExtractor:
    def __init__(self):
        print("🧠 [Re-ID] Loading Deep Learning Feature Extractor...")
        # Use GPU if available, otherwise CPU
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"⚙️ [Re-ID] Utilizing compute device: {self.device.type.upper()}")
        
        # Load the pre-trained ResNet18 weights
        weights = ResNet18_Weights.DEFAULT
        full_model = resnet18(weights=weights)
        
        # SLICE THE MODEL: Remove the final classification layer to get the raw 512-D features
        self.model = torch.nn.Sequential(*(list(full_model.children())[:-1]))
        self.model.to(self.device)
        self.model.eval() # Set to evaluation mode (turns off training layers)

        # The image transformations required by ResNet
        self.preprocess = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=weights.transforms().mean, std=weights.transforms().std)
        ])

    def get_vector(self, image_bgr):
        """
        Takes an OpenCV BGR image (the cropped car), passes it through the neural network,
        and returns a 512-dimensional Python list.
        """
        if image_bgr is None or image_bgr.size == 0:
            return None

        # Convert OpenCV BGR to RGB
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        
        # Preprocess and push to GPU/CPU
        tensor = self.preprocess(image_rgb).unsqueeze(0).to(self.device)
        
        # Pass through the network without calculating gradients (saves memory)
        with torch.no_grad():
            features = self.model(tensor)
            
        # Flatten the output to a 1D array and convert to a standard Python list
        feature_vector = features.flatten().cpu().numpy().tolist()
        return feature_vector

    def compare_vectors(self, vector1, vector2):
        """
        Uses Cosine Similarity to compare two vectors. 
        Returns a percentage match (0.0 to 1.0).
        """
        if not vector1 or not vector2:
            return 0.0
            
        # Scipy's cosine calculates 'distance'. 
        # Similarity is 1 - distance.
        similarity = 1 - cosine(vector1, vector2)
        
        # Ensure it doesn't drop below 0 due to float math
        return max(0.0, similarity)

# ==========================================
# UNIT TEST MODULE
# ==========================================
if __name__ == "__main__":
    print("\n" + "="*50)
    print("🧪 RUNNING UNIT TEST: mod_reid.py")
    print("="*50)
    
    extractor = VehicleFeatureExtractor()
    
    # 1. Create two dummy "cropped car" images (just random noise for testing)
    print("\n📸 Generating mock vehicle crops...")
    car_a = np.random.randint(0, 255, (300, 400, 3), dtype=np.uint8)
    car_b = np.random.randint(0, 255, (300, 400, 3), dtype=np.uint8)
    
    # 2. Extract Vectors
    print("🔢 Extracting 512-D feature vectors...")
    vec_a = extractor.get_vector(car_a)
    vec_b = extractor.get_vector(car_b)
    
    print(f"✅ Vector A generated. Length: {len(vec_a)}")
    
    # 3. Compare them
    # Comparing Car A to itself should be a 100% match
    match_same = extractor.compare_vectors(vec_a, vec_a)
    print(f"🔍 Similarity (Car A vs Car A): {match_same * 100:.2f}% (Expected ~100%)")
    
    # Comparing Car A to Car B (random noise) should be a low match
    match_diff = extractor.compare_vectors(vec_a, vec_b)
    print(f"🔍 Similarity (Car A vs Car B): {match_diff * 100:.2f}% (Expected low %)")
    
    print("\n✅ MODULE TEST COMPLETE. READY FOR PIPELINE.")