"""
Virtual Try-On Service with 3D Effects

Uses Nano Banana Pro API for virtual try-on functionality.
Preserves 3D effects processing which is pure image manipulation.
"""
import os
import time
import shutil
import tempfile 
from pathlib import Path
from typing import Any, Dict, Optional, Union, Literal
from PIL import Image, ImageFilter
import numpy as np
import cv2

from .nanobanana_service import NanoBananaClient, get_public_url_for_image


TOP_ALIASES = {"top", "top-wear", "upper", "upper-body", "shirt"}
BOTTOM_ALIASES = {"bottom", "bottom-wear", "lower", "lower-body", "pants", "shorts"}
OUTFIT_ALIASES = {"outfit", "suit", "co-ord", "coord", "set"}
DRESS_ALIASES = {"dress", "full-body", "one-piece"}


def _has_any(text: str, keywords) -> bool:
    return any(keyword in text for keyword in keywords)


def normalize_tryon_action(garment_category: Optional[str], description_text: str = "") -> str:
    """
    Resolve try-on action. Frontend button wins; product text is only fallback.
    """
    selected = (garment_category or "").strip().lower()
    text = (description_text or "").strip().lower()

    if selected in TOP_ALIASES:
        return "top"
    if selected in BOTTOM_ALIASES:
        return "bottom"
    if selected in OUTFIT_ALIASES:
        return "outfit"
    if selected in DRESS_ALIASES:
        return "dress"

    if _has_any(text, ["dress", "gown", "jumpsuit", "romper"]):
        return "dress"
    if _has_any(text, ["pants", "jeans", "trousers", "chinos", "slacks", "shorts", "skirt", "leggings"]):
        return "bottom"
    if _has_any(text, ["top", "shirt", "t-shirt", "tshirt", "blouse", "sweater", "jacket", "coat", "hoodie"]):
        return "top"

    return "top"


def build_garment_intent(garment_category: Optional[str], description_text: str = "") -> Dict[str, Any]:
    """
    Convert button intent and product text into deterministic prompt metadata.
    """
    text = (description_text or "").lower()
    action = normalize_tryon_action(garment_category, text)

    subtype = "garment"
    if _has_any(text, ["jumpsuit"]):
        subtype = "jumpsuit"
    elif _has_any(text, ["romper"]):
        subtype = "romper"
    elif _has_any(text, ["dress", "gown"]):
        subtype = "dress"
    elif _has_any(text, ["shorts", "short pant", "half pant", "half-pant"]):
        subtype = "shorts"
    elif _has_any(text, ["jeans", "denim"]):
        subtype = "jeans"
    elif _has_any(text, ["pants", "trousers", "chinos", "slacks"]):
        subtype = "pants"
    elif _has_any(text, ["skirt"]):
        subtype = "skirt"
    elif _has_any(text, ["leggings", "tights", "yoga pants"]):
        subtype = "leggings"
    elif _has_any(text, ["hoodie"]):
        subtype = "hoodie"
    elif _has_any(text, ["jacket", "coat", "blazer"]):
        subtype = "jacket"
    elif _has_any(text, ["t-shirt", "tshirt", "tee"]):
        subtype = "t-shirt"
    elif _has_any(text, ["shirt", "top", "blouse", "sweater", "polo"]):
        subtype = "top"

    sleeve_length = "unknown"
    if _has_any(text, ["sleeveless", "tank", "vest"]):
        sleeve_length = "sleeveless"
    elif _has_any(text, ["long sleeve", "long-sleeve", "full sleeve", "full-sleeve", "full sleeves"]):
        sleeve_length = "long"
    elif _has_any(text, ["short sleeve", "short-sleeve", "half sleeve", "half-sleeve", "half sleeves"]):
        sleeve_length = "short"
    elif subtype in ["t-shirt", "polo"]:
        sleeve_length = "short"

    hem_length = "unknown"
    if subtype == "shorts":
        hem_length = "above-knee"
    elif subtype in ["jeans", "pants", "leggings"]:
        hem_length = "full-length"
    elif subtype == "skirt":
        hem_length = "skirt"
    elif subtype in ["dress", "jumpsuit", "romper"]:
        hem_length = "one-piece"

    model_category = {
        "top": "Upper-body",
        "bottom": "Lower-body",
        "outfit": "Outfit",
        "dress": "Dress",
    }[action]

    if action == "outfit" and subtype in ["dress", "jumpsuit", "romper"]:
        model_category = "Dress"

    return {
        "action": action,
        "model_category": model_category,
        "subtype": subtype,
        "sleeve_length": sleeve_length,
        "hem_length": hem_length,
        "description": description_text or "",
    }


