# Smart Parking Garage — Team Setup Guide

Backend setup and ownership are documented in [README.md](README.md). The Unity onboarding sections below describe
the original cs:2 baseline; use the numbered handoff documents for the later simulation status. Joshua works only
in this sibling backend workspace and does not modify the Unity workspace.

## Project Overview

**Project:** Smart Parking Garage Management and Guidance System  
**Team:** The SemiColons  
**Unity version:** **6000.6.0f1**  
**Render pipeline:** **HDRP**  
**Main Unity scene:** `Assets/Scenes/Main/MainGarage.unity`  
**Unity Version Control repository:** `SmartParkingGarage/SmartParkingGarage`  
**Branch:** `/main`  
**Team baseline:** `cs:2`

### What we are building

This project is a real-time smart parking system built around a realistic multi-level parking garage.

The system is intended to let a driver:

- see live parking availability;
- receive an assigned parking space;
- be guided through the garage to that space;
- use red/green overhead indicators to identify occupied/open spaces;
- see availability by level;
- eventually reserve a space, use EV/ADA-aware assignment, and use “Find My Car.”

The garage operator will have a separate management interface that can:

- monitor total and per-level occupancy;
- see the state of individual parking spaces;
- manage reserved/out-of-service spaces;
- view active parking sessions;
- monitor congestion and garage activity;
- view analytics and performance metrics.

The 3D garage in Unity is the simulation environment used to test the software. Vehicles, parking spaces, guidance lights, digital signs, gates, routing, the backend, and the management dashboard will eventually stay synchronized in real time.

### Current technical direction

- **Unity / C#** — 3D simulation, garage behavior, cameras, vehicle movement, parking-space visualization
- **Blender** — source environment/artwork
- **Python + FastAPI** — backend/API
- **PostgreSQL** — planned persistence; the current backend stores its projection and commands in memory
- **React + TypeScript** — operator dashboard and possibly the driver-facing interface
- **REST polling** — current Unity/backend communication; WebSockets are not implemented

### Repository boundaries

- Unity source stays in the UVCS workspace described below.
- Backend source is under `Backend/` in the team GitHub checkout, with `app/`, `tests/`, and `pyproject.toml` at the backend root. Run it with `uv`; PostgreSQL and Compose are not required for the current baseline.
- The backend folder is outside the Unity workspace. Do not create a Git repository inside the Unity workspace or copy backend files back into it.
- The canonical GitHub repository is <https://github.com/CEN4090L-Fall-2026/SmartParkingGarage>; keep its checkout separate from the Unity workspace.


The Unity project already contains the HDRP baseline, imported garage, main scene, organized floor hierarchy, colliders, materials, and starter C# manager classes. The current shared baseline is **changeset `cs:2` on `/main`**.

---

# 1. Required Software

Everyone should use the **same Unity Editor version**:

**Unity 6000.6.0f1**

Install it from Unity Hub.

Do not open the shared project with a different Unity version unless the team explicitly agrees to upgrade. Different Editor versions can rewrite serialized project data and create unnecessary source-control conflicts.

Recommended tools:

- Unity Hub
- Unity 6000.6.0f1
- Visual Studio / VS Code / Rider
- Unity Version Control client if Unity prompts you to install it
- Unity CLI if you want to use Codex or another AI agent with the live Unity Editor

---

# 2. Accepting the Project Invite

You should receive an invitation to the Unity organization/project at the email address associated with your Unity account.

1. Open the Unity invitation email.
2. Accept the invitation while signed into the Unity account you intend to use for the project.
3. If you do not already have a Unity ID, create one using the invited email address.
4. Open **Unity Hub** and sign into that same Unity account.
5. Confirm that the shared Smart Parking Garage project is visible.

If the project does not appear after accepting the invite, contact Hayden before creating anything. **Do not create your own separate SmartParkingGarage project or repository.**

---

# 3. Unity Version Control — What It Is

We are using **Unity Version Control (UVCS)** for the shared Unity project.

Repository:

```text
SmartParkingGarage/SmartParkingGarage
```

Branch:

```text
/main
```

Current team baseline:

```text
cs:2
```

Think of UVCS as the central shared copy and history of the project.

Each team member has their **own local workspace**:

```text
Your computer
    │
    │  Check in / Get latest
    ▼
Unity Version Control repository
    ▲
    │
Other teammates' computers
```

Do **not** work directly out of someone else's project folder, OneDrive folder, Google Drive folder, shared network folder, etc.

Your local workspace is your working copy. UVCS stores the shared changesets/history.

### Important terms

- **Repository** — the shared project and its complete history.
- **Workspace** — your local copy of that repository.
- **Pending Changes** — files you changed locally but have not checked in.
- **Checkin** — sends your changes to the shared repository as a changeset.
- **Update/Get Latest** — downloads teammates' newer changes into your workspace.
- **Changeset** — one saved group of changes in project history.

---

# 4. Getting Your Local Copy of the Project

After accepting the invite:

1. Open Unity Version Control from Unity/Unity Hub, or open the Unity Version Control desktop client if installed.
2. Sign in using the same Unity ID that accepted the project invite.
3. Select the shared project and repository:

```text
SmartParkingGarage/SmartParkingGarage
```

4. Create a **new workspace** from the repository.
5. Choose a local location, for example:

```text
C:\Users\YOUR_NAME\SmartParkingGarage
```

6. Make sure the workspace is on branch:

```text
/main
```

7. **Get Latest / Update** until you are on at least:

```text
cs:2
```

8. Open the downloaded project using **Unity 6000.6.0f1**.
9. Let Unity finish importing packages/assets before doing any work.
10. Open `Assets/Scenes/Main/MainGarage.unity` and verify the Console is clean.

