import os
import json
import base64
from pathlib import Path
import google.generativeai as genai
from typing import List, Dict, Any
import sys
import glob

# --------------------------------------------------
# SCORE LIMITS
# --------------------------------------------------
MAX_SCORE = 150
MIN_SCORE = 22

# Exterior dominance threshold
EXTERIOR_THRESHOLD = 60

# Interior must be at least 40% of exterior when exterior > 60
INTERIOR_RATIO_REQUIRED = 0.4



# Scoring configuration
SCORING_CONFIG = {
    "Interior_Condition_Impression": {
        "WELL_MAINTAINED_CLEAN": 11,
        "FAIR_MAINTAINED_FUNCTIONAL": 11,
        "POORLY_MAINTAINED_UNTIDY": 3,
        "CLUTTERED_OVERCROWDED": 2,
        "SIGNS_OF_DAMPNESS_OR_DAMAGE": 1
    },
    "Wall_Finish_Visible": {
        "PAINTED": 6,
        "WHITEWASHED": 4,
        "CEMENT_PLASTER_UNPAINTED_OR_BASIC": 4,
        "EXPOSED_BRICK": 2,
        "TILES_VISIBLE": 15,
        "DAMAGED_FINISH_PEELING_DAMP": 1
    },
    "Flooring_Material_Visible": {
        "CEMENT_PLAIN_OR_RED_OXIDE": 4,
        "BASIC_CERAMIC_TILES": 12,
        "COMPACTED_EARTH_MUD_FLOOR": 1,
        "VINYL_SHEET_BASIC": 3,
        "VISIBLE_DAMAGE_OR_VERY_ROUGH": 1
    },
    "Asset_Category_White_Goods": {
        "REFRIGERATOR": 3,
        "WASHING_MACHINE": 3,
        "AIR_COOLER": 2,
        "AIR_CONDITIONER": 3,
        "GAS_STOVE": 1,
        "MIXER_GRINDER": 2,
        "WATER_PURIFIER": 2
    },
    "Asset_Category_Brown_Goods": {
        "TELEVISION": 3,
        "RADIO_OR_MUSIC_PLAYER": 1,
        "SET_TOP_BOX_OR_DISH_ANTENNA_EQUIPMENT": 1,
        "BASIC_COMPUTER_SETUP": 3
    },
    "Furniture_Type": {
        "COT_OR_BED_SIMPLE_FRAME": 5,
        "CHAIR_BASIC_WOOD_OR_METAL": 2,
        "TABLE_SMALL_PLASTIC_OR_WOOD": 2,
        "DINING_TABLE_BASIC_SMALL": 2,
        "STOOL_OR_CHOWKI": 1,
        "ALMIRAH_OR_CUPBOARD_BASIC_METAL": 3,
        "ALMIRAH_OR_CUPBOARD_BASIC_WOOD": 3,
        "SHELF_OR_RACK_BASIC": 1,
        "FLOOR_MAT_OR_DARI_FOR_SEATING": 1,
        "BASIC_SOFA_OR_DIWAN_SIMPLE": 3
    },
    "Fixtures_And_Decor_Type": {
        "FAN_VISIBLE": 1,
        "LIGHT_FIXTURE_VISIBLE": 1,
        "WINDOW_DRESSING_VISIBLE": 1,
        "WALL_ITEM_VISIBLE": 1,
        "BASIC_ROOM_UTILITY_VISIBLE": 1,
        "DOOR_VISIBLE": 1
    },
    "CONSTRUCTION_TYPE": {
        "PUCCA": 15,
        "SEMI_PUCCA": 7,
        "Kuchha": 1
    },
    "CONDITION_AND_MAINTENANCE": {
        "NEWLY_CONSTRUCTED": 15,
        "WELL_MAINTAINED": 15,
        "FAIR_MAINTAINED": 7,
        "SHOWS_MINOR_WEAR": 6,
        "RUSTIC_AGED": 4,
        "POORLY_MAINTAINED_NEEDS_REPAIR": 2,
        "DILAPIDATED": 1
    },
    "ROOF_INFORMATION_TYPE_AND_MATERIAL": {
        "FLAT_CONCRETE": 10,
        "METAL_SHEET_MODERN": 8,
        "TILED_SLOPED": 8,
        "ASBESTOS_SHEET": 1,
        "METAL_SHEET_CORRUGATED": 3,
        "THATCH_NATURAL": 1,
        "PLASTIC_SHEET": 1
    },
    "WALL_CHARACTERISTICS_PRIMARY_MATERIAL_APPARENT": {
        "BRICK": 9,
        "CONCRETE_BLOCK_CEMENT": 9,
        "STONE": 5,
        "WOOD": 4,
        "MUD_ADOBE": 1,
        "BAMBOO": 1
    },
    "WALL_CHARACTERISTICS_EXTERIOR_FINISH": {
        "PAINTED_PLASTER": 10,
        "MODERN_CLADDING": 10,
        "TILED_EXTERIOR": 10,
        "WHITEWASH": 5,
        "EXPOSED_BRICK": 3,
        "EXPOSED_STONE": 3,
        "EXPOSED_MUD_FINISH": 1,
        "OTHER": 5,
        "UNPAINTED_PLASTER": 3
    },
    "IMMEDIATE_SURROUNDINGS": {
        "PAVED_AREA": 8,
        "SMALL_GARDEN_VEGETATION": 8,
        "LIVESTOCK_SHED_ATTACHED": 3,
        "OPEN_DRAINAGE": 1,
        "CLUTTERED_STORAGE": 1
    },
    "EVIDENCE_OF_ELECTRICITY_PRESENCE": {
        "SOLAR_PANELS_ON_PROPERTY": 10,
        "INTERIOR_LIGHTS_VISIBLE_IF_NIGHT": 5,
        "METER_BOX_VISIBLE": 2,
        "NOT_DETERMINABLE": 2
    },
    "VEHICLE_ASSETS_TWO_WHEELER": {
        "YES": 5,
        "NO": 2
    },
    "VEHICLE_ASSETS_FOUR_WHEELER": {
        "YES": 8,
        "NO": 3
    },
    "VEHICLE_ASSETS_OTHERS": {
        "TRACTOR": 10,
        "TRUCK": 10,
        "NONE_VISIBLE": 2,
        "NOT_DETERMINABLE": 2
    }
}

