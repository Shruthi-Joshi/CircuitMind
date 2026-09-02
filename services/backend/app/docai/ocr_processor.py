"""OCR processor for extracting BOM data from images using Tesseract.

Supports extracting component information from:
- Photos of BOMs printed on paper
- Screenshots of BOM tables
- Component label photos
- Circuit board images with component markings
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

from .parser import BOMRow, _MPN_PATTERN, _REF_DES_PATTERN, _QTY_PATTERN, _try_int


class OCRProcessor:
    """OCR-based text extraction from images for BOM parsing."""
    
    def __init__(self):
        if not OCR_AVAILABLE:
            raise RuntimeError("OCR dependencies not installed. Run: pip install pytesseract pillow")
    
    def extract_text(self, image_path: str | Path) -> str:
        """Extract text from image using Tesseract OCR."""
        try:
            image = Image.open(image_path)
            # Optimize OCR for text detection
            text = pytesseract.image_to_string(
                image,
                config='--psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_/.,():; '
            )
            return text
        except Exception as e:
            raise RuntimeError(f"OCR extraction failed: {e}")
    
    def parse_bom_image(self, image_path: str | Path) -> list[dict]:
        """Parse BOM data from an image containing a BOM table or list."""
        text = self.extract_text(image_path)
        return self._parse_bom_text(text)
    
    def parse_component_label(self, image_path: str | Path) -> dict | None:
        """Extract component info from a single component label photo."""
        text = self.extract_text(image_path)
        
        # Look for MPN patterns in the text
        mpn_matches = _MPN_PATTERN.findall(text)
        if not mpn_matches:
            return None
        
        # Take the most likely MPN (longest one)
        mpn = max(mpn_matches, key=len)
        
        # Try to extract reference designator
        ref_match = _REF_DES_PATTERN.search(text)
        ref = ref_match.group() if ref_match else ""
        
        # Extract description (remaining text)
        desc_text = text.replace(mpn, "").replace(ref, "").strip()
        
        return {
            "line_number": 1,
            "reference_designator": ref,
            "mpn": mpn,
            "quantity": 1,
            "description": desc_text[:100],  # Limit description length
        }
    
    def parse_multiple_components(self, image_paths: list[str | Path]) -> list[dict]:
        """Extract components from multiple component photos."""
        components = []
        line_num = 1
        
        for image_path in image_paths:
            try:
                component = self.parse_component_label(image_path)
                if component:
                    component["line_number"] = line_num
                    components.append(component)
                    line_num += 1
            except Exception:
                # Skip failed images but continue processing others
                continue
        
        return components
    
    def smart_component_extraction(self, image_path: str | Path) -> dict | None:
        """Advanced component extraction with pattern recognition."""
        text = self.extract_text(image_path)
        
        # Enhanced patterns for different component types
        patterns = {
            'ic': re.compile(r'[A-Z]{2,6}\d{2,6}[A-Z]{0,4}', re.IGNORECASE),
            'resistor': re.compile(r'\d+[KMR]?\d*\s*[Ω]?', re.IGNORECASE), 
            'capacitor': re.compile(r'\d+[nμupμ]?[Ff]', re.IGNORECASE),
            'diode': re.compile(r'[1-9][NS]\d{4}[A-Z]?', re.IGNORECASE),
        }
        
        # Try to identify component type and extract relevant info
        component_type = "unknown"
        value = ""
        
        for comp_type, pattern in patterns.items():
            matches = pattern.findall(text)
            if matches:
                component_type = comp_type
                value = matches[0]
                break
        
        # Look for standard MPN
        mpn_matches = _MPN_PATTERN.findall(text)
        mpn = max(mpn_matches, key=len) if mpn_matches else value
        
        if not mpn:
            return None
        
        # Extract reference designator
        ref_match = _REF_DES_PATTERN.search(text)
        ref = ref_match.group() if ref_match else ""
        
        # Build description
        description = f"{component_type.title()} {value}".strip()
        if len(description) < 10:
            description = text.replace(mpn, "").replace(ref, "").strip()[:100]
        
        return {
            "line_number": 1,
            "reference_designator": ref,
            "mpn": mpn,
            "quantity": 1,
            "description": description,
            "component_type": component_type,
        }
    
    def _parse_bom_text(self, text: str) -> list[dict]:
        """Parse extracted OCR text into BOM rows using existing text parser."""
        from .parser import _parse_text
        return _parse_text(text)
    
    def extract_table_structured(self, image_path: str | Path) -> list[dict]:
        """Extract structured table data using OCR with table detection."""
        try:
            image = Image.open(image_path)
            # Use table-specific OCM mode
            data = pytesseract.image_to_data(
                image,
                output_type=pytesseract.Output.DICT,
                config='--psm 6'
            )
            
            # Group text by lines based on y-coordinates
            lines = {}
            for i in range(len(data['text'])):
                if int(data['conf'][i]) > 30:  # Confidence threshold
                    y = data['top'][i]
                    text = data['text'][i].strip()
                    if text:
                        if y not in lines:
                            lines[y] = []
                        lines[y].append((data['left'][i], text))
            
            # Sort lines by y-coordinate and texts by x-coordinate
            sorted_lines = []
            for y in sorted(lines.keys()):
                line_texts = [text for _, text in sorted(lines[y], key=lambda x: x[0])]
                sorted_lines.append(" ".join(line_texts))
            
            # Parse the structured lines
            return self._parse_bom_text("\n".join(sorted_lines))
            
        except Exception:
            # Fallback to simple text extraction
            return self.parse_bom_image(image_path)


def parse_bom_image(image_path: str | Path) -> list[dict]:
    """Parse BOM data from image file - main entry point."""
    processor = OCRProcessor()
    return processor.parse_bom_image(image_path)


def parse_component_image(image_path: str | Path) -> dict | None:
    """Extract single component info from image."""
    processor = OCRProcessor()
    return processor.parse_component_label(image_path)


# Image file extensions supported
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif'}


def is_image_file(filepath: str | Path) -> bool:
    """Check if file is a supported image format."""
    return Path(filepath).suffix.lower() in IMAGE_EXTENSIONS