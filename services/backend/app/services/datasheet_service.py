"""Datasheet integration service for automatic component specification lookup.

Integrates with component databases and APIs to fetch detailed specifications,
datasheets, and real-time availability data for identified components.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import quote

try:
    import aiohttp
    HTTP_AVAILABLE = True
except ImportError:
    HTTP_AVAILABLE = False


@dataclass
class ComponentSpecs:
    """Complete component specifications from datasheet APIs."""
    mpn: str
    manufacturer: str
    description: str
    datasheet_url: Optional[str] = None
    electrical_specs: Dict[str, Any] = None
    mechanical_specs: Dict[str, Any] = None
    pricing: List[Dict[str, Any]] = None
    availability: Dict[str, Any] = None
    alternatives: List[str] = None
    
    def __post_init__(self):
        if self.electrical_specs is None:
            self.electrical_specs = {}
        if self.mechanical_specs is None:
            self.mechanical_specs = {}
        if self.pricing is None:
            self.pricing = []
        if self.availability is None:
            self.availability = {}
        if self.alternatives is None:
            self.alternatives = []


class DatasheetService:
    """Service for fetching component datasheets and specifications."""
    
    def __init__(self):
        self.session = None
        
        # API endpoints (would be configured with real API keys)
        self.apis = {
            "octopart": {
                "base_url": "https://octopart.com/api/v4/rest",
                "api_key": "demo_key",  # Would be real API key
                "enabled": False,  # Disabled for demo
            },
            "digikey": {
                "base_url": "https://api.digikey.com/v1",
                "api_key": "demo_key",
                "enabled": False,
            },
            "mouser": {
                "base_url": "https://api.mouser.com/api/v1",
                "api_key": "demo_key", 
                "enabled": False,
            }
        }
    
    async def get_component_specs(self, mpn: str, manufacturer: str = None) -> ComponentSpecs:
        """Fetch complete component specifications from multiple APIs."""
        
        # For demo/hackathon, return realistic mock data
        mock_specs = self._get_mock_specs(mpn, manufacturer)
        if mock_specs:
            return mock_specs
        
        # Real API integration (disabled for demo)
        if HTTP_AVAILABLE and any(api["enabled"] for api in self.apis.values()):
            return await self._fetch_from_apis(mpn, manufacturer)
        
        # Fallback: basic specs only
        return ComponentSpecs(
            mpn=mpn,
            manufacturer=manufacturer or "Unknown",
            description=f"Component {mpn}",
            datasheet_url=None
        )
    
    def _get_mock_specs(self, mpn: str, manufacturer: str = None) -> Optional[ComponentSpecs]:
        """Return realistic mock datasheet data for demo purposes."""
        
        # Mock datasheet database for common components
        mock_db = {
            "STM32F411CEU6": ComponentSpecs(
                mpn="STM32F411CEU6",
                manufacturer="STMicroelectronics",
                description="ARM Cortex-M4 32-bit MCU, 512KB Flash, 128KB RAM, 100MHz",
                datasheet_url="https://www.st.com/resource/en/datasheet/stm32f411ce.pdf",
                electrical_specs={
                    "supply_voltage_min": 1.7,
                    "supply_voltage_max": 3.6,
                    "operating_temp_min": -40,
                    "operating_temp_max": 85,
                    "flash_size_kb": 512,
                    "ram_size_kb": 128,
                    "cpu_frequency_mhz": 100,
                    "gpio_pins": 81,
                    "adc_channels": 16,
                    "timers": 11,
                },
                mechanical_specs={
                    "package": "UFQFPN48",
                    "pin_count": 48,
                    "dimensions_mm": "7x7x0.55",
                    "pitch_mm": 0.5,
                },
                pricing=[
                    {"supplier": "DigiKey", "price_usd": 5.20, "qty_min": 1, "in_stock": False},
                    {"supplier": "Mouser", "price_usd": 5.35, "qty_min": 1, "in_stock": False},
                    {"supplier": "Arrow", "price_usd": 5.10, "qty_min": 1, "in_stock": False},
                ],
                availability={
                    "total_stock": 0,
                    "lead_time_weeks": 8,
                    "lifecycle_status": "Active",
                },
                alternatives=["STM32F401CEU6", "STM32F411CEU7", "STM32F446CEU6"]
            ),
            
            "AP2112K-3.3TRG1": ComponentSpecs(
                mpn="AP2112K-3.3TRG1",
                manufacturer="Diodes Incorporated",
                description="3.3V 600mA Ultra Low Dropout Linear Regulator",
                datasheet_url="https://www.diodes.com/assets/Datasheets/AP2112.pdf",
                electrical_specs={
                    "input_voltage_min": 2.5,
                    "input_voltage_max": 6.0,
                    "output_voltage": 3.3,
                    "output_current_max": 0.6,
                    "dropout_voltage": 0.4,
                    "quiescent_current_ua": 55,
                    "line_regulation": 0.2,
                    "load_regulation": 0.4,
                },
                mechanical_specs={
                    "package": "SOT-23-5",
                    "pin_count": 5,
                    "dimensions_mm": "2.9x1.6x1.1",
                },
                pricing=[
                    {"supplier": "DigiKey", "price_usd": 0.45, "qty_min": 1, "in_stock": False},
                    {"supplier": "Mouser", "price_usd": 0.48, "qty_min": 1, "in_stock": False},
                ],
                availability={
                    "total_stock": 0,
                    "lead_time_weeks": 5,
                    "lifecycle_status": "Active",
                },
                alternatives=["AMS1117-3.3", "LM1117-3.3", "XC6206P332MR"]
            ),
            
            "RC0603FR-0710KL": ComponentSpecs(
                mpn="RC0603FR-0710KL",
                manufacturer="Yageo",
                description="10kΩ ±1% 0.1W Thick Film Resistor 0603",
                datasheet_url="https://www.yageo.com/upload/media/product/productsearch/datasheet/rchip/PYu-RC_Group_51_RoHS_L_11.pdf",
                electrical_specs={
                    "resistance_ohm": 10000,
                    "tolerance_percent": 1,
                    "power_rating_w": 0.1,
                    "voltage_rating_v": 75,
                    "temp_coefficient_ppm": 100,
                    "operating_temp_min": -55,
                    "operating_temp_max": 155,
                },
                mechanical_specs={
                    "package": "0603",
                    "dimensions_mm": "1.6x0.8x0.45",
                },
                pricing=[
                    {"supplier": "DigiKey", "price_usd": 0.005, "qty_min": 1, "in_stock": True},
                    {"supplier": "Mouser", "price_usd": 0.006, "qty_min": 1, "in_stock": True},
                ],
                availability={
                    "total_stock": 100000,
                    "lead_time_weeks": 0,
                    "lifecycle_status": "Active",
                },
                alternatives=["CRCW060310K0FKEA", "ERJ-3EKF1002V", "RT0603FRE0710KL"]
            ),
        }
        
        return mock_db.get(mpn.upper())
    
    async def _fetch_from_apis(self, mpn: str, manufacturer: str = None) -> ComponentSpecs:
        """Fetch real data from component APIs (for production use)."""
        
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        tasks = []
        
        # Octopart API
        if self.apis["octopart"]["enabled"]:
            tasks.append(self._fetch_octopart(mpn, manufacturer))
        
        # DigiKey API  
        if self.apis["digikey"]["enabled"]:
            tasks.append(self._fetch_digikey(mpn, manufacturer))
        
        # Mouser API
        if self.apis["mouser"]["enabled"]:
            tasks.append(self._fetch_mouser(mpn, manufacturer))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return self._merge_api_results(results, mpn, manufacturer)
        
        return ComponentSpecs(mpn=mpn, manufacturer=manufacturer or "Unknown", description="")
    
    async def _fetch_octopart(self, mpn: str, manufacturer: str = None):
        """Fetch from Octopart API."""
        # Implementation would go here
        pass
    
    async def _fetch_digikey(self, mpn: str, manufacturer: str = None):
        """Fetch from DigiKey API.""" 
        # Implementation would go here
        pass
    
    async def _fetch_mouser(self, mpn: str, manufacturer: str = None):
        """Fetch from Mouser API."""
        # Implementation would go here
        pass
    
    def _merge_api_results(self, results: List, mpn: str, manufacturer: str) -> ComponentSpecs:
        """Merge results from multiple APIs."""
        # Intelligent merging logic would go here
        return ComponentSpecs(mpn=mpn, manufacturer=manufacturer or "Unknown", description="")
    
    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()


# Convenience functions
async def get_datasheet_specs(mpn: str, manufacturer: str = None) -> ComponentSpecs:
    """Get complete component specifications including datasheet."""
    service = DatasheetService()
    try:
        return await service.get_component_specs(mpn, manufacturer)
    finally:
        await service.close()


def get_datasheet_specs_sync(mpn: str, manufacturer: str = None) -> ComponentSpecs:
    """Synchronous version for easier integration."""
    return asyncio.run(get_datasheet_specs(mpn, manufacturer))