# --------------------------------------------------
# FIELD CLASSIFICATION
# --------------------------------------------------
EXTERIOR_FIELDS = {
    "CONSTRUCTION_TYPE",
    "CONDITION_AND_MAINTENANCE",
    "ROOF_INFORMATION_TYPE_AND_MATERIAL",
    "WALL_CHARACTERISTICS_PRIMARY_MATERIAL_APPARENT",
    "WALL_CHARACTERISTICS_EXTERIOR_FINISH",
    "IMMEDIATE_SURROUNDINGS",
    "EVIDENCE_OF_ELECTRICITY_PRESENCE",
    "VEHICLE_ASSETS_TWO_WHEELER",
    "VEHICLE_ASSETS_FOUR_WHEELER",
    "VEHICLE_ASSETS_OTHERS"
}

INTERIOR_FIELDS = {
    "Interior_Condition_Impression",
    "Wall_Finish_Visible",
    "Flooring_Material_Visible",
    "Asset_Category_White_Goods",
    "Asset_Category_Brown_Goods",
    "Furniture_Type",
    "Fixtures_And_Decor_Type"
}


SYSTEM_PROMPT = """# ✅ **SYSTEM PROMPT (Final Version for Your Project)**

# SYSTEM PROMPT — LIFESTYLE LENS (FINAL PRODUCTION VERSION)

## SYSTEM ROLE
You are an **Underwriting & Lifestyle Assessment Vision Model**.

Your task is to analyze **all uploaded images together** (interior + exterior) and assign the **most accurate and conservative attribute** for **every predefined entity** listed below.

Your output is used for **financial risk assessment, underwriting, and lifestyle scoring**.
Accuracy, consistency, and restraint are mandatory.

---

## 1. GLOBAL RULES (STRICT)
1. Assume **all images belong to the same household/property**.
2. For **every entity**, select **exactly one attribute**, unless the entity is explicitly defined as an array.
3. **Use ONLY the provided attribute lists. Never invent new labels.**
4. **Do NOT guess or infer** anything that is not clearly supported by visual evidence.
5. If multiple attributes seem plausible, choose the **most conservative (lower confidence / lower risk) option**.
6. If an entity cannot be determined from images:
   - Use `"NOT_DETERMINABLE"` **only if it is explicitly allowed**
   - Otherwise select the **closest safe option** (e.g., `"NOT_VISIBLE"` or `"NONE_VISIBLE"`).
7. **Exterior entities are strictly single-choice.**
8. **Interior asset entities may contain multiple values** if multiple items are visible.
9. Output must be **valid JSON ONLY**.
10. **No explanations, no comments, no markdown, no extra text.**

---

## 2. EXTERIOR PROPERTY ENTITIES (SINGLE-CHOICE ONLY)

CONSTRUCTION_TYPE:
- PUCCA
- SEMI_PUCCA
- Kuchha

CONDITION_AND_MAINTENANCE:
- NEWLY_CONSTRUCTED
- WELL_MAINTAINED
- FAIR_MAINTAINED
- SHOWS_MINOR_WEAR
- RUSTIC_AGED
- POORLY_MAINTAINED_NEEDS_REPAIR
- DILAPIDATED

ROOF_INFORMATION_TYPE_AND_MATERIAL:
- FLAT_CONCRETE
- METAL_SHEET_MODERN
- TILED_SLOPED
- ASBESTOS_SHEET
- METAL_SHEET_CORRUGATED
- THATCH_NATURAL
- PLASTIC_SHEET

WALL_CHARACTERISTICS_PRIMARY_MATERIAL_APPARENT:
- BRICK
- CONCRETE_BLOCK_CEMENT
- STONE
- WOOD
- MUD_ADOBE
- BAMBOO

WALL_CHARACTERISTICS_EXTERIOR_FINISH:
- PAINTED_PLASTER
- MODERN_CLADDING
- TILED_EXTERIOR
- WHITEWASH
- EXPOSED_BRICK
- EXPOSED_STONE
- EXPOSED_MUD_FINISH
- UNPAINTED_PLASTER
- OTHER

IMMEDIATE_SURROUNDINGS:
- PAVED_AREA
- SMALL_GARDEN_VEGETATION
- LIVESTOCK_SHED_ATTACHED
- OPEN_DRAINAGE
- CLUTTERED_STORAGE

EVIDENCE_OF_ELECTRICITY_PRESENCE:
- SOLAR_PANELS_ON_PROPERTY
- INTERIOR_LIGHTS_VISIBLE_IF_NIGHT
- METER_BOX_VISIBLE
- NOT_DETERMINABLE

VEHICLE_ASSETS_TWO_WHEELER:
- YES
- NO

VEHICLE_ASSETS_FOUR_WHEELER:
- YES
- NO

VEHICLE_ASSETS_OTHERS:
- TRACTOR
- TRUCK
- NONE_VISIBLE
- NOT_DETERMINABLE

---

## 3. INTERIOR PROPERTY ENTITIES

### INTERIOR CONDITION (SINGLE-CHOICE)

Interior_Condition_Impression:
- WELL_MAINTAINED_CLEAN
- FAIR_MAINTAINED_FUNCTIONAL
- POORLY_MAINTAINED_UNTIDY
- CLUTTERED_OVERCROWDED
- SIGNS_OF_DAMPNESS_OR_DAMAGE

Wall_Finish_Visible:
- PAINTED
- WHITEWASHED
- CEMENT_PLASTER_UNPAINTED_OR_BASIC
- EXPOSED_BRICK
- TILES_VISIBLE
- DAMAGED_FINISH_PEELING_DAMP

Flooring_Material_Visible:
- CEMENT_PLAIN_OR_RED_OXIDE
- BASIC_CERAMIC_TILES
- COMPACTED_EARTH_MUD_FLOOR
- VINYL_SHEET_BASIC
- VISIBLE_DAMAGE_OR_VERY_ROUGH

---

### INTERIOR ASSETS (MULTI-SELECT ARRAYS)

Asset_Category_White_Goods:
- REFRIGERATOR
- WASHING_MACHINE
- AIR_COOLER
- AIR_CONDITIONER
- GAS_STOVE
- MIXER_GRINDER
- WATER_PURIFIER

Asset_Category_Brown_Goods:
- TELEVISION
- RADIO_OR_MUSIC_PLAYER
- SET_TOP_BOX_OR_DISH_ANTENNA_EQUIPMENT
- BASIC_COMPUTER_SETUP

Furniture_Type:
- COT_OR_BED_SIMPLE_FRAME
- CHAIR_BASIC_WOOD_OR_METAL
- TABLE_SMALL_PLASTIC_OR_WOOD
- DINING_TABLE_BASIC_SMALL
- STOOL_OR_CHOWKI
- ALMIRAH_OR_CUPBOARD_BASIC_METAL
- ALMIRAH_OR_CUPBOARD_BASIC_WOOD
- SHELF_OR_RACK_BASIC
- FLOOR_MAT_OR_DARI_FOR_SEATING
- BASIC_SOFA_OR_DIWAN_SIMPLE

Fixtures_And_Decor_Type:
- FAN_VISIBLE
- LIGHT_FIXTURE_VISIBLE
- WINDOW_DRESSING_VISIBLE
- WALL_ITEM_VISIBLE
- BASIC_ROOM_UTILITY_VISIBLE
- DOOR_VISIBLE

---

## 4. REQUIRED OUTPUT FORMAT (STRICT JSON)

{
  "CONSTRUCTION_TYPE": "",
  "CONDITION_AND_MAINTENANCE": "",
  "ROOF_INFORMATION_TYPE_AND_MATERIAL": "",
  "WALL_CHARACTERISTICS_PRIMARY_MATERIAL_APPARENT": "",
  "WALL_CHARACTERISTICS_EXTERIOR_FINISH": "",
  "IMMEDIATE_SURROUNDINGS": "",
  "EVIDENCE_OF_ELECTRICITY_PRESENCE": "",
  "VEHICLE_ASSETS_TWO_WHEELER": "",
  "VEHICLE_ASSETS_FOUR_WHEELER": "",
  "VEHICLE_ASSETS_OTHERS": "",

  "Interior_Condition_Impression": "",
  "Wall_Finish_Visible": "",
  "Flooring_Material_Visible": "",

  "Asset_Category_White_Goods": [],
  "Asset_Category_Brown_Goods": [],
  "Furniture_Type": [],
  "Fixtures_And_Decor_Type": []
}

---

## 5. FINAL ENFORCEMENT
- Output **JSON only**
- No markdown
- No comments
- No confidence scores
- No null values
- No extra keys
"""

