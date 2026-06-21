import math
import uuid
import ifcopenshell
import ifcopenshell.api

def guid():
    return ifcopenshell.guid.compress(uuid.uuid1().hex)

def add_to_model(model, config):
    md_params   = config["components"]["main_deck"]["parameters"]
    fs_params   = config["components"]["foundation_slab"]["parameters"]
    abut_params = config["components"]["abutment"]["parameters"]

    Lbr           = float(md_params["Lbr"]["example_value"])
    Traff_w       = float(md_params["Traff_w"]["example_value"])
    Cape_w        = float(md_params["Cape_w"]["example_value"])
    deck_w_tot    = Traff_w + 2.0 * (Cape_w - 0.25)
    Foun_Sl_t_min = float(fs_params["Foun_Sl_t_min"]["example_value"])
    Foun_Sl_t_max = Foun_Sl_t_min + 0.10
    raw_abut_t    = float(abut_params["Abut_t"]["example_value"])
    abut_t        = raw_abut_t / 100.0 if raw_abut_t > 10 else raw_abut_t
    Abut_h        = float(abut_params["Abut_h"]["example_value"])

    Wing_L_upper  = 0.2 + 1.5 * (Abut_h + Foun_Sl_t_max) + 0.8

    # Embankment profile parameters
    H_total       = Abut_h + Foun_Sl_t_max          # = 3.6 m (height)
    bottom_start  = 0.2                              # 0.2m from abutment inner face
    bottom_end    = 1.5 * H_total                    # = 5.4 m
    top_start     = 0.2                              # thin top edge
    top_end       = Wing_L_upper - 0.8               # = 5.6 m
    depth         = deck_w_tot - 2.0 * abut_t        # = 9.6 m (Y axis)

    body_context = None
    for ctx in model.by_type("IfcGeometricRepresentationSubContext"):
        if ctx.ContextIdentifier == "Body" and ctx.is_a("IfcGeometricRepresentationSubContext"):
            body_context = ctx
            break
    if body_context is None:
        raise ValueError("Body subcontext not found!")

    bridge = model.by_type("IfcBridge")[0]

    earthworks_part = ifcopenshell.api.run(
        "root.create_entity", model,
        ifc_class="IfcBridgePart", name="Embankment"
    )
    ifcopenshell.api.run("attribute.edit_attributes", model,
        product=earthworks_part,
        attributes={"CompositionType": "ELEMENT", "UsageType": "LATERAL"})
    ifcopenshell.api.run("aggregate.assign_object", model,
        products=[earthworks_part], relating_object=bridge)

    classification = ifcopenshell.api.run(
        "classification.add_classification", model, classification="Uniclass2015")

    def make_embankment(name, x_sign):
        # Trapezoidal profile in local XZ plane:
        # Bottom: from bottom_start to bottom_end at Z=0
        # Top:    from top_start    to top_end    at Z=H_total
        # x_sign = +1 for outlet side, -1 for inlet side
        first_point = model.create_entity("IfcCartesianPoint", Coordinates=(bottom_start, 0.0))
        points = [
            first_point,
            model.create_entity("IfcCartesianPoint", Coordinates=(bottom_end,  0.0)),
            model.create_entity("IfcCartesianPoint", Coordinates=(top_end,     H_total)),
            model.create_entity("IfcCartesianPoint", Coordinates=(top_start,   H_total)),
            first_point,
        ]
        polyline = model.create_entity("IfcPolyline", Points=points)
        profile  = model.create_entity("IfcArbitraryClosedProfileDef",
            ProfileType="AREA", OuterCurve=polyline)

        extrusion_dir = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))

        # Body placement: profile drawn in XZ, extruded along Y (depth)
        body_pt  = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
        body_z   = model.create_entity("IfcDirection", DirectionRatios=(0.0, 1.0, 0.0))   # extrusion axis = Y
        body_x   = model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
        body_placement = model.create_entity("IfcAxis2Placement3D",
            Location=body_pt, Axis=body_z, RefDirection=body_x)

        solid = model.create_entity("IfcExtrudedAreaSolid",
            SweptArea=profile,
            Position=body_placement,
            ExtrudedDirection=extrusion_dir,
            Depth=depth)

        shape = model.create_entity("IfcShapeRepresentation",
            ContextOfItems=body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid])

        product_shape = model.create_entity("IfcProductDefinitionShape",
            Representations=[shape])

        # Placement:
        # X = abutment outer face (±(Lbr/2 + abut_t)), mirrored for inlet/outlet
        # Y = -deck_w_tot/2 + abut_t (start of depth)
        # Z = 0 (top of foundation slab)
        x_pos = x_sign * (Lbr / 2.0 + abut_t)
        y_pos = -deck_w_tot / 2.0 + abut_t

        angle        = 0.0 if x_sign > 0 else math.pi   # flip for inlet side
        point        = model.create_entity("IfcCartesianPoint",
            Coordinates=(float(x_pos), float(y_pos), 0.0))
        ref_dir      = model.create_entity("IfcDirection",
            DirectionRatios=(float(math.cos(angle)), float(math.sin(angle)), 0.0))
        axis         = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
        placement_3d = model.create_entity("IfcAxis2Placement3D",
            Location=point, Axis=axis, RefDirection=ref_dir)
        local_placement = model.create_entity("IfcLocalPlacement",
            RelativePlacement=placement_3d)

        embankment = model.create_entity(
            "IfcEarthworksFill",
            GlobalId=guid(),
            Name=name,
            ObjectPlacement=local_placement,
            Representation=product_shape
        )

        pset = ifcopenshell.api.run("pset.add_pset", model,
            product=embankment, name="Pset_EarthworksFillCommon")
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset,
            properties={"IsExternal": True})

        ifcopenshell.api.run("classification.add_reference", model,
            products=[embankment],
            classification=classification,
            identification="Ss_25_16_95",
            name="Bridge Embankments")

        return embankment

    embankments = [
        make_embankment("Inlet Embankment",  -1),
        make_embankment("Outlet Embankment", +1),
    ]

    model.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=guid(),
        RelatingStructure=earthworks_part,
        RelatedElements=embankments
    )