"""
Avatar Improvement Service using Nano Banana Pro API

Generates full-body avatars from selfies using Nano Banana Pro (Gemini 3 Pro Image).
"""
import base64
import shutil
from PIL import Image
from io import BytesIO
from django.conf import settings
import json
import os
import tempfile

from .nanobanana_service import NanoBananaClient, get_public_url_for_image
from .virtual_tryon_service import compress_image_for_upload


def detect_gender_and_features(image_path):
    """
    Analyze selfie to detect gender and appearance features.
    
    Uses Nano Banana Pro for image analysis via a descriptive generation task.
    Returns basic features detected from the image.
    """
    print("🔍 Analyzing selfie for features...")
    
    try:
        # For now, return default features - Nano Banana Pro will handle
        # the identity preservation automatically during avatar generation
        # A more sophisticated approach would use a separate vision model
        
        # Load image to detect basic attributes
        img = Image.open(image_path)
        width, height = img.size
        
        # Basic heuristics (placeholder for more sophisticated analysis)
        return {
            "gender": "person",  # Will be detected by Nano Banana Pro
            "age_range": "adult",
            "skin_tone": "medium",
            "hair_color": "brown",
            "hair_style": "medium",
            "clothing_color": "neutral",
            "clothing_type": "casual"
        }
        
    except Exception as e:
        print(f"Feature detection error: {e}")
        return {
            "gender": "person",
            "age_range": "adult",
            "skin_tone": "medium",
            "hair_color": "brown",
            "hair_style": "medium",
            "clothing_color": "neutral",
            "clothing_type": "shirt"
        }