def calculate_max_possible_score() -> int:
    """Hard-fixed maximum score"""
    return MAX_SCORE

    
    # For single-value fields, take the maximum value
    single_value_fields = [
        "Interior_Condition_Impression",
        "Wall_Finish_Visible",
        "Flooring_Material_Visible",
        "CONSTRUCTION_TYPE",
        "CONDITION_AND_MAINTENANCE",
        "ROOF_INFORMATION_TYPE_AND_MATERIAL",
        "WALL_CHARACTERISTICS_PRIMARY_MATERIAL_APPARENT",
        "WALL_CHARACTERISTICS_EXTERIOR_FINISH",
        "IMMEDIATE_SURROUNDINGS",
        "EVIDENCE_OF_ELECTRICITY_PRESENCE",
        "VEHICLE_ASSETS_TWO_WHEELER",
        "VEHICLE_ASSETS_FOUR_WHEELER",
        "VEHICLE_ASSETS_OTHERS"
    ]
    
    for field in single_value_fields:
        if field in SCORING_CONFIG:
            max_score += max(SCORING_CONFIG[field].values())
    
    # For array fields, sum all possible values (assuming all items can be present)
    array_fields = [
        "Asset_Category_White_Goods",
        "Asset_Category_Brown_Goods",
        "Furniture_Type",
        "Fixtures_And_Decor_Type"
    ]
    
    for field in array_fields:
        if field in SCORING_CONFIG:
            max_score += sum(SCORING_CONFIG[field].values())
    
    return max_score


