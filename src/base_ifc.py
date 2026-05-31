import os
import ifcopenshell
from ifcopenshell.api import run

def create_base_model(output_path):
    model = ifcopenshell.file(schema="IFC4X3")
    my_project = run("root.create_entity", model, ifc_class="IfcProject", name="OpenBIM Bridge Automation")

    # BUG FIX: Removed bare run("unit.assign_unit", model) call which created an
    # orphaned millimetre length unit alongside the metre unit, causing a duplicate
    # unit definition in the IFC file and potential scaling errors in other BIM tools.
    metre = run("unit.add_si_unit", model, unit_type="LENGTHUNIT", prefix=None)
    run("unit.assign_unit", model, units=[metre])

    # Geometric Contexts
    context = run("context.add_context", model, context_type="Model")
    body_context = run("context.add_context", model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=context
    )

    # Spatial Hierarchy
    my_site = run("root.create_entity", model, ifc_class="IfcSite", name="Bridge Site")
    run("aggregate.assign_object", model, products=[my_site], relating_object=my_project)
    my_road = run("root.create_entity", model, ifc_class="IfcRoad", name="Main_Connecting_Road")
    run("aggregate.assign_object", model, products=[my_road], relating_object=my_site)
    my_bridge = run("root.create_entity", model, ifc_class="IfcBridge", name="Main Bridge")
    run("aggregate.assign_object", model, products=[my_bridge], relating_object=my_road)

    # -------------------------------------------------------------------------
    # GRF003 FIX: Add Coordinate Reference System (CRS)
    # Using placeholder values suitable for a demo/test project.
    # For a real project, replace Eastings/Northings/OrthogonalHeight with
    # actual survey coordinates, and adjust the EPSG code to your local CRS.
    # -------------------------------------------------------------------------
    metre_unit = model.create_entity(
        "IfcSIUnit",
        UnitType="LENGTHUNIT",
        Name="METRE"
    )
    projected_crs = model.create_entity(
        "IfcProjectedCRS",
        Name="EPSG:25832",                  # ETRS89 / UTM zone 32N — common in Central Europe
        Description="Demo CRS for test project (placeholder)",
        GeodeticDatum="ETRS89",
        VerticalDatum="DHHN2016",           # German national height datum
        MapProjection="UTM",
        MapZone="32N",
        MapUnit=metre_unit
    )
    model.create_entity(
        "IfcMapConversion",
        SourceCRS=context,                  # links to the Model geometric context
        TargetCRS=projected_crs,
        Eastings=500000.0,                  # placeholder — centre of UTM zone 32N
        Northings=5500000.0,                # placeholder — roughly Central Europe
        OrthogonalHeight=0.0,               # placeholder — elevation of project origin
        XAxisAbscissa=1.0,                  # no rotation relative to CRS north
        XAxisOrdinate=0.0,
        Scale=1.0
    )
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # HEADER METADATA FIX: Populate IFC file header fields directly.
    # Uses low-level setArgument API (required for IfcOpenShell 0.8.x).
    #
    # FILE_NAME field indices:
    #   [0] name                 -> File Name in Header
    #   [1] time_stamp           -> (auto-set by IfcOpenShell)
    #   [2] author               -> Author
    #   [3] organization         -> Company Name
    #   [4] preprocessor_version -> Application Name
    #   [5] originating_system   -> Originating System
    #   [6] authorization        -> (not shown in validator)
    #
    # NOTE: IfcApplication/IfcOrganization entities are intentionally NOT added
    # here — they are "resource entities" unconnected to IfcRoot and will trigger
    # validation warning IFC106.
    # -------------------------------------------------------------------------
    h  = model.wrapped_data.header()
    fd = h.file_description_py()
    fn = h.file_name_py()

    fd.setArgumentAsAggregateOfString(0, ["ViewDefinition [IFC4X3]"])   # MVD
    fn.setArgumentAsString(0, output_path)                               # File Name in Header
    fn.setArgumentAsAggregateOfString(3, ["Emch + Berger"])              # Company Name
    fn.setArgumentAsString(4, "Blender + Bonsai")                        # Application Name
    fn.setArgumentAsString(5, "Blender 4.2.9 LTS + Bonsai")             # Originating System
    # -------------------------------------------------------------------------

    # Save the file
    model.write(output_path)
    print(f"Base scaffolding generated at: {output_path}")