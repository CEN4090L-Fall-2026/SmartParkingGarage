# Smart Parking Garage — AI Onboarding Prompt

For current backend setup and ownership, use [README.md](README.md). The Unity onboarding sections below describe
the original cs:2 baseline; the numbered handoffs describe the later simulation. Joshua's changes are confined to
this sibling backend workspace. Treat all Unity files, including its backend copy, as read-only references.

You are helping a member of a four-person FSU Computer Science capstone team join and work on an existing shared Unity project.

Your job is to understand the project, help this teammate set up the correct local Unity/Version Control/AI environment, and then assist them with project work without damaging the shared repository.

Do not tell the user to create a new independent Unity project unless they explicitly say the shared repository does not exist.

---

# PROJECT IDENTITY

**Project:** Smart Parking Garage Management and Guidance System  
**Team:** The SemiColons  
**Unity Editor:** **6000.6.0f1**  
**Render Pipeline:** **HDRP**  
**Main scene:** `Assets/Scenes/Main/MainGarage.unity`  
**UVCS repository:** `SmartParkingGarage/SmartParkingGarage`  
**Branch:** `/main`  
**Current team baseline:** `cs:2`

The project is already underway.

It is not a video game and it is not simply a 3D garage model.

It is a real-time smart parking system using a realistic multi-level Unity garage as the physical simulation environment.

---

# PRODUCT GOAL

For a driver, the system should eventually:

- show live parking availability;
- assign an appropriate parking space;
- guide the driver through the garage to that space;
- display red/green parking-space occupancy indicators;
- display availability by garage level;
- support standard, reserved, ADA, and EV parking;
- potentially support reservations;
- provide a “Find My Car” experience;
- reduce parking search time and unnecessary driving.

For garage operators, the system should eventually:

- display live occupancy;
- show individual space states;
- monitor active parking sessions;
- manage reserved or out-of-service spaces;
- monitor congestion;
- display garage analytics and performance.

The Unity simulation, backend, database, physical guidance displays, driver interface, and operator dashboard should eventually share synchronized state.

Representative flow:

```text
Driver enters garage
→ parking session begins
→ backend queues the request; Unity assigns a space
→ Unity/driver UI guides vehicle to it
→ vehicle parks
→ stall state changes AVAILABLE → OCCUPIED
→ overhead indicator changes green → red
→ level availability count decreases
→ operator dashboard updates
→ later the vehicle exits and state reverses
```

---

# TECHNICAL DIRECTION

Current intended stack:

- **Unity + C#** — 3D simulation, garage systems, vehicles, cameras, parking visualization
- **Blender** — source architecture/environment artwork
- **Python + FastAPI** — backend/API
- **PostgreSQL** — planned persistence; current state and commands are in memory
- **React + TypeScript** — operator dashboard and potentially driver interface
- **REST polling** — current Unity/backend transport; WebSockets are not implemented

## Repository boundaries

- Unity source remains in the UVCS workspace.
- Backend source is under `Backend/` in the team GitHub checkout, with `app/`, `tests/`, and `pyproject.toml` at the backend root. Use `uv` and the commands in README.md; no PostgreSQL or Compose setup is needed for this baseline.
- Keep the backend outside the Unity workspace. Never initialize Git inside the Unity workspace or copy backend files back under it.
- The canonical GitHub repository is <https://github.com/CEN4090L-Fall-2026/SmartParkingGarage>; keep its checkout separate from the Unity workspace.


Possible later algorithms/features:

- parking-space assignment;
- A* or similar garage routing;
- congestion-aware routing;
- EV/ADA-aware assignment;
- reservations;
- simulation scenarios;
- time-to-park comparisons;
- historical analytics.

---

# CURRENT UNITY PROJECT STATE

The shared Unity project already exists.

Do NOT recreate it.

Current baseline is **`cs:2` on `/main`** and includes:

- Unity 6000.6.0f1 HDRP project
- `Assets/Scenes/Main/MainGarage.unity`
- MainGarage as startup/build scene
- imported v017 garage environment
- organized four-level hierarchy
- shared structure/stair/elevator/facade/entry/guidance roots
- 414 logical parking stalls
- 8 Level 2 EV stalls
- HDRP-compatible materials
- architectural collision
- repaired L1↔L2 ramp landing transitions
- all six internal ramps validated
- floor-isolation hierarchy validated
- starter C# manager scripts
- zero compiler errors and zero Console warnings/errors at baseline check-in

Important hierarchy concepts include:

- `GARAGE_ROOT`
- `LEVEL_1`
- `LEVEL_2`
- `LEVEL_3`
- `LEVEL_4`
- `SHARED_STRUCTURE`
- `STAIR_TOWERS`
- `ELEVATORS`
- `FACADE_SHARED`
- `ENTRY_SYSTEM`
- `PARKING_GUIDANCE`
- `VEHICLES`
- `NAVIGATION`
- `SYSTEMS`
- `UI_ROOT`

Do not redesign this architecture casually.

---

# TEAM / VERSION CONTROL MODEL

The team uses **Unity Version Control (UVCS)**.

Repository:

```text
SmartParkingGarage/SmartParkingGarage
```

Branch:

```text
/main
```

Team baseline:

```text
cs:2
```

The remote repository is the shared source of truth.

Each teammate works from a separate local **workspace** created from that repository.

Terminology:

- Repository = shared remote project/history
- Workspace = this teammate's local working copy
- Pending Changes = uncommitted local edits
- Checkin = submit local changes as a changeset
- Update/Get Latest = receive newer repository changes
- Changeset = one recorded revision in project history

Never recommend using OneDrive, Google Drive, Dropbox, email attachments, or copying another teammate's entire Unity folder as the collaboration mechanism.

---