def find_images_in_directory(directory: str = '.') -> List[str]:
    """Find all image files in the given directory"""
    image_extensions = ['*.png', '*.jpg', '*.jpeg', '*.gif', '*.webp', '*.PNG', '*.JPG', '*.JPEG']
    images = []
    for ext in image_extensions:
        images.extend(glob.glob(os.path.join(directory, ext)))
    return sorted(images)


def normalize_path(path: str) -> str:
    """Normalize Windows file paths by removing quotes and expanding"""
    path = path.strip('\'"')
    path = os.path.expanduser(path)
    path = os.path.abspath(path)
    return path


def load_image_to_base64(image_path: str) -> dict:
    """Load image and convert to format required by Gemini"""
    with open(image_path, 'rb') as f:
        image_data = f.read()
    
    ext = Path(image_path).suffix.lower()
    mime_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp'
    }
    mime_type = mime_types.get(ext, 'image/jpeg')
    
    return {
        'mime_type': mime_type,
        'data': image_data
    }


def analyze_with_gemini(image_paths: List[str], api_key: str) -> Dict[str, Any]:
    """Send images to Gemini 2 Flash for analysis"""
    print("\n" + "="*80)
    print("STEP 1: LOADING IMAGES")
    print("="*80)
    
    client = genai.Client(api_key=api_key)
    
    images = []
    for i, img_path in enumerate(image_paths, 1):
        print(f"  [{i}] Loading: {img_path}")
        images.append(load_image_to_base64(img_path))
    
    print(f"\n✓ Loaded {len(images)} images successfully")
    
    print("\n" + "="*80)
    print("STEP 2: SENDING TO GEMINI 2 FLASH")
    print("="*80)
    print("  Model: gemini-2.5-flash")
    print("  Prompt: System prompt with classification rules")
    print("  Processing...")
    
    content = [SYSTEM_PROMPT] + images
    response = client.models.generate_content(
        model="gemini-2.5-flash", contents=content
    )
    
    print("\n✓ Response received from Gemini")
    
    response_text = response.text.strip()
    
    if response_text.startswith('```json'):
        response_text = response_text[7:]
    if response_text.startswith('```'):
        response_text = response_text[3:]
    if response_text.endswith('```'):
        response_text = response_text[:-3]
    
    response_text = response_text.strip()
    
    print("\n" + "="*80)
    print("STEP 3: PARSING JSON RESPONSE")
    print("="*80)
    
    try:
        result = json.loads(response_text)
        print("✓ JSON parsed successfully")
        usage = {}
        try:
            meta = getattr(response, "usage_metadata", None)
            if meta:
                usage = {
                    "input_tokens": getattr(meta, "input_token_count", None) or getattr(meta, "prompt_token_count", None),
                    "output_tokens": getattr(meta, "output_token_count", None) or getattr(meta, "candidates_token_count", None),
                    "total_tokens": getattr(meta, "total_token_count", None)
                }
        except Exception:
            usage = {}
        try:
            analyze_with_gemini._last_usage = usage
        except Exception:
            pass
        return result
    except json.JSONDecodeError as e:
        print(f"✗ JSON parsing failed: {e}")
        print(f"\nRaw response:\n{response_text}")
        raise


