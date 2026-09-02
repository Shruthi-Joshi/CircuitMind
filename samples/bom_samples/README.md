# 📂 Sample BOM Files for Multi-Modal Demo

This directory contains realistic BOM files for testing and demonstrating the multi-modal input capabilities.

## 📊 Structured BOMs

### `iot_sensor_board_v2.1.csv`
**Type**: Professional CSV BOM  
**Components**: 35 components  
**Use Case**: IoT sensor board with STM32F411, ESP32-S3, various passives  
**Features**: Complete part numbers, manufacturers, packages, values  
**Demo Value**: Shows how structured data gets 95% confidence scoring  

### `arduino_clone_detailed.csv` 
**Type**: Detailed BOM with pricing  
**Components**: 25 components  
**Use Case**: Arduino-compatible board  
**Features**: Pricing, suppliers, lead times, quantities  
**Demo Value**: Demonstrates supply chain integration capabilities  

## 📝 Text/Handwritten Style BOMs

### `power_supply_bom_handwritten.txt`
**Type**: Handwritten/typed BOM  
**Components**: 14 components  
**Use Case**: Linear power supply module  
**Features**: Notes, estimated costs, assembly instructions  
**Demo Value**: Shows OCR-like processing of informal BOMs  

### `led_driver_simple.txt`
**Type**: Quick component list  
**Components**: 13 components  
**Use Case**: LED driver circuit  
**Features**: Minimal format, component values only  
**Demo Value**: Handles incomplete/informal data gracefully  

### `audio_amp_schematic_extracted.txt`
**Type**: PDF extraction style  
**Components**: 19 components  
**Use Case**: Audio amplifier circuit  
**Features**: Schematic format, performance specs  
**Demo Value**: Shows PDF/schematic processing capabilities  

## 📸 Component Photos (OCR Simulation)

### `component_photos/stm32_chip.txt`
**Simulates**: Photo of STM32F411CEU6 microcontroller  
**Contains**: Part marking, manufacturer, package info  
**Demo Value**: Shows IC identification from component photos  

### `component_photos/resistor_10k.txt` 
**Simulates**: Photo of 10kΩ resistor  
**Contains**: Part number, value, package  
**Demo Value**: Demonstrates resistor value extraction  

### `component_photos/capacitor_100nf.txt`
**Simulates**: Photo of 100nF ceramic capacitor  
**Contains**: Murata part number, value, voltage rating  
**Demo Value**: Shows capacitor specification extraction  

### `component_photos/opamp_lm358.txt`
**Simulates**: Photo of LM358 op-amp  
**Contains**: TI part number, package info  
**Demo Value**: Demonstrates IC identification  

## 🎯 Hackathon Demo Scenarios

### Scenario 1: Mixed Input Processing
```bash
Files: iot_sensor_board_v2.1.csv + power_supply_bom_handwritten.txt + component photos
Result: Unified BOM with confidence scores and source tracking
```

### Scenario 2: Component Identification
```bash  
Files: All component photos
Result: Real-time component identification with type detection
```

### Scenario 3: Data Enhancement
```bash
Files: led_driver_simple.txt + detailed component photos
Result: Enhanced BOM with photos filling missing specifications
```

## 🔧 Usage Examples

### Test Individual Files
```python
from docai.parser import parse_bom_file
components = parse_bom_file("sample_files/iot_sensor_board_v2.1.csv")
print(f"Found {len(components)} components")
```

### Test Hybrid Parsing
```python
from docai.hybrid_parser import parse_hybrid_bom
files = ["sample_files/iot_sensor_board_v2.1.csv", 
         "sample_files/power_supply_bom_handwritten.txt"]
components = parse_hybrid_bom(files)
```

### API Testing
```bash
# Upload batch files
curl -X POST "http://localhost:8000/api/v1/bom/analyze/batch" \
  -F "files=@sample_files/iot_sensor_board_v2.1.csv" \
  -F "files=@sample_files/power_supply_bom_handwritten.txt"

# Component photo analysis  
curl -X POST "http://localhost:8000/api/v1/components/analyze-photos" \
  -F "files=@sample_files/component_photos/stm32_chip.txt"
```

## 💡 Demo Tips

1. **Start with structured**: Show CSV parsing first (instant success)
2. **Add complexity**: Mix in handwritten BOMs (shows intelligence)  
3. **Finish with photos**: Component identification (wow factor)
4. **Highlight confidence**: Show how system tracks source reliability
5. **Show conflicts**: Upload same component from different sources

## 📈 Expected Results

- **Total unique components**: ~60-80 after deduplication
- **Confidence distribution**: 95% (CSV) → 85% (text) → 75% (photos)
- **Processing time**: 2-5 seconds for full batch
- **Success rate**: 90%+ component extraction

## 🚀 Live Demo Enhancement

For live demos, replace the `.txt` files in `component_photos/` with actual `.jpg` images:
1. Take photos of real components
2. Replace simulation files with actual images  
3. System will perform real OCR extraction
4. Even more impressive live results!