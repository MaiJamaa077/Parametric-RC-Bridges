import uuid
import math
import ifcopenshell
import ifcopenshell.api

def guid():
    return ifcopenshell.guid.compress(uuid.uuid1().hex)

def add_to_model(model, config):
    md_params   = config["components"]["main_deck"]["parameters"]
    abut_params = config["components"]["abutment"]["parameters"]

    Lbr        = float(md_params["Lbr"]["example_value"])
    deck_t     = float(md_params["deck_t"]["example_value"])
    deck_i     = float(str(md_params["deck_i"]["example_value"]).strip('%')) / 100.0
    Traff_w    = float(md_params["Traff_w"]["example_value"])
    Cape_w     = float(md_params["Cape_w"]["example_value"])
    deck_w_tot = Traff_w + 2.0 * (Cape_w - 0.25)
    deck_t_max = deck_t + 0.5 * Traff_w * deck_i
    abut_h     = float(abut_params["Abut_h"]["example_value"])
    raw_abut_t = float(abut_params["Abut_t"]["example_value"])
    abut_t     = raw_abut_t / 100.0 if raw_abut_t > 10 else raw_abut_t
    deck_length = Lbr + (2 * abut_t)

    body_context = None
    for ctx in model.by_type("IfcGeometricRepresentationSubContext"):
        if ctx.ContextIdentifier == "Body" and ctx.is_a("IfcGeometricRepresentationSubContext"):
            body_context = ctx
            break
    if body_context is None:
        raise ValueError("Body subcontext not found!")
    print(f"main_deck using context: #{body_context.id()} | {body_context.is_a()} | {body_context.ContextIdentifier}")

    bridge = model.by_type("IfcBridge")[0]

    superstructure = model.create_entity(
        "IfcBridgePart",
        GlobalId=guid(),
        Name="Superstructure",
        PredefinedType="SUPERSTRUCTURE"
    )
    ifcopenshell.api.run("attribute.edit_attributes", model, product=superstructure, attributes={"CompositionType": "ELEMENT", "UsageType": "LONGITUDINAL"})
    model.create_entity("IfcRelAggregates", GlobalId=guid(), RelatingObject=bridge, RelatedObjects=[superstructure])

    concrete = ifcopenshell.api.run("material.add_material", model, name="C30/37")
    crown_h  = deck_t_max - deck_t

    first_point = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, crown_h))
    points = [
        first_point,
        model.create_entity("IfcCartesianPoint", Coordinates=( deck_w_tot/2.0,  0.0)),
        model.create_entity("IfcCartesianPoint", Coordinates=( deck_w_tot/2.0, -deck_t)),
        model.create_entity("IfcCartesianPoint", Coordinates=(-deck_w_tot/2.0, -deck_t)),
        model.create_entity("IfcCartesianPoint", Coordinates=(-deck_w_tot/2.0,  0.0)),
        first_point,
    ]

    polyline       = model.create_entity("IfcPolyline", Points=points)
    profile        = model.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=polyline)
    extrusion_dir  = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    body_pt        = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    body_z         = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    body_x         = model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    body_placement = model.create_entity("IfcAxis2Placement3D", Location=body_pt, Axis=body_z, RefDirection=body_x)

    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=body_placement,
        ExtrudedDirection=extrusion_dir,
        Depth=deck_length
    )
    shape = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_context,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid]
    )
    print(f"main_deck shape rep: #{shape.id()} | ContextOfItems=#{shape.ContextOfItems.id()} | Identifier={shape.RepresentationIdentifier}")

    product_shape    = model.create_entity("IfcProductDefinitionShape", Representations=[shape])
    obj_pt           = model.create_entity("IfcCartesianPoint", Coordinates=(-deck_length/2.0, 0.0, abut_h + deck_t))
    obj_z            = model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    obj_x            = model.create_entity("IfcDirection", DirectionRatios=(0.0, 1.0, 0.0))
    obj_placement_3d = model.create_entity("IfcAxis2Placement3D", Location=obj_pt, Axis=obj_z, RefDirection=obj_x)
    obj_placement    = model.create_entity("IfcLocalPlacement", RelativePlacement=obj_placement_3d)

    deck = model.create_entity(
        "IfcSlab",
        GlobalId=guid(),
        Name="Main Deck",
        PredefinedType="ROOF",
        ObjectPlacement=obj_placement,
        Representation=product_shape
    )

    ifcopenshell.api.run("material.assign_material", model, products=[deck], type="IfcMaterial", material=concrete)
    model.create_entity("IfcRelContainedInSpatialStructure", GlobalId=guid(), RelatingStructure=superstructure, RelatedElements=[deck])

    pset = ifcopenshell.api.run("pset.add_pset", model, product=deck, name="Pset_SlabCommon")
    ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties={"LoadBearing": True, "IsExternal": True})
    qto = ifcopenshell.api.run("pset.add_qto", model, product=deck, name="Qto_SlabBaseQuantities")
    ifcopenshell.api.run("pset.edit_qto", model, qto=qto, properties={
        "Length": float(deck_length),
        "Width": float(deck_w_tot),
        "GrossVolume": float(deck_length * deck_w_tot * deck_t),
    })

    classification = ifcopenshell.api.run("classification.add_classification", model, classification="Uniclass2015")
    ifcopenshell.api.run("classification.add_reference", model,
        products=[deck],
        classification=classification,
        identification="Ss_25_16_95",
        name="Bridge Decks")