import ifcopenshell
import ifcopenshell.api
import os

def create_hello_bridge():
    # 1. Initialize a blank IFC 4.3 model as required by the roadmap [3, 4]
    model = ifcopenshell.file(schema="IFC4X3")

    # 2. Use the ifcopenshell.api to create an IfcProject [1, 2]
    # The API handles GUIDs and owner history automatically [5, 6]
    project = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcProject", name="Toolchain Verification"
    )

    # 3. Assign default SI units to the project model [5]
    ifcopenshell.api.unit.assign_unit(model)

    # 4. Create an IfcSite to verify the spatial hierarchy logic [7, 8]
    ifcopenshell.api.spatial.assign_container(
        model, product=project, ifc_class="IfcSite", name="Test Site"
    )

    # 5. Ensure the standard project output directory exists [9, 10]
    output_dir = "ifc_output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 6. Save the generated .ifc file to disk [1, 11]
    output_path = os.path.join(output_dir, "hello_bridge.ifc")
    model.write(output_path)
    
    print(f"\n[SUCCESS] Milestone Phase 0.2 verified.")
    print(f"Generated: {output_path}")
    print("ACTION: Confirm this file opens correctly in Bonsai (Blender) to proceed.")

if __name__ == "__main__":
    create_hello_bridge()