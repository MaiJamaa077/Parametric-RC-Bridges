import math
import uuid
import ifcopenshell
import ifcopenshell.api

def guid():
    return ifcopenshell.guid.compress(uuid.uuid1().hex)

def add_to_model(model, config):
    ww_params      = config["components"]["wing_walls"]["parameters"]
    md_params      = config["components"]["main_deck"]["parameters"]
    abut_params    = config["components"]["abutment"]["parameters"]
    fs_params      = config["components"]["foundation_slab"]["parameters"]

    Wing_i         = float(ww_params["Wing_i"]["example_value"])
    Traff_w        = float(md_params["Traff_w"]["example_value"])
    Cape_w         = float(md_params["Cape_w"]["example_value"])
    deck_t         = float(md_params["deck_t"]["example_value"])
    cw             = Traff_w + 2.0 * (Cape_w - 0.25)
    culvert_length = float(md_params["Lbr"]["example_value"])
    raw_abut_t     = float(abut_params["Abut_t"]["example_value"])
    abut_t         = raw_abut_t / 100.0 if raw_abut_t > 10 else raw_abut_t
    Abut_h         = float(abut_params["Abut_h"]["example_value"])
    Foun_Sl_t_max  = float(fs_params["Foun_Sl_t_min"]["example_value"]) + 0.10

    Wing_h_total   = Abut_h + deck_t
    Wing_h_upper   = 0.2
    Wing_t         = float(ww_params["Wing_t"]["example_value"])
    Wing_L_upper   = 0.2 + 1.5 * (Abut_h + Foun_Sl_t_max) + 0.8
    Wing_L_lower   = 0.2 + 1.5 * (Abut_h + Foun_Sl_t_max) - Foun_Sl_t_max - (Abut_h - Foun_Sl_t_max - 0.2) / math.tan(math.radians(60))

    body_context = None
    for ctx in model.by_type("IfcGeometricRepresentationSubContext"):
        if ctx.ContextIdentifier == "Body" and ctx.is_a("IfcGeometricRepresentationSubContext"):
            body_context = ctx
            break
    if body_context is None:
        raise ValueError("Body subcontext not found!")

    bridge = model.by_type("IfcBridge")[0]

    concrete = ifcopenshell.api.run("material.add_material", model, name="C30/37")

    wing_wall_part = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBridgePart", name="Wing Walls")
    ifcopenshell.api.run("attribute.edit_attributes", model, product=wing_wall_part, attributes={"CompositionType": "ELEMENT", "UsageType": "LATERAL"})
    ifcopenshell.api.run("aggregate.assign_object", model, products=[wing_wall_part], relating_object=bridge)

    classification = ifcopenshell.api.run("classification.add_classification", model, classification="Uniclass2015")

    def local_placement(x, y, z, rotation_deg):
        angle        = math.radians(rotation_deg)
        point        = model.create_entity("IfcCartesianPoint", Coordinates=(float(x), float(y), float(z)))
        ref_dir      = model.create_entity("IfcDirection", DirectionRatios=(float(math.cos(angle)), float(math.sin(angle)), 0.0))
        axis         = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
        placement_3d = model.create_entity("IfcAxis2Placement3D", Location=point, Axis=axis, RefDirection=ref_dir)
        return model.create_entity("IfcLocalPlacement", RelativePlacement=placement_3d)

    def wall_body_placement():
        point   = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
        axis    = model.create_entity("IfcDirection", DirectionRatios=(0.0, -1.0, 0.0))
        ref_dir = model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
        return model.create_entity("IfcAxis2Placement3D", Location=point, Axis=axis, RefDirection=ref_dir)

    def create_trapezoid_wing_wall(name, x, y, z, rotation_deg):
        first_point = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0))
        points = [
            first_point,
            model.create_entity("IfcCartesianPoint", Coordinates=(Wing_L_lower, 0.0)),
            model.create_entity("IfcCartesianPoint", Coordinates=(Wing_L_upper, Wing_h_total - Wing_h_upper)),
            model.create_entity("IfcCartesianPoint", Coordinates=(Wing_L_upper, Wing_h_total)),
            model.create_entity("IfcCartesianPoint", Coordinates=(0.0,          Wing_h_total)),
            first_point,
        ]
        polyline = model.create_entity("IfcPolyline", Points=points)
        profile  = model.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=polyline)
        extrusion_direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
        solid = model.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=profile,
            Position=wall_body_placement(),
            ExtrudedDirection=extrusion_direction,
            Depth=Wing_t
        )
        shape = model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid]
        )
        product_shape = model.create_entity("IfcProductDefinitionShape", Representations=[shape])
        wall = model.create_entity(
            "IfcWall",
            GlobalId=guid(),
            Name=name,
            ObjectPlacement=local_placement(x, y, z, rotation_deg),
            Representation=product_shape
        )
        ifcopenshell.api.run("material.assign_material", model, products=[wall], type="IfcMaterial", material=concrete)
        pset = ifcopenshell.api.run("pset.add_pset", model, product=wall, name="Pset_WallCommon")
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties={"LoadBearing": True, "IsExternal": True})
        qto = ifcopenshell.api.run("pset.add_qto", model, product=wall, name="Qto_WallBaseQuantities")
        ifcopenshell.api.run("pset.edit_qto", model, qto=qto, properties={"Length": float(Wing_L_upper), "Height": float(Wing_h_total), "Width": float(Wing_t)})
        ifcopenshell.api.run("classification.add_reference", model,
            products=[wall],
            classification=classification,
            identification="Ss_25_16_16",
            name="Bridge Wing Walls")
        return wall

    x_inlet  = -culvert_length / 2.0 - abut_t
    x_outlet =  culvert_length / 2.0 + abut_t

    wing_rad = math.radians(Wing_i)
    # Miter offset so the inner connecting face stays coplanar with the abutment
    # outer face at all angles. At Wing_i=0: miter=0, identical to original.
    miter = Wing_t * math.tan(wing_rad) if Wing_i != 0 else 0.0

    def create_trapezoid_wing_wall(name, x, y, z, rotation_deg):
        p_inner_bottom = model.create_entity("IfcCartesianPoint", Coordinates=(miter, 0.0))
        p_inner_top    = model.create_entity("IfcCartesianPoint", Coordinates=(miter, Wing_h_total))
        points = [
            p_inner_bottom,
            model.create_entity("IfcCartesianPoint", Coordinates=(Wing_L_lower + miter, 0.0)),
            model.create_entity("IfcCartesianPoint", Coordinates=(Wing_L_upper + miter, Wing_h_total - Wing_h_upper)),
            model.create_entity("IfcCartesianPoint", Coordinates=(Wing_L_upper + miter, Wing_h_total)),
            p_inner_top,
            p_inner_bottom,
        ]
        polyline = model.create_entity("IfcPolyline", Points=points)
        profile  = model.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=polyline)
        extrusion_direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
        solid = model.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=profile,
            Position=wall_body_placement(),
            ExtrudedDirection=extrusion_direction,
            Depth=Wing_t
        )
        shape = model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid]
        )
        product_shape = model.create_entity("IfcProductDefinitionShape", Representations=[shape])
        wall = model.create_entity(
            "IfcWall",
            GlobalId=guid(),
            Name=name,
            ObjectPlacement=local_placement(x, y, z, rotation_deg),
            Representation=product_shape
        )
        ifcopenshell.api.run("material.assign_material", model, products=[wall], type="IfcMaterial", material=concrete)
        pset = ifcopenshell.api.run("pset.add_pset", model, product=wall, name="Pset_WallCommon")
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties={"LoadBearing": True, "IsExternal": True})
        qto = ifcopenshell.api.run("pset.add_qto", model, product=wall, name="Qto_WallBaseQuantities")
        ifcopenshell.api.run("pset.edit_qto", model, qto=qto, properties={"Length": float(Wing_L_upper), "Height": float(Wing_h_total), "Width": float(Wing_t)})
        ifcopenshell.api.run("classification.add_reference", model,
            products=[wall],
            classification=classification,
            identification="Ss_25_16_16",
            name="Bridge Wing Walls")
        return wall

    walls = [
        create_trapezoid_wing_wall("Inlet Left Wing Wall",   x_inlet,  -(cw/2),         0.0, 180.0 - Wing_i),
        create_trapezoid_wing_wall("Inlet Right Wing Wall",  x_inlet,   (cw/2 - Wing_t), 0.0, 180.0 + Wing_i),
        create_trapezoid_wing_wall("Outlet Left Wing Wall",  x_outlet, -(cw/2 - Wing_t), 0.0,   0.0 + Wing_i),
        create_trapezoid_wing_wall("Outlet Right Wing Wall", x_outlet,  (cw/2),          0.0,   0.0 - Wing_i),
    ]

    model.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=guid(),
        RelatingStructure=wing_wall_part,
        RelatedElements=walls
    )