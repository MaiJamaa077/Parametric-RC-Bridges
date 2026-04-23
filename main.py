"""
main.py — Parametric Bridge Engine (OpenBIM)
Entry point for parameter-driven IFC generation of standardised RC frame bridges 
(Rahmenbauwerke) for Emch+Berger GmbH Weimar.

Roadmap coverage:
Phase 0.2 — Environment & toolchain verification
Phase 0.3 — Parameter loading and range guardrails
Phase 1.1 — Parameter register validation
Phase 2.1 — IFC 4.3 scaffold (IfcFacility hierarchy)
Phase 3.1 — Automated syntactic validation via ifcopenshell.validate
Phase 2.6 — Bonsai/Blender integration shim
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

# ── Detect execution environment (Phase 2.6) ──────────────────────────
# Check if running inside Blender to allow live viewport updates
try:
    import bpy # type: ignore
    IN_BLENDER = True
except ModuleNotFoundError:
    IN_BLENDER = False

# ── ifcopenshell availability check (Phase 0.2) ───────────────────────
try:
    import ifcopenshell # type: ignore
    import ifcopenshell.validate # type: ignore
    IFC_AVAILABLE = True
except ModuleNotFoundError:
    IFC_AVAILABLE = False
    print("Error: ifcopenshell not found. Run 'pip install ifcopenshell'.")

# Import custom engine modules from the /src directory
try:
    from src.bridge_generator import BridgeGenerator
    from src.parameter_validator import ParameterValidator, ValidationError
except ImportError:
    print("Error: src modules not found. Ensure current directory is the project root.")

# ═══════════════════════════════════════════════════════════════════════
# PARAMETER RANGE GUARDRAILS (Phase 0.3 / 1.1)
# Constraints derived from RAB-ING and RE-ING
# ═══════════════════════════════════════════════════════════════════════
PARAMETER_SCHEMA: dict = {
    # key: (type, min, max, unit, required)
    "span_l":           (float, 2.0,  25.0,  "m",   True),
    "height_h":         (float, 4.7,  8.0,   "m",   True),  # Min 4.70m per RE-ING A 3.2
    "wall_thickness_dw":(float, 0.4,  1.2,   "m",   True),  # Standard 1.00m per RAB-ING
    "slab_top_ds":      (float, 0.3,  0.8,   "m",   True),  # Min 0.20m per ZTV-ING
    "slab_bot_df":      (float, 0.3,  1.0,   "m",   True),
    "width_b":          (float, 1.0,  20.0,  "m",   True),
    "skew_angle_deg":   (float, 0.0,  60.0,  "deg", False), # Rotation strategy
    "haunch_h":         (float, 0.0,  0.6,   "m",   False),
    "haunch_w":         (float, 0.0,  0.6,   "m",   False),
}

# ═══════════════════════════════════════════════════════════════════════
# LOGGING HELPER (Phase 0.6)
# Standardizes progress reporting for Nextcloud documentation
# ═══════════════════════════════════════════════════════════════════════
class Logger:
    def info(self, msg: str):
        print(f"[INFO] {msg}")
    def error(self, msg: str):
        print(f"[ERROR] {msg}")
    def section(self, msg: str):
        print(f"\n{'='*20} {msg} {'='*20}\n")

# ═══════════════════════════════════════════════════════════════════════
# PIPELINE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

def validate_parameters(config: dict, log: Logger) -> bool:
    """Verifies config against German regulatory ranges."""
    log.info("Phase 1.1: Validating parameters against RAB-ING schema...")
    validator = ParameterValidator(PARAMETER_SCHEMA)
    try:
        validator.validate(config)
        return True
    except ValidationError as e:
        log.error(f"Parameter Error: {e}")
        return False

def run_ifc_validation(ifc_path: str, log: Logger) -> bool:
    """Automated syntactic check against IFC 4.3 schema (Phase 3.1)."""
    log.info("Phase 3.1: Running syntactic validation...")
    
    # Open the newly generated model
    model = ifcopenshell.open(ifc_path) 
    
    # Initialize the logger to capture results (Critical for modern API)
    logger = ifcopenshell.validate.json_logger()
    
    # Execute validation against the schema (IFC4X3)
    ifcopenshell.validate.validate(model, logger)
    
    # Extract errors from the logger statements
    errors = logger.statements
    
    if len(errors) == 0:
        log.info("Milestone 3.1 Verified: Zero schema errors.")
        return True
    else:
        log.error(f"Syntactic check FAILED with {len(errors)} issues.")
        # Print details for debugging (Required for Phase 3.1 report)
        for error in errors:
            instance = error.get('instance', 'Unknown')
            message = error.get('message', 'No message available')
            log.error(f" - [{instance}]: {message}")
        return False

def run_from_bonsai(config_path: str = "config.json"):
    """Shim for interactive updates in Blender viewport."""
    log = Logger()
    log.section("BONSAI INTERACTIVE UPDATE")
    # Execute generation and refresh view (to be implemented with bpy)
    main_logic(config_path, log)

# ═══════════════════════════════════════════════════════════════════════
# MAIN LOGIC & ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════

def main_logic(config_path: str, log: Logger):
    start_time = time.time()
    
    # 1. Load Config (Phase 0.3)
    if not os.path.exists(config_path):
        log.error(f"Config file {config_path} not found.")
        return

    with open(config_path, 'r') as f:
        config = json.load(f)

    # 2. Validate Parameters (Phase 1.1)
    if not validate_parameters(config, log):
        return

    # 3. Generate IFC Model (Phase 2.1 - 2.4)
    log.info("Phase 2: Initializing Generator (IFC 4.3)...")
    generator = BridgeGenerator(config)
    model = generator.generate()
    
    output_dir = "ifc_output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    out_path = os.path.join(output_dir, "bridge_gen.ifc")
    model.write(out_path)
    log.info(f"Model saved to: {out_path}")

    # 4. Syntactic Validation (Phase 3.1)
    ifc_ok = run_ifc_validation(out_path, log)
    
    elapsed = time.time() - start_time
    log.section(f"PIPELINE COMPLETE ({elapsed:.2f}s)")
    if ifc_ok:
        log.info("Ready for round-trip testing.")

def main():
    parser = argparse.ArgumentParser(description="Parametric Bridge Engine")
    parser.add_argument("--config", default="config.json", help="Path to config")
    args = parser.parse_args()
    
    log = Logger()
    log.section("PARAMETRIC BRIDGE ENGINE (OPENBIM)")
    main_logic(args.config, log)

if __name__ == "__main__":
    if IN_BLENDER:
        run_from_bonsai()
    else:
        main()