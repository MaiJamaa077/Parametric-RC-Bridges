import math
import ifcopenshell
import ifcopenshell.api
from ifcopenshell.guid import new as new_guid

def add_to_model(model, config):
    md_params   = config["components"]["main_deck"]["parameters"]
    fs_params   = config["components"]["foundation_slab"]["parameters"]
    abut_params = config["components"]["abutment"]["parameters"]

    Lbr               = float(md_params["Lbr"]["example_value"])
    Traff_w           = float(md_params["Traff_w"]["example_value"])
    Cape_w            = float(md_params["Cape_w"]["example_value"])
    deck_w_tot        = Traff_w + 2.0 * (Cape_w - 0.25)
    Foun_Sl_t_min_m   = float(fs_params["Foun_Sl_t_min"]["example_value"])
    Foun_Sl_t_max     = Foun_Sl_t_min_m + 0.10
    raw_abut_t        = float(abut_params["Abut_t"]["example_value"])
    abut_t            = raw_abut_t / 100.0 if raw_abut_t > 10 else raw_abut_t
    Abut_h            = float(abut_params["Abut_h"]["example_value"])

    ww_params     = config["components"]["wing_walls"]["parameters"]
    Wing_i        = float(ww_params["Wing_i"]["example_value"])
    Wing_t        = float(ww_params["Wing_t"]["example_value"])
    wing_rad      = math.radians(abs(Wing_i))
    cos_w         = math.cos(wing_rad)
    sin_w         = math.sin(wing_rad)
    Wing_L_upper  = 0.2 + 1.5 * (Abut_h + Foun_Sl_t_max) + 0.8
    Wing_L_lower  = 0.2 + 1.5 * (Abut_h + Foun_Sl_t_max) - Foun_Sl_t_max - (Abut_h - Foun_Sl_t_max - 0.2) / math.tan(math.radians(60))

    # Original structural length — unchanged
    slab_span     = Lbr + 2.0 * abut_t + 2.0 * Wing_L_lower + 0.4

    # Original structural width as base, angle-responsive delta added on top:
    # At Wing_i=0°: sin=0, cos=1 → delta=0, slab_wide stays deck_w_tot
    # As angle increases: sin grows → foundation widens to support angled wing walls
    slab_wide     = deck_w_tot + 2 * (sin_w * Wing_L_upper + (cos_w - 1) * Wing_t / 2)
    slab_thickness = Foun_Sl_t_max                                      # Z:  0.6  m

    bridge       = model.by_type("IfcBridge")[0]
    body_context = None
    for ctx in model.by_type("IfcGeometricRepresentationSubContext"):
        if ctx.ContextIdentifier == "Body" and ctx.is_a("IfcGeometricRepresentationSubContext"):
            body_context = ctx
            break
    if body_context is None:
        raise ValueError("Body subcontext not found!")

    concrete = ifcopenshell.api.run("material.add_material", model, name="C30/37")

    substructure = None
    for part in model.by_type("IfcBridgePart"):
        if part.Name == "Substructure":
            substructure = part
            break
    if substructure is None:
        substructure = ifcopenshell.api.run(
            "root.create_entity", model,
            ifc_class="IfcBridgePart", name="Substructure",
            predefined_type="SUBSTRUCTURE"
        )
        ifcopenshell.api.run("attribute.edit_attributes", model,
            product=substructure,
            attributes={"CompositionType": "ELEMENT", "UsageType": "LATERAL"})
        ifcopenshell.api.run(
            "aggregate.assign_object", model,
            products=[substructure], relating_object=bridge
        )

    # X = slab_span (longitudinal = 13.86 m)
    # Y = slab_wide (transverse   = 11.6  m)
    vertices = [
        (-slab_span/2, -slab_wide/2, -slab_thickness),
        ( slab_span/2, -slab_wide/2, -slab_thickness),
        ( slab_span/2,  slab_wide/2, -slab_thickness),
        (-slab_span/2,  slab_wide/2, -slab_thickness),
        (-slab_span/2, -slab_wide/2,  0.0),
        ( slab_span/2, -slab_wide/2,  0.0),
        ( slab_span/2,  slab_wide/2,  0.0),
        (-slab_span/2,  slab_wide/2,  0.0),
    ]

    faces = [
        [0, 3, 2, 1],
        [4, 5, 6, 7],
        [0, 1, 5, 4],
        [1, 2, 6, 5],
        [2, 3, 7, 6],
        [3, 0, 4, 7],
    ]

    def create_face(model, point_entities):
        loop  = model.create_entity("IfcPolyLoop", Polygon=point_entities)
        bound = model.create_entity("IfcFaceOuterBound", Bound=loop, Orientation=True)
        return model.create_entity("IfcFace", Bounds=[bound])

    ifc_pts   = [model.create_entity("IfcCartesianPoint", Coordinates=v) for v in vertices]
    ifc_faces = [create_face(model, [ifc_pts[i] for i in f]) for f in faces]
    shell     = model.create_entity("IfcClosedShell", CfsFaces=ifc_faces)
    brep      = model.create_entity("IfcFacetedBrep", Outer=shell)

    shape_rep     = model.create_entity("IfcShapeRepresentation", ContextOfItems=body_context, RepresentationIdentifier="Body", RepresentationType="Brep", Items=[brep])
    product_shape = model.create_entity("IfcProductDefinitionShape", Representations=[shape_rep])

    point           = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    axis_z          = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    axis_x          = model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    placement_3d    = model.create_entity("IfcAxis2Placement3D", Location=point, Axis=axis_z, RefDirection=axis_x)
    local_placement = model.create_entity("IfcLocalPlacement", RelativePlacement=placement_3d)

    foundation_slab = model.create_entity(
        "IfcFooting",
        GlobalId=new_guid(),
        Name="Foundation Slab",
        PredefinedType="PAD_FOOTING",
        ObjectPlacement=local_placement,
        Representation=product_shape
    )

    ifcopenshell.api.run("material.assign_material", model, products=[foundation_slab], type="IfcMaterial", material=concrete)

    model.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=new_guid(),
        RelatingStructure=substructure,
        RelatedElements=[foundation_slab]
    )

    pset = ifcopenshell.api.run("pset.add_pset", model, product=foundation_slab, name="Pset_FootingCommon")
    ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties={"LoadBearing": True})

    qto = ifcopenshell.api.run("pset.add_qto", model, product=foundation_slab, name="Qto_FootingBaseQuantities")
    ifcopenshell.api.run("pset.edit_qto", model, qto=qto, properties={
        "Length": float(slab_span),
        "Width":  float(slab_wide),
        "GrossVolume": float(slab_span * slab_wide * slab_thickness),
    })

    classification = ifcopenshell.api.run("classification.add_classification",
        model, classification="Uniclass2015")
    ifcopenshell.api.run("classification.add_reference", model,
        products=[foundation_slab],
        classification=classification,
        identification="Ss_25_16_30",
        name="Bridge Foundations")