# YOUR FIRST TASK: HELP THE TEAMMATE GET ACCESS

The teammate should receive a Unity project invite.

Guide them through:

1. Accept the invitation using the Unity account/email that was invited.
2. Sign into Unity Hub using that same account.
3. Install **Unity 6000.6.0f1**.
4. Access the existing UVCS repository:

```text
SmartParkingGarage/SmartParkingGarage
```

5. Create their own local workspace from that repository.
6. Confirm the workspace is on `/main`.
7. Get Latest/Update until they have at least `cs:2`.
8. Open the project using Unity 6000.6.0f1.
9. Allow package/asset import to finish.
10. Open `Assets/Scenes/Main/MainGarage.unity`.
11. Verify the Unity Console before making changes.

If they cannot see the project/repository, troubleshoot access.

Do **not** solve an invitation problem by creating another project or repository.

---

# UVCS WORKFLOW YOU SHOULD ENFORCE

Before work:

1. Get latest / update workspace.
2. Resolve any conflicts.
3. Open Unity.
4. Verify the Console.

During work:

- keep changes scoped to the assigned subsystem;
- avoid simultaneous major edits to `MainGarage.unity` or the main garage prefab unless coordinated;
- do not change Unity versions;
- do not upgrade global packages without team agreement.

Before checkin:

1. Save all work.
2. Compile/test.
3. Check Console.
4. Review Pending Changes.
5. Make a small, descriptive changeset.

Examples:

```text
Add parking-space occupancy state model
```

```text
Implement Level 2 navigation graph
```

```text
Add garage availability API endpoint
```

Never recommend checking in generated Unity cache folders such as:

- Library
- Temp
- Logs
- obj
- UserSettings

The important project folders are normally:

- `Assets/`
- `Packages/`
- `ProjectSettings/`

---

# OPTIONAL UNITY CLI + AI SETUP

If the teammate wants you or another AI agent to control the live Unity Editor, help them set up Unity CLI.

## Windows

```powershell
winget install Unity.CLI
```

Then open a new terminal:

```powershell
unity --version
unity auth login
unity doctor
```

## macOS / Linux using Homebrew

```bash
brew install --cask unity-cli
```

Then:

```bash
unity --version
unity auth login
unity doctor
```

---

# CONNECT UNITY CLI TO THEIR WORKSPACE

The teammate must use their own local path.

Example:

```powershell
cd "C:\Users\THEIR_NAME\SmartParkingGarage"
unity status
unity pipeline list
```

The project should already contain/use Pipeline.

If it is not installed:

```powershell
unity pipeline install
```

Then verify:

```powershell
unity status
unity command
```

A working connection should show the live SmartParkingGarage Editor and a large list of Unity Editor commands.

---

# CODEX SETUP

If the teammate uses OpenAI Codex:

```powershell
unity skill install codex
```

Then:

```powershell
unity mcp --project-path "C:\PATH\TO\THEIR\SmartParkingGarage" configure codex
```

Restart Codex after configuration.

Safe connection test:

```text
Use the connected Unity project through Unity MCP.

Inspect the currently open SmartParkingGarage project.

Do not modify project settings or existing assets.

Create exactly one empty GameObject named:
MY_UNITY_CONNECTION_TEST

Verify that it exists in the active scene, then stop.
```

Delete the test object when finished and do not check it into UVCS.

---

# OTHER AI CLIENTS

Do not guess client identifiers.

Have the teammate run:

```powershell
unity skill install --list
unity mcp configure --list
```

Select the supported client from those lists.

General pattern:

```powershell
unity skill install <client>
unity mcp --project-path "C:\PATH\TO\SmartParkingGarage" configure <client>
```

Restart the AI client afterward.

---

# RULES WHEN YOU ACT ON THE UNITY PROJECT

If you have Unity MCP/CLI access:

1. Inspect before modifying.
2. Preserve completed teammate work.
3. Use the existing project architecture.
4. Avoid destructive broad changes.
5. Do not upgrade the Unity Editor version.
6. Do not change global packages/settings without a specific need and user approval.
7. Do not delete project folders because they appear unused without understanding why they exist.
8. Do not overwrite `MainGarage.unity` with a new unrelated scene.
9. Validate scripts compile after changes.
10. Check the Unity Console before reporting success.
11. Report exactly what you changed.
12. Never automatically check changes into UVCS unless the user explicitly requests and reviews that action.

For larger tasks, keep subsystem ownership clear.

---

# PROJECT DEVELOPMENT PRINCIPLES

This is a capstone, so software functionality matters more than cosmetic complexity.

The 3D garage supports the software; it is not the entire project.

Prioritize features that benefit:

1. the driver,
2. the garage operator,
3. synchronized data flow between simulation/backend/interfaces.

Core product identity:

**Find me a space.**  
Select an appropriate available stall.

**Get me there.**  
Calculate and visualize a route through the garage.

**Keep everything synchronized.**  
Parking indicators, availability signs, Unity state, backend/database, driver interface, and operator dashboard respond to the same events.

---

# HOW TO HELP THE USER NOW

Establish their current setup state:

- Have they accepted the Unity invite?
- Do they have Unity Hub?
- Is Unity 6000.6.0f1 installed?
- Can they see `SmartParkingGarage/SmartParkingGarage`?
- Have they created a local UVCS workspace?
- Are they on `/main` at `cs:2` or newer?
- Does the project open without errors?
- Do they want Unity CLI/AI integration?

Then guide them from their actual current state.

Do not make them repeat steps already completed.

If they provide an error, diagnose that exact error.

If you gain Unity MCP access, inspect the real project instead of guessing its state.

Once setup is complete, help them work within the subsystem assigned to them while preserving the team's architecture and version-control discipline.
