import ifcopenshell
import ifcopenshell.api

def add_to_model(model, config):
    context = None
    for ctx in model.by_type("IfcGeometricRepresentationSubContext"):
        if ctx.ContextIdentifier == "Body" and ctx.is_a("IfcGeometricRepresentationSubContext"):
            context = ctx
            break
    if context is None:
        raise ValueError("Body subcontext not found!")

    bridge = model.by_type("IfcBridge")[0]
    substructure = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBridgePart", name="Substructure", predefined_type="SUBSTRUCTURE")
    ifcopenshell.api.run("attribute.edit_attributes", model, product=substructure, attributes={"CompositionType": "ELEMENT", "UsageType": "LATERAL"})
    ifcopenshell.api.run("aggregate.assign_object", model, products=[substructure], relating_object=bridge)
    concrete_material = ifcopenshell.api.run("material.add_material", model, name="C30/37")
    main_deck = config["components"]["main_deck"]["parameters"]
    abutment  = config["components"]["abutment"]["parameters"]
    Traff_w    = main_deck["Traff_w"]["example_value"]
    Cape_w     = main_deck["Cape_w"]["example_value"]
    Lbr        = main_deck["Lbr"]["example_value"]
    Abut_h     = abutment["Abut_h"]["example_value"]
    raw_abut_t = abutment["Abut_t"]["example_value"]
    Abut_t     = raw_abut_t / 100.0 if raw_abut_t > 10 else raw_abut_t
    deck_w_tot = Traff_w + 2 * (Cape_w - 0.25)
    classification = ifcopenshell.api.run("classification.add_classification",
        model, classification="Uniclass2015")

    def _create_wall(name, thickness, height, width, matrix):
        wall = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name=name, predefined_type="SOLIDWALL")
        representation = ifcopenshell.api.run("geometry.add_wall_representation", model, context=context, length=width, height=height, thickness=thickness)
        ifcopenshell.api.run("geometry.assign_representation", model, product=wall, representation=representation)
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=wall, matrix=matrix)
        ifcopenshell.api.run("material.assign_material", model, products=[wall], type="IfcMaterial", material=concrete_material)
        ifcopenshell.api.run("spatial.assign_container", model, products=[wall], relating_structure=substructure)
        pset = ifcopenshell.api.run("pset.add_pset", model, product=wall, name="Pset_WallCommon")
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties={"LoadBearing": True, "IsExternal": True})
        qto = ifcopenshell.api.run("pset.add_qto", model, product=wall, name="Qto_WallBaseQuantities")
        ifcopenshell.api.run("pset.edit_qto", model, qto=qto, properties={"Length": float(width), "Height": float(height), "Width": float(thickness)})
        ifcopenshell.api.run("classification.add_reference", model,
            products=[wall],
            classification=classification,
            identification="Ss_25_16_33",
            name="Bridge Abutments")

    def get_matrix(x_pos, y_pos):
        return [
            [0.0, -1.0, 0.0, x_pos],
            [1.0,  0.0, 0.0, y_pos],
            [0.0,  0.0, 1.0, 0.0],
            [0.0,  0.0, 0.0, 1.0]
        ]

    x_left  = -Lbr / 2.0
    x_right =  Lbr / 2.0 + Abut_t
    y_start = -deck_w_tot / 2.0
    _create_wall("Left Abutment",  Abut_t, Abut_h, deck_w_tot, get_matrix(x_left,  y_start))
    _create_wall("Right Abutment", Abut_t, Abut_h, deck_w_tot, get_matrix(x_right, y_start))