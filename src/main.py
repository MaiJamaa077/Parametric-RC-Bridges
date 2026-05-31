import os
import json
import ifcopenshell

# Import generation modules
import main_deck
import base_ifc
import foundation_slab
import abutment
import wing_walls

def build_bridge():
    # Dynamically resolve paths relative to where main.py is located
    script_dir = os.path.dirname(os.path.abspath(__file__)) # This is your 'src' folder
    project_root = os.path.dirname(script_dir) # Goes one level up to 'Blue_Rhinos'
    
    # Assumes config.json is in the 'src' folder next to main.py.
    # (If you kept it in the main Blue_Rhinos folder, change 'script_dir' to 'project_root' below)
    config_path = os.path.join(script_dir, "config.json")
    
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Error: Could not find config.json at {config_path}")
        print("Please ensure config.json is in the exact same folder as main.py.")
        return

    # Setup dynamic output paths for your specific machine
    output_dir = os.path.join(project_root, "ifc_output")
    os.makedirs(output_dir, exist_ok=True)
    
    base_path = os.path.join(output_dir, "base_bridge.ifc")
    complete_path = os.path.join(output_dir, "complete_bridge.ifc")

    # base IFC is generated first
    print("Generating base model...")
    base_ifc.create_base_model(base_path)

    # Open the fresh base IFC
    model = ifcopenshell.open(base_path)

    print("\nIntegrating components...")
    
    try:
        main_deck.add_to_model(model, config)
        print("Main Deck integrated")
        foundation_slab.add_to_model(model, config)
        print("Foundation Slab integrated")

        abutment.add_to_model(model, config)
        print("Abutments integrated")

        wing_walls.add_to_model(model, config)
        print("Wing Walls integrated")

    except Exception as e:
        print("Error during integration:")
        print (str(e))
        raise

    # Save the final compiled bridge
    model.write(complete_path)
    print(f"\nSuccess! Complete bridge model saved to:\n{complete_path}")

if __name__ == "__main__":
    build_bridge()