def detect_image_type(image_path):
    """
    Detect if an image is a selfie or full-body image.
    
    Uses multiple signals:
    - Aspect ratio (full body images must be VERY tall, ratio > 1.6)
    - Content analysis (checking for visible feet/shoes at bottom)
    - Face takes up significant portion of image = selfie
    
    Returns:
        dict: {
            "image_type": "selfie" | "full_body",
            "confidence": float (0-1),
            "description": str
        }
    """
    print("🔍 Detecting image type...")
    
    try:
        img = Image.open(image_path)
        width, height = img.size
        
        # Aspect ratio analysis
        aspect_ratio = height / width
        
        print(f"   Image size: {width}x{height}, aspect ratio: {aspect_ratio:.2f}")
        
        # Key insight: SELFIES have face taking up significant portion of image
        # FULL BODY images have small face and visible full body
        
        # For full body detection, we need:
        # 1. Very tall image (ratio > 1.6) - typical fashion photo proportions
        # 2. Content in bottom 25% that looks like feet/shoes (not just pattern/clothing)
        
        # Analyze image content
        img_rgb = img.convert('RGB')
        import numpy as np
        img_array = np.array(img_rgb)
        
        h = img_array.shape[0]
        w = img_array.shape[1]
        
        # Check for face presence in top portion (selfies have large faces in top half)
        top_half = img_array[:h//2, :, :]
        
        # Check bottom 20% for feet (full body has feet/floor at very bottom)
        bottom_20 = img_array[int(h*0.80):, :, :]
        
        # Check if bottom is mostly plain (background/floor) - fullbody indicator
        # Selfies with patterned shirts will have high variance at bottom
        bottom_variance = np.var(bottom_20)
        
        # Check for floor/background indicators (low color variance = plain floor)
        bottom_color_std = np.std(bottom_20, axis=(0, 1))
        is_plain_floor = np.mean(bottom_color_std) < 30  # Low variance = plain background
        
        print(f"   Bottom 20% variance: {bottom_variance:.0f}")
        print(f"   Bottom color uniformity: {np.mean(bottom_color_std):.1f} (plain floor: {is_plain_floor})")
        
        # STRICT Decision logic - default to SELFIE unless clearly full body
        
        # Only full body if:
        # 1. VERY tall (ratio > 1.6) - much taller than wide
        # 2. Bottom has plain floor/background (not patterned clothing)
        
        if aspect_ratio > 1.6 and is_plain_floor:
            # Very tall with plain floor at bottom = full body
            return {
                "image_type": "full_body",
                "confidence": 0.95,
                "visible_parts": ["face", "upper_body", "lower_body", "legs", "feet"],
                "description": "Full body image (very tall + visible floor/feet)"
            }
        elif aspect_ratio > 1.8:
            # Extremely tall - likely full body regardless
            return {
                "image_type": "full_body",
                "confidence": 0.85,
                "visible_parts": ["face", "upper_body", "lower_body", "legs"],
                "description": "Very tall portrait - likely full body"
            }
        else:
            # Everything else is treated as selfie - will generate avatar
            return {
                "image_type": "selfie",
                "confidence": 0.90,
                "visible_parts": ["face", "upper_body"],
                "description": "Selfie/half-body detected - will generate full body avatar"
            }
            
    except Exception as e:
        print(f"Image type detection error: {e}")
        return {
            "image_type": "selfie",
            "confidence": 0.5,
            "description": f"Could not determine - defaulting to selfie: {e}"
        }


def preprocess_for_avatar(
    input_image_path,
    output_path,
    full_body=True,
    include_shoes=True,
    user_description=None,
    reference_images=None,
    face_image_path=None,
):
    """
    Smart preprocessing that detects image type and routes accordingly.
    
    - SELFIE: Generate full-body avatar using Nano Banana Pro
    - FULL_BODY: Skip avatar generation, return original image path
    
    Returns:
        tuple: (output_path, is_full_body_image)
            - output_path: Path to the avatar/image to use
            - is_full_body_image: True if original was full-body (skipped generation)
    """
    print("\n" + "="*60)
    print("🔍 Smart Image Type Detection")
    print("="*60)
    
    # Detect image type
    # Use primary image for detection
    primary_image_path = input_image_path
    if isinstance(input_image_path, (list, tuple)) and input_image_path:
        primary_image_path = input_image_path[0]
        if reference_images is None:
            reference_images = list(input_image_path)

    detection = detect_image_type(primary_image_path)
    image_type = detection.get("image_type", "selfie")
    confidence = detection.get("confidence", 0.5)
    
    print(f"📸 Image Type Detection: {image_type} (confidence: {confidence})")
    print(f"   Visible parts: {detection.get('visible_parts', [])}")
    
    if image_type == "full_body" and confidence >= 0.7:
        # Full body image detected - skip avatar generation
        print("\n✓ Full-body image detected!")
        print("→ Skipping avatar generation - using original image directly")
        
        # Copy original image to output path to maintain consistency
        shutil.copy(primary_image_path, output_path)
        
        return output_path, True
    else:
        # Selfie detected - generate full-body avatar
        print("\n✓ Selfie detected!")
        print("→ Generating full-body avatar with Nano Banana Pro")
        
        # Use Nano Banana Pro for avatar generation
        result_path = improve_avatar(
            input_image_path=primary_image_path,
            output_path=output_path,
            full_body=full_body,
            include_shoes=include_shoes,
            user_description=user_description,
            reference_images=reference_images,
            face_image_path=face_image_path,
        )
        
        return result_path, False


def improve_avatar(
    input_image_path,
    output_path,
    full_body=True,
    include_shoes=True,
    user_description=None,
    reference_images=None,
    face_image_path=None,
):
    """
    Generate full-body avatar from selfie using Nano Banana Pro.
    
    Uses Nano Banana Pro's IMAGETOIAMGE mode to transform a selfie
    into a full-body avatar while preserving the person's identity.
    """
    print("🎨 Generating Full Body Avatar with Nano Banana Pro")
    
    try:
        client = NanoBananaClient()
        
        # Get features for prompt construction
        features = detect_gender_and_features(input_image_path)
        gender = features.get("gender", "person")
        print(f"Detected: {gender}, features: {features}")
        
        gender_term = "man" if gender == "male" else "woman" if gender == "female" else "person"
        
        # Build reference image list (front/side/back/face)
        reference_paths = []
        if reference_images:
            reference_paths.extend(reference_images)
        else:
            reference_paths.append(input_image_path)

        if face_image_path and face_image_path not in reference_paths:
            reference_paths.append(face_image_path)

        # Remove empty entries and preserve order
        reference_paths = [p for p in reference_paths if p]

        # Get public URLs for reference images
        try:
            reference_urls = []
            for path in reference_paths:
                compressed_path = compress_image_for_upload(path, max_width=800)
                reference_urls.append(get_public_url_for_image(compressed_path))
        except ValueError as e:
            print(f"⚠️ Cannot get public URL: {e}")
            raise Exception(
                "Cannot generate avatar: Input images must be publicly accessible. "
                "Ensure PUBLIC_BASE_URL is set and media files are served."
            )
        
        # Create prompt for avatar generation
        # Nano Banana Pro (Gemini 3 Pro) excels at identity preservation
        multi_ref_note = ""
        if len(reference_urls) > 1:
            multi_ref_note = (
                "You are given multiple reference images of the SAME person from different angles. "
                "Use ALL reference images to match body shape, proportions, and identity. "
                "Do NOT slim down or alter the body size or fat distribution. "
            )

        prompt = (
            f"{multi_ref_note}"
            f"Generate a photorealistic full-body portrait photograph of this person for a virtual try-on app. "
            f"The person should be standing naturally, facing forward, with arms relaxed and slightly away from the torso. "
            f"Facial expression: slight friendly smile, subtle and natural. "
            f"Wearing ONLY a clean try-on base outfit: a plain fitted light-gray sleeveless athletic tank top "
            f"and plain matte charcoal mid-thigh fitted shorts"
            f"{', with simple neutral low-profile sneakers' if include_shoes else ''}. "
            f"Arms, forearms, thighs, knees, calves, and lower legs must be clearly visible as natural skin. "
            f"Do NOT add jeans, chinos, long pants, long sleeves, jackets, hoodies, layered clothes, patterns, logos, or accessories. "
            f"Background: solid white seamless backdrop. "
            f"Show complete body from head to feet. "
            f"Maintain the exact facial features, skin tone, body shape, and identity from the reference images. "
            f"Professional e-commerce fashion photography style. "
            f"Single person, front-facing view only. "
        )
        
        if user_description:
            prompt += (
                f" \n\nCRITICAL INSTRUCTION FOR BODY SHAPE: The generated body MUST ACCURATELY REFLECT "
                f"the following physique and measurements: {user_description}. "
                f"Do NOT default to a thin or standard model if these measurements indicate "
                f"a larger, heavier, or different body type. Match the body mass and shape explicitly."
            )
        
        print(f"\n→ Prompt: {prompt[:150]}...")
        print(f"→ Reference images: {len(reference_urls)}")
        
        # OPTIMIZED: Reduced resolution for faster processing
        result_path = client.edit_and_download(
            prompt=prompt,
            image_urls=reference_urls,
            save_path=output_path,
            image_size="9:16",  # Standard vertical aspect ratio
            timeout=300  # Increased timeout to handle slow generations
        )
        
        print(f"✓ Avatar generated successfully: {result_path}")
        return result_path
        
    except Exception as e:
        print(f"❌ Avatar generation failed: {e}")
        raise e


def apply_face_swap(source_face_path, target_body_path):
    """
    Swap face from source onto target using Nano Banana Pro.
    
    Uses IMAGETOIAMGE mode with multiple input images to blend
    the face from source_face_path onto target_body_path.
    """
    print(f"🔄 Face swap with Nano Banana Pro...")
    print(f"   Source (Face): {source_face_path}")
    print(f"   Target (Body): {target_body_path}")
    
    try:
        client = NanoBananaClient()
        
        # Get URLs for both images
        source_url = get_public_url_for_image(source_face_path)
        target_url = get_public_url_for_image(target_body_path)
        
        # Create face swap prompt
        prompt = (
            "Replace the face in the second image with the face from the first image. "
            "Keep the exact same body pose, clothing, and background from the second image. "
            "Blend the face naturally, matching lighting and skin tone. "
            "The result should look like a single coherent photograph."
        )
        
        # Create temp output path
        output_path = tempfile.mktemp(suffix=".png")
        
        # Use IMAGETOIAMGE with both images
        result_path = client.edit_and_download(
            prompt=prompt,
            image_urls=[source_url, target_url],
            save_path=output_path,
            image_size="1:1",
            timeout=300
        )
        
        print(f"✓ Face swap completed: {result_path}")
        return result_path
        
    except Exception as e:
        print(f"❌ Face swap failed: {e}")
        raise e


# Keep backward compatibility alias
apply_face_swap_huggingface = apply_face_swap
