import cv2
import numpy as np
from loguru import logger
import re

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

def extract_license_plate(crop: np.ndarray) -> str:
    """
    Attempt to extract a license plate string from a vehicle crop.
    Uses basic contour heuristics and OCR if available.
    """
    if crop is None or crop.size == 0:
        return "Unknown"
        
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    # Basic simulated result if tesseract is not configured
    # In a real system, you would use PaddleOCR or EasyOCR here.
    if not HAS_TESSERACT:
        return "MOCK-PLT"

    # Edge detection
    bfilter = cv2.bilateralFilter(gray, 11, 17, 17)
    edged = cv2.Canny(bfilter, 30, 200)
    
    # Find contours
    keypoints = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    contours = keypoints[0] if len(keypoints) == 2 else keypoints[1]
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]
    
    location = None
    for contour in contours:
        approx = cv2.approxPolyDP(contour, 10, True)
        if len(approx) == 4:
            location = approx
            break
            
    if location is None:
        return "Unknown"
        
    mask = np.zeros(gray.shape, np.uint8)
    new_image = cv2.drawContours(mask, [location], 0, 255, -1)
    new_image = cv2.bitwise_and(crop, crop, mask=mask)
    
    (x, y) = np.where(mask == 255)
    (x1, y1) = (np.min(x), np.min(y))
    (x2, y2) = (np.max(x), np.max(y))
    cropped_image = gray[x1:x2+1, y1:y2+1]
    
    try:
        text = pytesseract.image_to_string(cropped_image, config='--psm 8')
        clean_text = re.sub(r'[\W_]+', '', text)
        if len(clean_text) >= 4:
            return clean_text.upper()
    except Exception as e:
        logger.debug(f"OCR failed: {e}")
        
    return "Unknown"
