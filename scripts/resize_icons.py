from PIL import Image
import os
import sys

def resize_icon(input_path, output_dir):
    try:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        with Image.open(input_path) as img:
            # Resize and save for 192x192
            img_192 = img.resize((192, 192), Image.Resampling.LANCZOS)
            img_192.save(os.path.join(output_dir, 'icon-192.png'), 'PNG')
            
            # Resize and save for 512x512
            img_512 = img.resize((512, 512), Image.Resampling.LANCZOS)
            img_512.save(os.path.join(output_dir, 'icon-512.png'), 'PNG')
            
        print("Icons resized successfully.")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    base_dir = r"c:\Users\dayus\Documents\RFCListen"
    input_image = r"C:\Users\dayus\.gemini\antigravity\brain\7bd285c9-0e63-4605-ab0f-d920d992bb61\rfc_headphones_icon_1773702294508.png"
    output_directory = os.path.join(base_dir, "frontend", "icons")
    
    resize_icon(input_image, output_directory)
