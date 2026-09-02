"""Seed the database with a realistic synthetic component catalog and
multi-vendor stock data so the system is fully runnable without external APIs.

Run via ``python -m app.db.seed`` or automatically on first startup when
the components table is empty.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Component, Supplier, SupplierStock
from .session import SessionLocal
from ..embeddings import embed_batch

# ── Synthetic component catalog ──────────────────────────────────────────────

_COMPONENTS: list[dict] = [
    # Microcontrollers
    dict(mpn="STM32F411CEU6", manufacturer="STMicroelectronics",
         description="ARM Cortex-M4 MCU 100 MHz 512 KB Flash 128 KB RAM UFQFPN48",
         category="MCU", package="UFQFPN48", pin_count=48,
         voltage_min=1.7, voltage_max=3.6,
         specs={"core": "Cortex-M4", "flash_kb": 512, "ram_kb": 128, "freq_mhz": 100}),
    dict(mpn="STM32F401CCU6", manufacturer="STMicroelectronics",
         description="ARM Cortex-M4 MCU 84 MHz 256 KB Flash 64 KB RAM UFQFPN48",
         category="MCU", package="UFQFPN48", pin_count=48,
         voltage_min=1.7, voltage_max=3.6,
         specs={"core": "Cortex-M4", "flash_kb": 256, "ram_kb": 64, "freq_mhz": 84}),
    dict(mpn="ESP32-S3-WROOM-1", manufacturer="Espressif",
         description="Dual-core Xtensa 240 MHz WiFi BLE SoC module 8 MB Flash QFN",
         category="MCU", package="QFN-56", pin_count=56,
         voltage_min=3.0, voltage_max=3.6,
         specs={"core": "Xtensa-LX7", "flash_kb": 8192, "ram_kb": 512, "freq_mhz": 240}),
    dict(mpn="ATSAMD21G18A-MUT", manufacturer="Microchip",
         description="ARM Cortex-M0+ MCU 48 MHz 256 KB Flash 32 KB RAM TQFP48",
         category="MCU", package="TQFP48", pin_count=48,
         voltage_min=1.62, voltage_max=3.63,
         specs={"core": "Cortex-M0+", "flash_kb": 256, "ram_kb": 32, "freq_mhz": 48}),
    # Additional MCUs from sample BOMs
    dict(mpn="ATMEGA328P-PU", manufacturer="Microchip Technology",
         description="8-bit microcontroller 32KB Flash DIP-28",
         category="MCU", package="DIP-28", pin_count=28,
         voltage_min=1.8, voltage_max=5.5,
         specs={"core": "AVR", "flash_kb": 32, "ram_kb": 2, "freq_mhz": 20}),
    dict(mpn="CP2102N-A01-GQFN28", manufacturer="Silicon Labs",
         description="USB to UART bridge controller",
         category="MCU", package="QFN-28", pin_count=28,
         voltage_min=1.8, voltage_max=3.6,
         specs={"interface": "USB-UART"}),

    # Voltage regulators
    dict(mpn="AMS1117-3.3", manufacturer="Advanced Monolithic Systems",
         description="3.3 V 1 A LDO voltage regulator SOT-223",
         category="Voltage Regulator", package="SOT-223", pin_count=3,
         voltage_min=3.3, voltage_max=3.3,
         specs={"output_v": 3.3, "max_current_a": 1.0, "dropout_v": 1.3}),
    dict(mpn="AP2112K-3.3TRG1", manufacturer="Diodes Inc.",
         description="3.3 V 600 mA LDO regulator SOT-23-5",
         category="Voltage Regulator", package="SOT-23-5", pin_count=5,
         voltage_min=3.3, voltage_max=3.3,
         specs={"output_v": 3.3, "max_current_a": 0.6, "dropout_v": 0.4}),
    dict(mpn="LM1117MP-3.3", manufacturer="Texas Instruments",
         description="3.3 V 800 mA LDO voltage regulator SOT-223",
         category="Voltage Regulator", package="SOT-223", pin_count=3,
         voltage_min=3.3, voltage_max=3.3,
         specs={"output_v": 3.3, "max_current_a": 0.8, "dropout_v": 1.2}),
    # Additional regulators from samples
    dict(mpn="AMS1117-5.0", manufacturer="Advanced Monolithic Systems",
         description="5V 1A Linear voltage regulator SOT-223",
         category="Voltage Regulator", package="SOT-223", pin_count=3,
         voltage_min=5.0, voltage_max=5.0,
         specs={"output_v": 5.0, "max_current_a": 1.0, "dropout_v": 1.3}),
    dict(mpn="LM2596S-3.3", manufacturer="Texas Instruments",
         description="3A Step-down voltage regulator TO-263",
         category="Voltage Regulator", package="TO-263", pin_count=5,
         voltage_min=3.3, voltage_max=3.3,
         specs={"output_v": 3.3, "max_current_a": 3.0, "switching": True}),

    # Op-amps
    dict(mpn="LM358DR", manufacturer="Texas Instruments",
         description="Dual general-purpose operational amplifier SOIC-8",
         category="Op-Amp", package="SOIC-8", pin_count=8,
         voltage_min=3.0, voltage_max=32.0,
         specs={"channels": 2, "gbw_mhz": 1.0, "slew_rate_v_us": 0.6}),
    dict(mpn="MCP6002-I/SN", manufacturer="Microchip",
         description="Dual 1 MHz rail-to-rail op-amp SOIC-8",
         category="Op-Amp", package="SOIC-8", pin_count=8,
         voltage_min=1.8, voltage_max=6.0,
         specs={"channels": 2, "gbw_mhz": 1.0, "slew_rate_v_us": 0.6}),

    # Capacitors
    dict(mpn="GRM188R71C104KA01D", manufacturer="Murata",
         description="100 nF 16 V X7R MLCC 0603",
         category="Capacitor", package="0603", pin_count=2,
         voltage_min=0.0, voltage_max=16.0,
         specs={"capacitance_nf": 100, "dielectric": "X7R", "tolerance": "10%"}),
    dict(mpn="CL10B104KB8NNNC", manufacturer="Samsung Electro-Mechanics",
         description="100 nF 50 V X7R MLCC 0603",
         category="Capacitor", package="0603", pin_count=2,
         voltage_min=0.0, voltage_max=50.0,
         specs={"capacitance_nf": 100, "dielectric": "X7R", "tolerance": "10%"}),
    dict(mpn="C0603C104J4RACTU", manufacturer="KEMET",
         description="100 nF 16 V X7R MLCC 0603",
         category="Capacitor", package="0603", pin_count=2,
         voltage_min=0.0, voltage_max=16.0,
         specs={"capacitance_nf": 100, "dielectric": "X7R", "tolerance": "5%"}),
    # Additional capacitors from samples
    dict(mpn="CL10B105KB8NNNC", manufacturer="Samsung",
         description="Multilayer ceramic capacitor X7R 50V 1µF 0603",
         category="Capacitor", package="0603", pin_count=2,
         voltage_min=0.0, voltage_max=50.0,
         specs={"capacitance_nf": 1000, "dielectric": "X7R", "tolerance": "10%"}),
    dict(mpn="TAJB226K016RNJ", manufacturer="AVX",
         description="Tantalum capacitor 16V 20% 22µF CASE-B",
         category="Capacitor", package="CASE-B", pin_count=2,
         voltage_min=0.0, voltage_max=16.0,
         specs={"capacitance_uf": 22, "dielectric": "Tantalum", "tolerance": "20%"}),
    dict(mpn="CC0603KRX7R9BB102", manufacturer="Yageo",
         description="Ceramic capacitor X7R 50V 10% 1nF 0603",
         category="Capacitor", package="0603", pin_count=2,
         voltage_min=0.0, voltage_max=50.0,
         specs={"capacitance_nf": 1, "dielectric": "X7R", "tolerance": "10%"}),

    # Resistors
    dict(mpn="RC0603FR-0710KL", manufacturer="Yageo",
         description="10 kΩ 1% 0603 thick-film resistor",
         category="Resistor", package="0603", pin_count=2,
         voltage_min=0.0, voltage_max=75.0,
         specs={"resistance_ohm": 10000, "tolerance": "1%", "power_w": 0.1}),
    dict(mpn="CRCW060310K0FKEA", manufacturer="Vishay",
         description="10 kΩ 1% 0603 thick-film resistor",
         category="Resistor", package="0603", pin_count=2,
         voltage_min=0.0, voltage_max=75.0,
         specs={"resistance_ohm": 10000, "tolerance": "1%", "power_w": 0.1}),
    # Additional resistors from samples
    dict(mpn="CRCW06034K70FKEA", manufacturer="Vishay",
         description="Thick film resistor 1% 1/10W 4.7kΩ 0603",
         category="Resistor", package="0603", pin_count=2,
         voltage_min=0.0, voltage_max=75.0,
         specs={"resistance_ohm": 4700, "tolerance": "1%", "power_w": 0.1}),
    dict(mpn="ERJ-3EKF1001V", manufacturer="Panasonic",
         description="Thick film resistor 1% 1/10W 1kΩ 0603",
         category="Resistor", package="0603", pin_count=2,
         voltage_min=0.0, voltage_max=75.0,
         specs={"resistance_ohm": 1000, "tolerance": "1%", "power_w": 0.1}),
    dict(mpn="RC0603JR-0722RL", manufacturer="Yageo",
         description="Thick film resistor 5% 1/10W 22Ω 0603",
         category="Resistor", package="0603", pin_count=2,
         voltage_min=0.0, voltage_max=75.0,
         specs={"resistance_ohm": 22, "tolerance": "5%", "power_w": 0.1}),

    # Connectors
    dict(mpn="USB4110-GF-A", manufacturer="GCT",
         description="USB Type-C 2.0 receptacle SMD right-angle 16-pin",
         category="Connector", package="SMD", pin_count=16,
         voltage_min=0.0, voltage_max=5.0,
         specs={"interface": "USB-C", "version": "2.0"}),
    dict(mpn="10118192-0001LF", manufacturer="Amphenol",
         description="Micro USB 2.0 Type-B receptacle SMD 5-pin",
         category="Connector", package="SMD", pin_count=5,
         voltage_min=0.0, voltage_max=5.0,
         specs={"interface": "Micro-USB-B", "version": "2.0"}),
    # Additional connectors from samples
    dict(mpn="S2B-PH-K-S(LF)(SN)", manufacturer="JST",
         description="Connector header 2 position 2mm PH-2",
         category="Connector", package="PH-2", pin_count=2,
         voltage_min=0.0, voltage_max=50.0,
         specs={"positions": 2, "pitch_mm": 2.0}),
    dict(mpn="61300211121", manufacturer="Würth Elektronik",
         description="Header connector 6 position 2.54mm",
         category="Connector", package="2.54mm", pin_count=6,
         voltage_min=0.0, voltage_max=250.0,
         specs={"positions": 6, "pitch_mm": 2.54}),

    # Crystals / oscillators
    dict(mpn="ABM8-272-T3", manufacturer="Abracon",
         description="8 MHz crystal 18 pF 20 ppm 3.2x2.5 mm",
         category="Crystal", package="3.2x2.5mm", pin_count=4,
         voltage_min=0.0, voltage_max=0.0,
         specs={"frequency_mhz": 8, "load_pf": 18, "ppm": 20}),
    dict(mpn="ECS-.327-12.5-34B-TR", manufacturer="ECS International",
         description="32.768 kHz crystal 12.5 pF 20 ppm 3.2x1.5 mm",
         category="Crystal", package="3.2x1.5mm", pin_count=2,
         voltage_min=0.0, voltage_max=0.0,
         specs={"frequency_mhz": 0.032768, "load_pf": 12.5, "ppm": 20}),
    # Additional crystals from samples
    dict(mpn="FC-135 32.7680KA-A3", manufacturer="Epson",
         description="Crystal 32.768kHz ±20ppm 12.5pF 3.2x1.5mm",
         category="Crystal", package="3.2x1.5mm", pin_count=2,
         voltage_min=0.0, voltage_max=0.0,
         specs={"frequency_mhz": 0.032768, "load_pf": 12.5, "ppm": 20}),

    # Additional ICs from samples
    dict(mpn="FT232RL", manufacturer="FTDI",
         description="USB to serial UART interface IC SSOP-28",
         category="Interface IC", package="SSOP-28", pin_count=28,
         voltage_min=3.3, voltage_max=5.25,
         specs={"interface": "USB-UART", "speed_bps": 3000000}),

    # Transistors
    dict(mpn="2N3904", manufacturer="ON Semiconductor",
         description="NPN bipolar transistor 40V 200mA TO-92",
         category="Transistor", package="TO-92", pin_count=3,
         voltage_min=0.0, voltage_max=40.0,
         specs={"type": "NPN", "ic_max_a": 0.2, "vceo_v": 40}),
    dict(mpn="IRF520N", manufacturer="Infineon",
         description="N-channel MOSFET 100V 9.2A TO-220",
         category="Transistor", package="TO-220", pin_count=3,
         voltage_min=0.0, voltage_max=100.0,
         specs={"type": "N-MOSFET", "id_max_a": 9.2, "vds_v": 100}),

    # Diodes
    dict(mpn="BAT54S", manufacturer="Infineon",
         description="Schottky diode dual series 30V SOT-23",
         category="Diode", package="SOT-23", pin_count=3,
         voltage_min=0.0, voltage_max=30.0,
         specs={"type": "Schottky", "vr_v": 30, "if_ma": 200}),
    dict(mpn="1N4007", manufacturer="Vishay Semiconductor",
         description="Rectifier diode 1A 1000V DO-41",
         category="Diode", package="DO-41", pin_count=2,
         voltage_min=0.0, voltage_max=1000.0,
         specs={"type": "Rectifier", "vr_v": 1000, "if_a": 1.0}),

    # LEDs
    dict(mpn="LTST-C170TBKT", manufacturer="Lite-On",
         description="LED blue 470nm 20mA 0603",
         category="LED", package="0603", pin_count=2,
         voltage_min=0.0, voltage_max=3.6,
         specs={"color": "Blue", "wavelength_nm": 470, "if_ma": 20}),
    dict(mpn="LTST-C170KRKT", manufacturer="Lite-On",
         description="LED red 625nm 20mA 0603",
         category="LED", package="0603", pin_count=2,
         voltage_min=0.0, voltage_max=2.2,
         specs={"color": "Red", "wavelength_nm": 625, "if_ma": 20}),

    # Inductors
    dict(mpn="MLZ2012M1R0WT000", manufacturer="TDK",
         description="Ferrite bead 1R 2A 0805",
         category="Inductor", package="0805", pin_count=2,
         voltage_min=0.0, voltage_max=50.0,
         specs={"impedance_ohm": 1, "current_a": 2.0, "type": "Ferrite Bead"}),
    dict(mpn="LQG15HN56NJ02D", manufacturer="Murata",
         description="Multilayer ceramic inductor 56nH 0402",
         category="Inductor", package="0402", pin_count=2,
         voltage_min=0.0, voltage_max=50.0,
         specs={"inductance_nh": 56, "current_a": 0.2, "type": "Ceramic"}),
]

_SUPPLIERS: list[dict] = [
    dict(name="DigiKey", region="US", shipping_days=2),
    dict(name="Mouser", region="US", shipping_days=3),
    dict(name="Arrow", region="US", shipping_days=4),
]

# Stock rows: (mpn, supplier_name, qty, unit_price, lead_days, in_stock)
_STOCK: list[tuple] = [
    # STM32F411 — make it OUT OF STOCK at all suppliers to trigger alternate flow
    ("STM32F411CEU6", "DigiKey",  0, 5.20, 56, False),
    ("STM32F411CEU6", "Mouser",   0, 5.35, 60, False),
    ("STM32F411CEU6", "Arrow",    0, 5.10, 52, False),
    # STM32F401 — in stock as an alternate
    ("STM32F401CCU6", "DigiKey",  1200, 3.80, 0, True),
    ("STM32F401CCU6", "Mouser",   800,  3.95, 0, True),
    # ESP32 — mixed availability
    ("ESP32-S3-WROOM-1", "DigiKey", 500, 3.10, 0, True),
    ("ESP32-S3-WROOM-1", "Arrow",   0,   3.50, 28, False),
    # SAMD21
    ("ATSAMD21G18A-MUT", "Mouser", 2500, 2.45, 0, True),
    
    # Additional MCUs from sample BOMs
    ("ATMEGA328P-PU", "DigiKey", 5000, 2.85, 0, True),
    ("ATMEGA328P-PU", "Mouser", 3200, 2.90, 0, True),
    ("CP2102N-A01-GQFN28", "DigiKey", 1500, 2.25, 0, True),
    
    # AMS1117-3.3 in stock
    ("AMS1117-3.3", "DigiKey",  5000, 0.28, 0, True),
    ("AMS1117-3.3", "Mouser",   3200, 0.30, 0, True),
    ("AMS1117-3.3", "Arrow",    4500, 0.27, 0, True),
    # AP2112K — out of stock (forces alternate for 3.3V LDO)
    ("AP2112K-3.3TRG1", "DigiKey", 0, 0.45, 35, False),
    ("AP2112K-3.3TRG1", "Mouser",  0, 0.48, 40, False),
    # LM1117 — in stock
    ("LM1117MP-3.3", "Arrow", 7000, 0.35, 0, True),
    # Additional regulators
    ("AMS1117-5.0", "DigiKey", 4000, 0.32, 0, True),
    ("LM2596S-3.3", "Mouser", 800, 1.85, 0, True),
    
    # LM358
    ("LM358DR", "DigiKey",  10000, 0.22, 0, True),
    ("LM358DR", "Mouser",   8000,  0.24, 0, True),
    # MCP6002
    ("MCP6002-I/SN", "Mouser", 6000, 0.32, 0, True),
    
    # Caps
    ("GRM188R71C104KA01D", "DigiKey", 50000, 0.01, 0, True),
    ("CL10B104KB8NNNC", "Mouser",     40000, 0.012, 0, True),
    ("C0603C104J4RACTU", "Arrow",      30000, 0.011, 0, True),
    # Additional caps from samples
    ("CL10B105KB8NNNC", "DigiKey", 25000, 0.018, 0, True),
    ("TAJB226K016RNJ", "Mouser", 8000, 0.45, 0, True),
    ("CC0603KRX7R9BB102", "Arrow", 15000, 0.008, 0, True),
    
    # Resistors
    ("RC0603FR-0710KL", "DigiKey", 100000, 0.005, 0, True),
    ("CRCW060310K0FKEA", "Mouser", 90000, 0.006, 0, True),
    # Additional resistors from samples
    ("CRCW06034K70FKEA", "DigiKey", 75000, 0.005, 0, True),
    ("ERJ-3EKF1001V", "Mouser", 85000, 0.004, 0, True),
    ("RC0603JR-0722RL", "Arrow", 95000, 0.003, 0, True),
    
    # Connectors
    ("USB4110-GF-A", "DigiKey", 3000, 0.85, 0, True),
    ("10118192-0001LF", "Mouser", 5000, 0.42, 0, True),
    # Additional connectors from samples
    ("S2B-PH-K-S(LF)(SN)", "DigiKey", 12000, 0.25, 0, True),
    ("61300211121", "Mouser", 8000, 0.65, 0, True),
    
    # Crystals
    ("ABM8-272-T3", "DigiKey", 8000, 0.35, 0, True),
    ("ECS-.327-12.5-34B-TR", "Mouser", 12000, 0.18, 0, True),
    ("FC-135 32.7680KA-A3", "DigiKey", 6000, 0.22, 0, True),
    
    # Additional ICs
    ("FT232RL", "DigiKey", 2000, 4.50, 0, True),
    ("FT232RL", "Mouser", 1500, 4.65, 0, True),
    
    # Transistors
    ("2N3904", "DigiKey", 15000, 0.12, 0, True),
    ("IRF520N", "Mouser", 3500, 1.25, 0, True),
    
    # Diodes
    ("BAT54S", "DigiKey", 20000, 0.18, 0, True),
    ("1N4007", "Mouser", 25000, 0.08, 0, True),
    
    # LEDs
    ("LTST-C170TBKT", "DigiKey", 18000, 0.15, 0, True),
    ("LTST-C170KRKT", "DigiKey", 19000, 0.15, 0, True),
    
    # Inductors
    ("MLZ2012M1R0WT000", "DigiKey", 12000, 0.085, 0, True),
    ("LQG15HN56NJ02D", "Mouser", 15000, 0.045, 0, True),
]


def _component_text(c: dict) -> str:
    """Build a text string for embedding from component metadata."""
    parts = [
        c["mpn"],
        c["manufacturer"],
        c["description"],
        c.get("category", ""),
        c.get("package", ""),
        f"pins={c.get('pin_count', '')}",
    ]
    if c.get("voltage_min") is not None:
        parts.append(f"voltage {c['voltage_min']}-{c['voltage_max']}V")
    for k, v in c.get("specs", {}).items():
        parts.append(f"{k}={v}")
    return " ".join(str(p) for p in parts if p)


def seed_if_empty(session: Session | None = None) -> None:
    """Insert synthetic data only if the components table is empty."""
    own_session = session is None
    if own_session:
        session = SessionLocal()
    try:
        existing = session.query(Component).count()
        if existing > 0:
            return

        print("[seed] Generating embeddings for component catalog ...")
        texts = [_component_text(c) for c in _COMPONENTS]
        vectors = embed_batch(texts)

        mpn_to_component: dict[str, Component] = {}
        for cdata, vec in zip(_COMPONENTS, vectors):
            comp = Component(
                mpn=cdata["mpn"],
                manufacturer=cdata["manufacturer"],
                description=cdata["description"],
                category=cdata.get("category", ""),
                package=cdata.get("package", ""),
                pin_count=cdata.get("pin_count", 0),
                voltage_min=cdata.get("voltage_min"),
                voltage_max=cdata.get("voltage_max"),
                specs=cdata.get("specs", {}),
                embedding=vec,
            )
            session.add(comp)
            mpn_to_component[comp.mpn] = comp

        name_to_supplier: dict[str, Supplier] = {}
        for sdata in _SUPPLIERS:
            sup = Supplier(**sdata)
            session.add(sup)
            name_to_supplier[sup.name] = sup

        session.flush()  # assign IDs

        for mpn, sname, qty, price, lead, in_stock in _STOCK:
            comp = mpn_to_component.get(mpn)
            sup = name_to_supplier.get(sname)
            if comp and sup:
                session.add(SupplierStock(
                    component_id=comp.id,
                    supplier_id=sup.id,
                    quantity_available=qty,
                    unit_price=price,
                    lead_time_days=lead,
                    is_in_stock=in_stock,
                ))

        session.commit()
        print(f"[seed] Seeded {len(mpn_to_component)} components, "
              f"{len(name_to_supplier)} suppliers, {len(_STOCK)} stock entries.")
    except Exception:
        session.rollback()
        raise
    finally:
        if own_session:
            session.close()


if __name__ == "__main__":
    from .init_db import init_db

    init_db()
    seed_if_empty()
    print("[seed] Done.")