Do not manually copy Hayden's Unity project directory. Create your workspace from UVCS so all changes are tracked correctly.

---

# 5. Version-Control Rules for the Team

## Before starting work

Always:

1. Save/finish any local work.
2. Open UVCS.
3. **Get Latest / Update workspace.**
4. Open Unity and verify there are no unexpected compile errors.

## While working

Try to work inside your assigned subsystem.

Examples:

- Unity simulation
- vehicle logic
- parking system
- navigation/routing
- backend
- database
- dashboard/UI

Avoid having multiple people make major edits to `MainGarage.unity` or the main garage prefab at the same time unless coordinated.

## When checking in

Make small, logical changesets.

Good:

```text
Add ParkingSpace occupancy state component
```

```text
Create Level 2 routing graph
```

```text
Add operator occupancy API endpoint
```

Bad:

```text
stuff
```

Before checking in:

- save scenes/assets;
- make sure scripts compile;
- check the Unity Console;
- review Pending Changes;
- do not include unrelated temporary/generated files.

## Files that normally belong in source control

- `Assets/`
- `Packages/`
- `ProjectSettings/`

Do not add generated/cache folders such as:

- `Library/`
- `Temp/`
- `Logs/`
- `obj/`
- `UserSettings/`

## Never overwrite teammate work blindly

If UVCS reports a conflict:

- stop;
- identify which files conflict;
- talk to the teammate if it is a scene/prefab or other important shared asset;
- merge intentionally rather than choosing a random version.

---

# 6. Current Shared Baseline

The current baseline checked into `/main` is:

```text
cs:2
```

It includes:

- Unity 6000.6 HDRP project setup
- `MainGarage.unity`
- core scene/system hierarchy
- imported and organized v017 garage
- **414 parking stalls**
- **8 EV stalls**
- HDRP-compatible materials
- architectural colliders
- repaired L1↔L2 ramp landing transitions
- validation of all six internal ramps
- floor-isolation hierarchy
- dynamic guidance/sign objects preserved for later runtime behavior
- zero compiler errors and zero Console warnings/errors at baseline check-in

If your local project does not match this, update your workspace before starting development.

---

# 7. Unity CLI Setup (Optional but Recommended for AI Assistance)

The Unity CLI allows Codex and other supported AI clients to communicate with a running Unity Editor through Unity Pipeline/MCP.

You do **not** need AI tooling to contribute to the project.

## Windows

Open PowerShell:

```powershell
winget install Unity.CLI
```

Then open a fresh PowerShell window:

```powershell
unity --version
unity auth login
unity doctor
```

Complete the Unity login in your browser if prompted.

## macOS / Linux with Homebrew

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

# 8. Connect the CLI to Your Local Unity Project

Open the shared project in Unity first.

Then in a terminal:

```powershell
cd "C:\path\to\your\SmartParkingGarage"
unity status
```

You should see the running Unity Editor and the `SmartParkingGarage` project.

Verify Pipeline:

```powershell
unity pipeline list
```

If Pipeline is missing for some reason:

```powershell
unity pipeline install
```

After Unity finishes compiling:

```powershell
unity status
unity command
```

`unity command` should show a large set of Editor commands if the connection is healthy.

---

# 9. Connect Codex to Unity

If you use **OpenAI Codex**:

```powershell
unity skill install codex
```

Then configure Unity MCP for **your own local workspace path**:

```powershell
unity mcp --project-path "C:\path\to\your\SmartParkingGarage" configure codex
```

Restart Codex afterward.

A simple connection test is:

```text
Use the connected Unity project through Unity MCP.

Inspect the currently open SmartParkingGarage project.

Do not modify project settings or existing assets.

Create exactly one empty GameObject named:
MY_UNITY_CONNECTION_TEST

Verify that it exists in the active scene, then stop.
```

Delete the test object afterward and do not check it into UVCS.

---

# 10. Using a Different AI Client

To see which skill integrations your installed Unity CLI supports:

```powershell
unity skill install --list
```

To see supported MCP clients:

```powershell
unity mcp configure --list
```

Use the client ID shown by those commands.

General pattern:

```powershell
unity skill install <client>
unity mcp --project-path "C:\path\to\SmartParkingGarage" configure <client>
```

Restart the AI client after configuring MCP.

Do not assume every AI client supports both the Unity skill and MCP. Use the lists returned by your installed Unity CLI.

---

# 11. AI Rules for This Project

When using Codex or another agent:

- tell it the exact local Unity project path;
- tell it to use the connected Unity project/MCP;
- scope the task narrowly;
- tell it what it must **not** change;
- make it inspect existing work before replacing anything;
- validate compilation/Console after code changes;
- review its changes before checking them into UVCS.

Do not allow an agent to:

- delete major project folders without explicit reason;
- upgrade Unity versions/packages without team approval;
- redesign shared architecture without coordination;
- overwrite teammate work;
- automatically check in large changes you have not reviewed.

AI-generated code is still our responsibility.

---

# 12. Recommended Team Workflow

At the beginning of a work session:

```text
Get Latest → Open project → Verify Console → Work
```

At the end:

```text
Save → Test → Check Console → Review Pending Changes → Check in
```

Communicate before editing the same major scene/prefab as another teammate.

For large tasks, keep ownership clear and integrate deliberately.

---

## Questions / Problems

If your invitation, UVCS workspace, Unity version, Pipeline connection, or MCP setup does not work, **do not create a separate replacement project**.

Send the error/output to Hayden or paste it into your AI assistant and troubleshoot the existing shared setup.