def build_tryon_guidance(intent: Dict[str, Any]) -> str:
    """Build extra sleeve/hem instructions from deterministic intent."""
    guidance = []
    action = intent.get("action")
    subtype = intent.get("subtype")
    sleeve_length = intent.get("sleeve_length")
    hem_length = intent.get("hem_length")

    if action in {"bottom", "outfit", "dress"}:
        if subtype == "shorts":
            guidance.append(
                "The lower garment is shorts. Shorts must end above the knee. "
                "Remove all previous pants or leggings below the shorts hem; legs below the hem must be natural bare skin."
            )
        elif subtype == "skirt":
            guidance.append(
                "The lower garment is a skirt. Remove all previous pants or leggings below the skirt hem; visible legs must be natural bare skin."
            )
        elif hem_length == "full-length":
            guidance.append(
                "The lower garment is full-length. It must reach the ankles naturally; do not turn jeans or pants into shorts."
            )
        elif subtype in ["dress", "jumpsuit", "romper"]:
            guidance.append(
                "The garment is one-piece/full-body. Replace the avatar's base top and bottom completely with this one-piece garment."
            )

    if action in {"top", "outfit", "dress"}:
        if sleeve_length == "sleeveless":
            guidance.append(
                "The garment is sleeveless. Keep shoulders and arms exposed; do not add sleeves."
            )
        elif sleeve_length == "short":
            guidance.append(
                "The garment has short/half sleeves. Sleeves must end above the elbow; forearms must remain bare skin."
            )
        elif sleeve_length == "long":
            guidance.append(
                "The garment has long/full sleeves. Sleeves must extend naturally to the wrists; do not shorten them."
            )

    return " ".join(guidance)


def select_tryon_person_path(avatar_path, latest_tryon_path, garment_category, path_exists=os.path.exists):
    """
    Pick Image 1 for try-on:
    - First top/bottom uses avatar_path.
    - Later top/bottom uses latest_tryon_path.
    - Outfit/dress always resets to avatar_path.
    """
    selected = (garment_category or "").strip().lower()
    action = normalize_tryon_action(garment_category)
    is_explicit_top_or_bottom = selected in TOP_ALIASES or selected in BOTTOM_ALIASES
    use_latest = (
        is_explicit_top_or_bottom
        and action in {"top", "bottom"}
        and latest_tryon_path
        and path_exists(latest_tryon_path)
    )

    if use_latest:
        return latest_tryon_path, "latest_tryon", True
    if avatar_path and path_exists(avatar_path):
        return avatar_path, "avatar", False
    return None, "missing", False


def compress_image_for_upload(image_path: str, max_width: int = 1500) -> str:
    """
    Compress and resize image before uploading to API for faster processing.
    
    Args:
        image_path: Path to the original image
        max_width: Maximum width in pixels (height will scale proportionally)
        
    Returns:
        Path to compressed image (may be same path if no compression needed)
    """
    
    if str(image_path).startswith('http://') or str(image_path).startswith('https://'):
        return str(image_path)
        
    try:
        img = Image.open(image_path)
        width, height = img.size
        
        # Only compress if image is larger than max_width
        if width > max_width:
            # Calculate new dimensions maintaining aspect ratio
            ratio = max_width / width
            new_height = int(height * ratio)
            
            # Resize with high-quality resampling
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
            
            # Save compressed version
            compressed_path = image_path.replace('.', '_compressed.')
            img.save(compressed_path, "JPEG", quality=100, optimize=True)
            print(f"   📦 Compressed: {width}x{height} → {max_width}x{new_height}")
            return compressed_path
        
        return image_path
    except Exception as e:
        print(f"   ⚠ Compression failed: {e}")
        return image_path


