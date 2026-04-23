# Parametric-RC-Bridges (OpenBIM)

### Parameter-Driven IFC 4.3 Generation for Standardized RC Frame Bridges

This repository contains a Python-based engine designed to automate the generation of **IFC 4.3** models for reinforced concrete frame bridges. By translating standardized engineering plans (Emch+Berger) into parametric logic, we aim to bridge the gap between static 2D drawings and dynamic OpenBIM workflows.

---

## Project Roadmap & Execution

We are approaching this in four distinct sprints. Our primary engine is built on **Python** and **IfcOpenShell**.

### Phase 1: The Digital Blueprint (Schema & Taxonomy)

* **Parameter Register:** Instead of hard-coding dimensions, we are centralizing all drivers in `config.json`.
* **IFC 4.3 Mapping:** Mapping bridge components (Slabs, Walls, Footings) to the latest IFC 4.3 spatial hierarchy (`IfcBridge`, `IfcFacilityPart`).
* **Reinforcement Strategy:** Determining whether to model `IfcReinforcingBar` as geometry or handle reinforcement via semantic property sets.

### Phase 2: The Geometry Engine

* **API Enforcement:** All entities are created via the `ifcopenshell.api` to ensure automatic GUID generation and correct relationship linking (avoiding raw STEP strings).
* **Prismatic Logic:** Developing functions for `IfcExtrudedAreaSolid` to handle the main structural frames.
* **Placement Matrix:** Implementing parametric `IfcLocalPlacement` logic to support variable skew angles.
* **BIM Data:** Automatic attachment of `IfcMaterial` and custom Property Sets (`Pset_ConcreteElementGeneral`).

### Phase 3: Validation & Visuals

* **Headless Validation:** Automated syntax checks using `ifcopenshell.validate`.
* **Visual Debugging:** Using **Bonsai** for real-time model inspection.
* **Interoperability:** Ensuring "round-trip" compatibility with Solibri and BIMcollab.

---

## Team Contribution & Git Flow

To keep the `main` branch stable and the geometry clean, we follow a feature-based branching model:

* **`main`**: The "Golden" version. Only contains code that generates valid, schema-passed .ifc files.
* **`dev`**: The integration branch. New components are merged here first for interoperability testing.
* **`feature/[component-name]`**: Dedicated branches for specific logic (e.g., `feature/wall-logic`, `feature/pset-automation`).

### Submission Checklist

Before opening a PR (Pull Request) into `dev`:

1. [ ] Script runs without `ifcopenshell` errors.
2. [ ] Generated model passes `ifcopenshell.validate`.
3. [ ] Geometric dimensions match the parameter register.

---

## Getting Started (Team Setup)

Follow these steps to replicate the environment and verify your toolchain.

### 1. Environment Installation

Ensure you have **Python 3.10+** installed. Then, install the required BIM libraries:

```bash
pip install ifcopenshell
```

### 2. Verify Toolchain (The "Hello World")

Before running the full engine, verify your installation using the dedicated test script. This script creates a basic IFC 4.3 project to confirm that your library is correctly configured.

```bash
python src/hello_bridge.py
```

* **Success Criteria:** You should see `Toolchain Verification Success!` in your terminal and a new file in `ifc_output/hello_world_verification.ifc`.

### 3. Run the Parametric Engine

To generate the full bridge model based on the current `config.json` parameters:

```bash
python main.py
```

This will:

1. Validate parameters against **RAB-ING** standards.
2. Generate the **IFC 4.3** spatial hierarchy and 3D geometry.
3. Run an automated **Syntactic Validation** report.

### 4. Visual Inspection (Bonsai)

* Open **Blender 4.x** with the **Bonsai** add-on enabled.
* Go to the **BIM tab** and use the "Open Project" folder icon to load the generated `.ifc` files from the `ifc_output` folder.
  
  ### Current File Structure

```text
├── src/               # The core Python generator
├── ifc_output/        # Generated .ifc test files
├── docs/              # Reference drawings (Emch+Berger Standards)
├── config.json        # Central parameter file
└── main.py            # Entry point for generation
```

---

## Collaborative Notes (Open Questions)

* **Regulatory Compliance:** We are enforcing **RE-ING A 3.2** (minimum clear height of 4.70m) as a hard guardrail in our `PARAMETER_SCHEMA`.
* **Standards:** We are currently aligning with German bridge standards (DIN FB 102).
* **Haunch Complexity:** Decision pending on whether haunches are chamfered profiles or separate geometric entities.
* **Coordinate Systems:** Supporting both Local Project Coordinates and Global (UTM/ETRS89) for project alignment.

---

## 🤝 Team Contribution & Git Flow
To keep the "Golden" version of the engine stable, we follow a feature-based branching model:

*   **`main`**: The "Golden" version. Only contains code that generates valid, schema-passed .ifc files.
*   **`dev`**: The integration branch. New components are merged here first for interoperability testing.
*   **`feature/[component-name]`**: Dedicated branches for specific logic (e.g., `feature/wall-logic`).

### Submission Checklist
Before opening a PR (Pull Request) into `dev`:
1. [x] Script runs without `ifcopenshell` errors.
2. [x] Generated model passes `ifcopenshell.validate` with zero schema errors.
3. [x] Geometric dimensions match the `config.json` parameters.

---

## 🧪 Testing Protocol
We don't trust our code until it's validated:
1.  **Unit Tests:** Ensuring geometric functions return accurate dimensions.
2.  **Schema Check:** Every generated file must pass the IFC 4.3 schema validation (Phase 3.1).
3.  **Official Verification:** Final models are cross-checked using the **buildingSMART online validation service** for official compliance reports.
4.  **Visual QA:** Manual check in Solibri/Bonsai for clash detection and property accuracy.
