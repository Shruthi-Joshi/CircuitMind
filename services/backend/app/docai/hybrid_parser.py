"""Hybrid parser for combining multiple input types into unified BOM data.

Merges data from CSV files, images, PDFs, and other sources intelligently,
handling duplicates and conflicting information.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .parser import parse_bom_file
from .ocr_processor import is_image_file, OCRProcessor


class HybridBOMParser:
    """Parser that intelligently combines multiple input sources."""
    
    def __init__(self):
        self.ocr_processor = None
        try:
            self.ocr_processor = OCRProcessor()
        except RuntimeError:
            pass  # OCR not available
    
    def parse_mixed_files(self, filepaths: list[str | Path]) -> list[dict]:
        """Parse multiple files of different types and merge intelligently."""
        all_components = []
        component_map = {}  # MPN -> component data for deduplication
        
        # Separate files by type for optimal processing order
        structured_files = []  # CSV, Excel, etc.
        image_files = []
        other_files = []
        
        for filepath in filepaths:
            path = Path(filepath)
            if is_image_file(path):
                image_files.append(path)
            elif path.suffix.lower() in {'.csv', '.xlsx', '.xls'}:
                structured_files.append(path)
            else:
                other_files.append(path)
        
        # Process structured files first (highest confidence)
        for filepath in structured_files:
            try:
                components = parse_bom_file(filepath)
                for comp in components:
                    mpn = comp.get('mpn', '').strip().upper()
                    if mpn and mpn not in component_map:
                        comp['source_type'] = 'structured'
                        comp['source_file'] = str(filepath.name)
                        comp['confidence'] = 0.95
                        component_map[mpn] = comp
                        all_components.append(comp)
            except Exception:
                continue
        
        # Process other text files (medium confidence)
        for filepath in other_files:
            try:
                components = parse_bom_file(filepath)
                for comp in components:
                    mpn = comp.get('mpn', '').strip().upper()
                    if mpn and mpn not in component_map:
                        comp['source_type'] = 'text'
                        comp['source_file'] = str(filepath.name)
                        comp['confidence'] = 0.85
                        component_map[mpn] = comp
                        all_components.append(comp)
                    elif mpn in component_map:
                        # Merge additional info
                        self._merge_component_data(component_map[mpn], comp)
            except Exception:
                continue
        
        # Process images last (lower confidence, fill gaps)
        if self.ocr_processor and image_files:
            for filepath in image_files:
                try:
                    components = parse_bom_file(filepath)
                    for comp in components:
                        mpn = comp.get('mpn', '').strip().upper()
                        if mpn and mpn not in component_map:
                            comp['source_type'] = 'image'
                            comp['source_file'] = str(filepath.name)
                            comp['confidence'] = 0.70
                            component_map[mpn] = comp
                            all_components.append(comp)
                        elif mpn in component_map:
                            # Enhance existing component with image data
                            self._merge_component_data(component_map[mpn], comp)
                except Exception:
                    continue
        
        # Re-number line items sequentially
        for i, comp in enumerate(all_components, 1):
            comp['line_number'] = i
        
        return all_components
    
    def _merge_component_data(self, primary: dict, secondary: dict) -> None:
        """Merge secondary component data into primary, preserving higher confidence data."""
        
        # Merge descriptions (take longer, more detailed one)
        primary_desc = primary.get('description', '').strip()
        secondary_desc = secondary.get('description', '').strip()
        
        if len(secondary_desc) > len(primary_desc) and secondary_desc:
            primary['description'] = secondary_desc
        
        # Merge reference designators if primary is missing
        if not primary.get('reference_designator') and secondary.get('reference_designator'):
            primary['reference_designator'] = secondary['reference_designator']
        
        # Add component type if detected from image
        if secondary.get('component_type') and not primary.get('component_type'):
            primary['component_type'] = secondary['component_type']
        
        # Track multiple sources
        if 'additional_sources' not in primary:
            primary['additional_sources'] = []
        
        primary['additional_sources'].append({
            'type': secondary.get('source_type', 'unknown'),
            'file': secondary.get('source_file', 'unknown'),
            'confidence': secondary.get('confidence', 0.5)
        })
    
    def parse_component_photos_batch(self, image_paths: list[str | Path]) -> list[dict]:
        """Process multiple component photos and return combined results."""
        if not self.ocr_processor:
            return []
        
        return self.ocr_processor.parse_multiple_components(image_paths)
    
    def smart_merge_bom_sources(self, 
                               structured_file: str | Path | None = None,
                               image_files: list[str | Path] | None = None,
                               component_photos: list[str | Path] | None = None) -> list[dict]:
        """High-level method for typical hackathon use case."""
        
        all_files = []
        
        if structured_file:
            all_files.append(structured_file)
        
        if image_files:
            all_files.extend(image_files)
        
        # Parse main files
        components = self.parse_mixed_files(all_files)
        
        # Add individual component photos
        if component_photos and self.ocr_processor:
            photo_components = self.parse_component_photos_batch(component_photos)
            
            # Merge photo results with main BOM
            component_map = {comp.get('mpn', '').strip().upper(): comp for comp in components}
            
            for photo_comp in photo_components:
                mpn = photo_comp.get('mpn', '').strip().upper()
                if mpn and mpn not in component_map:
                    photo_comp['source_type'] = 'component_photo'
                    photo_comp['confidence'] = 0.75
                    photo_comp['line_number'] = len(components) + 1
                    components.append(photo_comp)
        
        return components


# Convenience functions
def parse_hybrid_bom(filepaths: list[str | Path]) -> list[dict]:
    """Parse mixed file types into unified BOM."""
    parser = HybridBOMParser()
    return parser.parse_mixed_files(filepaths)


def merge_bom_sources(structured_file: str | Path | None = None,
                     image_files: list[str | Path] | None = None,
                     component_photos: list[str | Path] | None = None) -> list[dict]:
    """Smart merge for typical hackathon demo scenarios."""
    parser = HybridBOMParser()
    return parser.smart_merge_bom_sources(structured_file, image_files, component_photos)