def detect_garment_category(garment_path: str) -> Literal["Upper-body", "Lower-body", "Dress"]:
    """
    Analyze a garment image to detect its category (top, bottom, or dress).
    
    Uses advanced image analysis focusing on:
    - Where the main COLORED GARMENT is located (not skin)
    - Color distribution across image sections
    - Detecting dark/colored clothing vs skin tones
    
    Args:
        garment_path: Path to the garment image
        
    Returns:
        Category string: "Upper-body", "Lower-body", or "Dress"
    """
    print("\n🔍 Analyzing garment image to detect category...")
    
    try:
        # Load the image
        if str(garment_path).startswith('http://') or str(garment_path).startswith('https://'):
            import requests
            from io import BytesIO
            resp = requests.get(garment_path, stream=True, timeout=15)
            img = Image.open(BytesIO(resp.content))
        else:
            img = Image.open(garment_path)
            
        width, height = img.size
        
        # Convert to RGB array for analysis
        img_rgb = img.convert('RGB')
        img_array = np.array(img_rgb)
        
        # Split image into sections (focusing on middle-lower for shorts detection)
        h = img_array.shape[0]
        
        # More granular splits: top (0-25%), upper-mid (25-50%), lower-mid (50-75%), bottom (75-100%)
        top_quarter = img_array[:h//4, :, :]
        upper_mid = img_array[h//4:h//2, :, :]
        lower_mid = img_array[h//2:3*h//4, :, :]
        bottom_quarter = img_array[3*h//4:, :, :]
        
        def has_dark_clothing(section):
            """Check if section has significant dark/colored clothing (not skin)."""
            # Convert to grayscale for analysis
            gray = np.mean(section, axis=2)
            # Count dark pixels (clothing) vs light pixels (background/skin)
            dark_pixels = np.sum(gray < 100)  # Dark clothing
            colored_pixels = np.sum(np.std(section, axis=2) > 30)  # Colored/patterned areas
            total_pixels = section.shape[0] * section.shape[1]
            return (dark_pixels + colored_pixels) / total_pixels
        
        def get_dominant_colors(section):
            """Get the variety of colors in a section."""
            # Check color variance (more variance = more patterns/clothing)
            color_std = np.std(section, axis=(0, 1))
            return np.mean(color_std)
        
        # Analyze each section for clothing presence
        top_clothing = has_dark_clothing(top_quarter)
        upper_mid_clothing = has_dark_clothing(upper_mid)
        lower_mid_clothing = has_dark_clothing(lower_mid)
        bottom_clothing = has_dark_clothing(bottom_quarter)
        
        # Also check color variety
        top_colors = get_dominant_colors(top_quarter)
        upper_mid_colors = get_dominant_colors(upper_mid)
        lower_mid_colors = get_dominant_colors(lower_mid)
        bottom_colors = get_dominant_colors(bottom_quarter)
        
        print(f"   Image size: {width}x{height}")
        print(f"   Clothing presence - Top: {top_clothing:.2%}, Upper-mid: {upper_mid_clothing:.2%}")
        print(f"   Clothing presence - Lower-mid: {lower_mid_clothing:.2%}, Bottom: {bottom_clothing:.2%}")
        
        # KEY DETECTION LOGIC:
        # Shorts/Pants: Main clothing is in lower-mid section (waist to thighs)
        # Shirts/Tops: Main clothing is in upper sections
        
        lower_body_score = lower_mid_clothing + bottom_clothing * 0.5
        upper_body_score = top_clothing + upper_mid_clothing * 0.8
        
        # If lower-mid has significant dark clothing and it's more than top -> Bottom wear
        if lower_mid_clothing > 0.15 and lower_mid_clothing > top_clothing:
            category = "Lower-body"
            print(f"   ✓ Detected: LOWER-BODY (clothing in lower-mid section: {lower_mid_clothing:.2%})")
        elif lower_mid_clothing > 0.20:  # Strong presence in lower mid
            category = "Lower-body"
            print(f"   ✓ Detected: LOWER-BODY (strong lower-mid presence)")
        elif upper_mid_clothing > lower_mid_clothing and top_clothing > 0.1:
            category = "Upper-body"
            print(f"   ✓ Detected: UPPER-BODY (clothing in upper sections)")
        elif lower_mid_colors > upper_mid_colors and lower_mid_colors > 40:
            # More color variation in lower section = likely shorts/pants with pattern
            category = "Lower-body"
            print(f"   ✓ Detected: LOWER-BODY (color pattern in lower section)")
        else:
            # Default based on overall comparison
            if lower_body_score > upper_body_score:
                category = "Lower-body"
                print(f"   ✓ Detected: LOWER-BODY (score comparison)")
            else:
                category = "Upper-body"
                print(f"   ✓ Detected: UPPER-BODY (default)")
        
        return category
        
    except Exception as e:
        print(f"   ⚠ Garment analysis failed: {e}")
        print(f"   → Defaulting to Upper-body")
        return "Upper-body"


class Person3DEffects:
    """Add 3D effects specifically to the person in the image."""

    def __init__(self, image_path):
        """Load the image."""
        self.image = Image.open(image_path).convert("RGB")
        self.width, self.height = self.image.size
        self.image_array = np.array(self.image)

    def detect_person_mask(self):
        """Detect and create a mask for the person in the image."""
        print("  → Detecting person in image...")

        try:
            import mediapipe as mp

            mp_selfie_segmentation = mp.solutions.selfie_segmentation
            selfie_segmentation = mp_selfie_segmentation.SelfieSegmentation(model_selection=1)

            results = selfie_segmentation.process(cv2.cvtColor(self.image_array, cv2.COLOR_RGB2BGR))
            mask = results.segmentation_mask
            mask_binary = (mask > 0.5).astype(np.uint8) * 255
            mask_image = Image.fromarray(mask_binary, mode='L')
            mask_image = mask_image.filter(ImageFilter.GaussianBlur(radius=3))

            print("  ✓ Person detected successfully")
            return mask_image

        except (ImportError, Exception) as e:
            print(f"  → Using alternative detection method...")
            return self._simple_person_detection()

    def _simple_person_detection(self):
        """Simple person detection using edge detection and center focus."""
        gray = cv2.cvtColor(self.image_array, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        mask = np.zeros((self.height, self.width), dtype=np.uint8)
        center_x, center_y = self.width // 2, self.height // 2
        axes_x, axes_y = int(self.width * 0.4), int(self.height * 0.6)
        cv2.ellipse(mask, (center_x, center_y), (axes_x, axes_y), 0, 0, 360, 255, -1)

        if len(contours) > 0:
            largest_contour = max(contours, key=cv2.contourArea)
            cv2.fillPoly(mask, [largest_contour], 255)

        mask = cv2.GaussianBlur(mask, (15, 15), 0)
        return Image.fromarray(mask, mode='L')

    def apply_3d_to_person(self, mask, depth_strength=15):
        """Apply 3D depth effect to the person using the mask."""
        print("  → Applying 3D depth effect to person...")

        mask_array = np.array(mask, dtype=np.float32) / 255.0
        result = self.image.copy()

        # Create shadow layer
        shadow = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
        shadow_offset = depth_strength
        shadow_mask = Image.new('L', (self.width, self.height), 0)
        shadow_mask.paste(mask, (shadow_offset, shadow_offset))

        shadow_array = np.array(shadow_mask, dtype=np.float32) / 255.0 * 0.6
        shadow_rgba = np.zeros((self.height, self.width, 4), dtype=np.uint8)
        shadow_rgba[:, :, 3] = (shadow_array * 255).astype(np.uint8)
        shadow = Image.fromarray(shadow_rgba, mode='RGBA')
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=shadow_offset // 2))

        result = Image.alpha_composite(result.convert('RGBA'), shadow)

        # Apply emboss effect to person area
        embossed = self.image.filter(ImageFilter.EMBOSS)
        mask_rgba = Image.new('RGBA', (self.width, self.height), (0, 0, 0, 0))
        mask_rgba.paste(embossed, (0, 0))
        alpha = mask.point(lambda p: int(p * 0.3))
        mask_rgba.putalpha(alpha)
        result = Image.alpha_composite(result, mask_rgba)

        # Enhance contrast on person
        mask_array_3d = np.stack([mask_array] * 3, axis=2)
        enhanced = np.array(result.convert('RGB'))
        enhanced = enhanced.astype(np.float32)
        person_area = enhanced * mask_array_3d
        background_area = enhanced * (1 - mask_array_3d)
        person_area = person_area * 1.1
        person_area = np.clip(person_area, 0, 255)
        enhanced = (person_area + background_area).astype(np.uint8)
        result = Image.fromarray(enhanced, mode='RGB')

        return result

    def add_3d_popout_effect(self, mask, popout_strength=10):
        """Create a 3D pop-out effect for the person."""
        print("  → Creating 3D pop-out effect...")

        layers = []
        num_layers = 3
        mask_array = np.array(mask, dtype=np.float32) / 255.0

        for i in range(num_layers):
            offset_x = int(i * popout_strength / num_layers)
            offset_y = int(i * popout_strength / num_layers)

            offset_mask = Image.new('L', (self.width + popout_strength, self.height + popout_strength), 0)
            offset_mask.paste(mask, (offset_x, offset_y))

            layer = Image.new('RGBA', (self.width + popout_strength, self.height + popout_strength), (0, 0, 0, 0))
            layer.paste(self.image, (offset_x, offset_y))

            alpha = int(255 * (1.0 - i * 0.2))
            alpha_mask = offset_mask.point(lambda p: int(p * alpha / 255))
            layer.putalpha(alpha_mask)
            layers.append(layer)

        result = Image.new('RGB', (self.width + popout_strength, self.height + popout_strength), (255, 255, 255))
        for layer in reversed(layers):
            result = Image.alpha_composite(result.convert('RGBA'), layer).convert('RGB')

        return result

    def add_depth_shadow_to_person(self, mask, blur_radius=20, offset=(15, 15)):
        """Add a realistic shadow behind the person."""
        print("  → Adding depth shadow...")

        shadow_mask = mask.copy()
        shadow_canvas = Image.new('L', (self.width + offset[0] * 2, self.height + offset[1] * 2), 0)
        shadow_canvas.paste(shadow_mask, (offset[0], offset[1]))
        shadow_canvas = shadow_canvas.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        shadow = Image.new('RGBA', (self.width + offset[0] * 2, self.height + offset[1] * 2), (0, 0, 0, 0))
        shadow_array = np.array(shadow_canvas, dtype=np.float32) / 255.0 * 0.7
        shadow_rgba = np.zeros((shadow.height, shadow.width, 4), dtype=np.uint8)
        shadow_rgba[:, :, 3] = (shadow_array * 255).astype(np.uint8)
        shadow = Image.fromarray(shadow_rgba, mode='RGBA')

        result = Image.new('RGB', (self.width + offset[0] * 2, self.height + offset[1] * 2), (255, 255, 255))
        result = Image.alpha_composite(result.convert('RGBA'), shadow).convert('RGB')
        result.paste(self.image, (offset[0], offset[1]))

        return result

    def process_full_3d(self):
        """Apply full 3D effect pipeline to the person."""
        print("\n" + "="*60)
        print("Applying 3D effects to person...")
        print("="*60)

        mask = self.detect_person_mask()
        result = self.apply_3d_to_person(mask, depth_strength=20)
        result = self.add_3d_popout_effect(mask, popout_strength=12)
        mask_resized = mask.resize(result.size, Image.Resampling.LANCZOS)
        result = self.add_depth_shadow_to_person(mask_resized, blur_radius=25, offset=(20, 20))

        print("\n✓ 3D effects applied successfully!")
        return result


class NanoBananaTryOn:
    """
    Virtual Try-On service using Nano Banana Pro API.
    
    Uses Gemini 3 Pro Image's IMAGETOIAMGE mode to combine
    person image with garment image for realistic virtual try-on.
    """
    
    def __init__(self):
        """Initialize the Virtual Try-On service."""
        self.client = None
        self._initialized = False
    
    def _ensure_client(self):
        """Lazy initialization of the client."""
        if not self._initialized:
            self.client = NanoBananaClient()
            self._initialized = True
            
    def _prepare_and_upload(self, image: Union[str, Path, Image.Image], prefix: str, max_width: int):
        path = self._prepare_image(image, prefix)
        compressed_path = compress_image_for_upload(path, max_width=max_width)
        url = get_public_url_for_image(compressed_path)
        return path, compressed_path, url
    
    
    def try_on(
        self,
        person_image: Union[str, Path, Image.Image],
        cloth_image: Union[str, Path, Image.Image],
        category: Literal["Upper-body", "Lower-body", "Dress", "Outfit"] = "Upper-body",
        timeout: int = 120,
        extra_guidance: str = "",
        garment_intent: Optional[Dict[str, Any]] = None,
    ) -> Image.Image:
        """
        Perform virtual try-on using Nano Banana Pro.
        
        Args:
            person_image: Person/avatar image (path or PIL Image)
            cloth_image: Garment/clothing image (path or PIL Image)
            category: Clothing category for context
            timeout: Max wait time for result
            
        Returns:
            PIL Image with try-on result
        """
        self._ensure_client()
        
        print("\n" + "="*60)
        print("🎨 Nano Banana Pro Virtual Try-On")
        print("="*60)
        
        # OPTIMIZATION: Prepare and upload images in parallel
        import concurrent.futures
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_person = executor.submit(self._prepare_and_upload, person_image, "person", 1500)
            future_cloth = executor.submit(self._prepare_and_upload, cloth_image, "cloth", 1500)
            
            try:
                person_original_path, person_path, person_url = future_person.result()
                cloth_original_path, cloth_path, cloth_url = future_cloth.result()
            except Exception as e:
                raise Exception(
                    f"Cannot perform virtual try-on: Images must be publicly accessible. "
                    f"Ensure PUBLIC_BASE_URL is set. Error: {e}"
                )
        
        garment_intent = garment_intent or {}

        # Identity and product-reference rules are placed first so the model
        # treats Image 1 as the only person and Image 2 as clothing only.
        _identity = (
            "CRITICAL IDENTITY RULES (HIGHEST PRIORITY): "
            "Image 1 is the ONLY person source. The output MUST show the exact same person from Image 1: "
            "same face, head, hair, skin tone, body shape, body weight, pose, camera angle, and background. "
            "Do NOT alter the person's identity, body type, proportions, pose, or background. "
            "Image 2 is ONLY a clothing reference. Extract only the selected garment's fabric, color, pattern, cut, fit, and logo details. "
            "COMPLETELY IGNORE every human/model/body part in Image 2: face, hair, skin, arms, hands, legs, feet, tattoos, pose, muscles, physique, and proportions. "
            "The output person must be ONLY the person from Image 1, NEVER the model from Image 2. "
            "Output must be ONE single photorealistic photo. NO collages. NO side-by-side. NO floating clothes. "
            "The clothing must look naturally worn on Image 1's body with proper draping, wrinkles, and shadows. "
        )

        # Extra length/style guidance is inserted between identity and clothing instructions
        _extra = ""
        if extra_guidance:
            _extra = f"GARMENT SHAPE RULES: {extra_guidance} "
        
        if category == "Upper-body":
            prompt = (
                f"{_identity}"
                f"{_extra}"
                "MODE: TOP ONLY. Make the person in Image 1 wear ONLY the upper-body garment from Image 2. "
                "Replace the existing upper-body garment from Image 1 completely; no old shirt, sleeve, collar, or layer may remain visible. "
                "Change only torso/shoulder/arm clothing. Preserve the lower body from Image 1 exactly as it appears, including pants/shorts/skirt, legs, shoes, shadows, and background. "
                "Do not change the lower garment length, color, or style. "
            )
        elif category == "Lower-body":
            prompt = (
                f"{_identity}"
                f"{_extra}"
                "MODE: BOTTOM ONLY. Make the person in Image 1 wear ONLY the lower-body garment from Image 2. "
                "Replace the existing lower-body garment from Image 1 completely; no old pants, shorts, leggings, waistband, or layer may remain visible. "
                "Change only waist/hips/legs clothing. Preserve the upper body from Image 1 exactly as it appears, including shirt/top/jacket, sleeves, arms, hands, face, shoes, shadows, and background. "
                "If the new garment is shorts or a skirt, everything below the new hem must be natural bare skin from Image 1, not old pants underneath. "
            )
        elif category == "Outfit":
            prompt = (
                f"{_identity}"
                f"{_extra}"
                "MODE: FULL OUTFIT. Make the person in Image 1 wear the complete outfit shown in Image 2. "
                "Replace all existing visible clothing from Image 1 that conflicts with the outfit: upper garment and lower garment must both be replaced. "
                "No remnants of the base tank top, base shorts, old shirt, old pants, old sleeves, or old waistband may remain visible. "
                "Keep the exact person, face, body, pose, background, and shoes from Image 1 unless Image 2 clearly includes matching footwear as part of the outfit. "
            )
        else:  # Dress
            prompt = (
                f"{_identity}"
                f"{_extra}"
                "MODE: ONE-PIECE / DRESS. Make the person in Image 1 wear the one-piece full-body garment from Image 2. "
                "Replace both upper and lower base clothing completely with the dress/jumpsuit/romper. "
                "No old shirt, old shorts, old pants, waistband, or layered clothing may remain visible. "
                "Keep the exact person, face, body, pose, shoes, and background from Image 1 unchanged. "
            )
        
        print(f"   Category: {category}")
        print(f"   Garment intent: {garment_intent}")
        print(f"   Prompt: {prompt[:120]}...")
        
        # Create temp output path
        temp_output = tempfile.mktemp(suffix=".jpg")
        
        result_path = self.client.edit_and_download(
            prompt=prompt,
            image_urls=[person_url, cloth_url],
            save_path=temp_output,
            image_size="9:16",
            timeout=300
        )
        
        # Load and return result
        result_image = Image.open(result_path).convert("RGB")
        
        # Cleanup temp file
        try:
            if isinstance(person_image, Image.Image) and os.path.exists(person_original_path):
                os.remove(person_original_path)
            if person_original_path != person_path and os.path.exists(person_path):
                os.remove(person_path)
                
            if isinstance(cloth_image, Image.Image) and os.path.exists(cloth_original_path):
                os.remove(cloth_original_path)
            if cloth_original_path != cloth_path and os.path.exists(cloth_path):
                os.remove(cloth_path)
        except:
            pass
        
        print("✓ Virtual try-on complete!")
        return result_image
    
    def _prepare_image(self, image: Union[str, Path, Image.Image], prefix: str) -> str:
        """Convert image to file path."""
        if isinstance(image, Image.Image):
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, f"nanobanana_{prefix}_{id(image)}.png")
            image.save(temp_path, "PNG", optimize=True)  # Added optimize for smaller files
            return temp_path
        return str(image)


# Aliases for backward compatibility
CatVTONTryOn = NanoBananaTryOn
OOTDiffusionTryOn = NanoBananaTryOn


def virtual_tryon(person_img_path, dress_img_path, garment_des="A stylish dress", output_path=None, is_full_body=False, explicit_category=None):
    """
    Wrapper function for virtual try-on with Nano Banana Pro.
    
    Args:
        person_img_path: Path to the person's avatar/image
        dress_img_path: Path to the garment image
        garment_des: Description (used as fallback for category detection)
        output_path: Optional output path
        is_full_body: Flag for logging purposes
        explicit_category: Explicit category from frontend ('top', 'bottom', 'dress')
                          If provided, skips all detection and uses this directly
        
    Returns:
        Path to the saved result image
    """
    print("\n" + "="*60)
    print(f"Virtual Try-On - Nano Banana Pro")
    print("="*60)
    
    intent = build_garment_intent(explicit_category, garment_des)

    # PRIORITY 1: Use EXPLICIT category from frontend (if provided)
    if explicit_category:
        category = intent["model_category"]
        print(f"✅ Using EXPLICIT category from frontend: {explicit_category} → {category}")
    else:
        # FALLBACK: Image-based category detection
        print("⚠ No explicit category provided - using image detection...")
        category = detect_garment_category(dress_img_path)
        
        # Text-based validation
        des_lower = garment_des.lower()
        text_category = None
        
        if "dress" in des_lower or "gown" in des_lower:
            text_category = "Dress"
        elif any(word in des_lower for word in ["pants", "jeans", "skirt", "shorts", "trousers", "leggings", "bottom", "lower"]):
            text_category = "Lower-body"
        elif any(word in des_lower for word in ["top", "shirt", "t-shirt", "tshirt", "blouse", "sweater", "jacket", "coat", "upper"]):
            text_category = "Upper-body"
        
        if text_category and text_category != category:
            print(f"   ⚠ Text description suggests: {text_category}")
            print(f"   → Using text-based category: {text_category}")
            category = text_category  # Trust text description over image analysis
        intent["model_category"] = category
    
    print(f"\n📦 Final Category: {category}")
    print(f"📦 Garment Intent: {intent}")
    print(f"📸 Image Type: {'Full Body (Original)' if is_full_body else 'Selfie (Generated Avatar)'}")
    length_guidance = build_tryon_guidance(intent)

    try:
        # Perform virtual try-on
        service = NanoBananaTryOn()
        result_image = service.try_on(
            person_image=person_img_path,
            cloth_image=dress_img_path,
            category=category,
            timeout=300,
            extra_guidance=length_guidance,
            garment_intent=intent
        )
        
        # Save Result
        if output_path is None:
            output_path = Path(person_img_path).parent / f"tryon_result_{category}_{int(time.time())}.jpg"
        else:
            output_path = Path(output_path)
            
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result_image.save(str(output_path), "JPEG", quality=100)  # High quality for realistic output
        
        print(f"🎉 Success! Result saved to: {output_path}")
        return str(output_path)
        
    except Exception as e:
        print(f"❌ Virtual Try-On Failed: {e}")
        raise e


def apply_3d_effects(image_path):
    """
    Apply 3D effects to an image.
    """    
    try:
        effects = Person3DEffects(image_path)
        result = effects.process_full_3d()
        
        output_path = Path(image_path).parent / f"3d_{Path(image_path).name}"
        result.save(output_path, quality=95)
        
        return str(output_path)
    except Exception as e:
        print(f"Error applying 3D effects: {e}")
        return image_path