def calculate_score(analysis_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Final scoring with:
    - Exterior vs Interior separation
    - Exterior dominance dependency rule
    - Fixed min/max score (22–150)
    """

    print("\n" + "="*80)
    print("STEP 4: CALCULATING SCORES (BALANCED EXTERIOR–INTERIOR)")
    print("="*80)

    total_base_score = 0
    exterior_score = 0
    interior_score = 0

    category_scores = {}
    scoring_details = []

    # ---------------- BASE SCORING ----------------
    for field, value in analysis_result.items():
        if field not in SCORING_CONFIG:
            continue

        field_score = 0
        items_scored = []

        if isinstance(value, list):
            for item in value:
                if item in SCORING_CONFIG[field]:
                    s = SCORING_CONFIG[field][item]
                    field_score += s
                    items_scored.append(f"{item} (+{s})")

        elif value in SCORING_CONFIG[field]:
            field_score = SCORING_CONFIG[field][value]
            items_scored.append(f"{value} (+{field_score})")

        if items_scored:
            total_base_score += field_score
            category_scores[field] = field_score

            if field in EXTERIOR_FIELDS:
                exterior_score += field_score
            elif field in INTERIOR_FIELDS:
                interior_score += field_score

            scoring_details.append({
                "field": field,
                "value": value,
                "items": items_scored,
                "score": field_score
            })

            print(f"\n  {field}:")
            for i in items_scored:
                print(f"    • {i}")
            print(f"    Subtotal: {field_score}")

    print("\n" + "-"*80)
    print(f"EXTERIOR SCORE: {exterior_score}")
    print(f"INTERIOR SCORE: {interior_score}")

    # ---------------- DEPENDENCY RULE ----------------
    adjusted_exterior = exterior_score
    interior_required = 0

    if exterior_score > EXTERIOR_THRESHOLD:
        interior_required = min(50, INTERIOR_RATIO_REQUIRED * exterior_score)

        if interior_score < interior_required:
            penalty_factor = interior_score / interior_required
            adjusted_exterior = round(exterior_score * penalty_factor, 2)

            print("\n⚠ EXTERIOR DOMINANCE DETECTED")
            print(f"Required Interior: {interior_required}")
            print(f"Penalty Factor: {round(penalty_factor, 2)}")
            print(f"Adjusted Exterior Score: {adjusted_exterior}")

    # ---------------- FINAL SCORE ----------------
    raw_final_score = adjusted_exterior + interior_score

    final_score = max(MIN_SCORE, min(MAX_SCORE, raw_final_score))

    normalized_score = round(
        100 * (final_score - MIN_SCORE) / (MAX_SCORE - MIN_SCORE), 2
    )

    print("\n" + "-"*80)
    print(f"RAW FINAL SCORE: {raw_final_score}")
    print(f"FINAL SCORE (CLAMPED): {final_score} / {MAX_SCORE}")
    print(f"NORMALIZED SCORE: {normalized_score}%")
    print("="*80)

    return {
        "exterior_score": exterior_score,
        "interior_score": interior_score,
        "adjusted_exterior_score": adjusted_exterior,
        "final_score": final_score,
        "total_score": final_score,
        "min_possible_score": MIN_SCORE,
        "max_possible_score": MAX_SCORE,
        "normalized_score": normalized_score,
        "category_scores": category_scores,
        "scoring_details": scoring_details
    }


def print_detailed_analysis(analysis_result: Dict[str, Any]):
    """Print detailed analysis results"""
    print("\n" + "="*80)
    print("DETAILED ANALYSIS RESULTS")
    print("="*80)
    
    print("\n--- EXTERIOR PROPERTY ---")
    exterior_fields = [
        'CONSTRUCTION_TYPE', 'CONDITION_AND_MAINTENANCE',
        'ROOF_INFORMATION_TYPE_AND_MATERIAL',
        'WALL_CHARACTERISTICS_PRIMARY_MATERIAL_APPARENT',
        'WALL_CHARACTERISTICS_EXTERIOR_FINISH',
        'IMMEDIATE_SURROUNDINGS', 'EVIDENCE_OF_ELECTRICITY_PRESENCE',
        'VEHICLE_ASSETS_TWO_WHEELER', 'VEHICLE_ASSETS_FOUR_WHEELER',
        'VEHICLE_ASSETS_OTHERS'
    ]
    
    for field in exterior_fields:
        if field in analysis_result:
            value = analysis_result[field]
            print(f"  {field}: {value}")
    
    print("\n--- INTERIOR PROPERTY ---")
    interior_fields = [
        'Interior_Condition_Impression', 'Wall_Finish_Visible',
        'Flooring_Material_Visible', 'Asset_Category_White_Goods',
        'Asset_Category_Brown_Goods', 'Furniture_Type',
        'Fixtures_And_Decor_Type'
    ]
    
    for field in interior_fields:
        if field in analysis_result:
            value = analysis_result[field]
            if isinstance(value, list):
                print(f"  {field}: {', '.join(value) if value else '[]'}")
            else:
                print(f"  {field}: {value}")


def main():
    """Main function with improved UI and file handling"""
    print("\n" + "="*80)
    print(" UNDERWRITING & LIFESTYLE ASSESSMENT SYSTEM")
    print("="*80)
    
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        api_key = input("\nEnter your Gemini API Key: ").strip()
        if not api_key:
            print("✗ API key is required!")
            return
    
    current_dir_images = find_images_in_directory()
    
    print("\n" + "-"*80)
    print("IMAGE INPUT OPTIONS")
    print("-"*80)
    
    if current_dir_images:
        print(f"\nFound {len(current_dir_images)} image(s) in current directory:")
        for i, img in enumerate(current_dir_images, 1):
            print(f"  [{i}] {os.path.basename(img)}")
        
        use_current = input("\nUse these images? (y/n): ").strip().lower()
        if use_current == 'y':
            if len(current_dir_images) >= 2:
                image_paths = current_dir_images[:4]
                print(f"\n✓ Using {len(image_paths)} images from current directory")
            else:
                print("  ⚠ Need at least 2 images. Please provide more.")
                current_dir_images = []
    
    if not current_dir_images or use_current != 'y':
        print("\nEnter image file paths (2-4 images: 1-2 interior, 1-2 exterior)")
        print("Tips:")
        print("  • Copy full path from File Explorer")
        print("  • Don't use quotes around the path")
        print("  • Make sure to include file extension (.png, .jpg, etc.)")
        print("  • Type 'done' when finished\n")
        
        image_paths = []
        while len(image_paths) < 4:
            path = input(f"Image {len(image_paths) + 1} path (or 'done'): ").strip()
            
            if path.lower() == 'done':
                if len(image_paths) >= 2:
                    break
                else:
                    print("  ⚠ Please provide at least 2 images")
                    continue
            
            normalized_path = normalize_path(path)
            
            if not os.path.exists(normalized_path):
                print(f"  ✗ File not found: {normalized_path}")
                continue
            
            if not any(normalized_path.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                print(f"  ✗ Not a valid image file")
                continue
            
            image_paths.append(normalized_path)
            print(f"  ✓ Added: {os.path.basename(normalized_path)}")
    
    if not image_paths:
        print("\n✗ No images provided!")
        return
    
    print(f"\n✓ Total images to analyze: {len(image_paths)}")
    
    try:
        analysis_result = analyze_with_gemini(image_paths, api_key)
        print_detailed_analysis(analysis_result)
        scoring_result = calculate_score(analysis_result)
        
        output = {
            'images_analyzed': image_paths,
            'analysis_result': analysis_result,
            'scoring_result': scoring_result
        }
        
        output_file = 'underwriting_analysis.json'
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"\n✓ Complete results saved to: {output_file}")
        
        print("\n" + "="*80)
        print("ANALYSIS COMPLETE")
        print("="*80)
        print(f"\n📊 Final Score: {scoring_result['total_score']} / {scoring_result['max_possible_score']}")
        print(f"📈 Normalized Score: {scoring_result['normalized_score']} / 100")
        
        # Add visual indicator
        percentage = scoring_result['normalized_score']
        bar_length = 50
        filled = int(bar_length * percentage / 100)
        bar = '█' * filled + '░' * (bar_length - filled)
        print(f"\n[{bar}] {percentage}%")
        
    except Exception as e:
        print(f"\n✗ Error occurred: {str(e)}")
        import traceback
        traceback.print_exc()


def run_full_pipeline(image_paths: List[str]) -> Dict[str, Any]:
    """
    Backend-safe wrapper for:
    Gemini Vision → Attribute extraction → Lifestyle scoring
    """

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    analysis_result = analyze_with_gemini(image_paths, api_key)
    scoring_result = calculate_score(analysis_result)
    usage = {}
    try:
        usage = getattr(analyze_with_gemini, "_last_usage", {}) or {}
    except Exception:
        usage = {}

    return {
        "analysis": analysis_result,
        "scoring": scoring_result,
        "usage": usage
    }