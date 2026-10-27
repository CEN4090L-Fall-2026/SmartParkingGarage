# Archived Unity CCTV capture notes

> Historical Unity-side capture notes and proposed transport contract.
> Backend camera endpoints and Unity's HTTP publisher have since been implemented.
> Use the [backend guide](../../../Backend/README.md#unity-camera-publisher) and
> [dashboard API reference](../../frontend-api.md#cctv) for the current contract.
> Original status claims, performance measurements, and transport options below are preserved as historical material,
> not current verification results or a list of implemented features.

Operator CCTV system (Unity side)
Status: Unity capture working. Dashboard streaming NOT integrated. Nothing in Backend/ or the dashboards consumes these feeds yet; this document proposes the contract for that later task.
Piece
State
Unity CCTV capture (14 thumbnails + 1 focused feed, latest-frame store, health)
Implemented
Unity keeps simulating and capturing while it is not the foreground app
Implemented (Run In Background, see below)
FastAPI / React CCTV streaming
Not yet integrated (no camera endpoints, no dashboard component)
Pieces
File
Responsibility
CCTVCameraRegistry.cs
Camera definitions (stable id, name, category, level, anchor, FOV, enabled, capture profile, description, coverage). Owns no Camera.
CCTVOperatorView.cs
The interactive operator view: sole owner of the primary MainCamera pose. Snaps to fixed anchors; IOperatorViewSource seam for a future vehicle-tracking rig.
CCTVCaptureService.cs
Offscreen capture: scheduling, HDRP render requests, async GPU readback, JPEG encoding on worker threads, status.
CCTVFrameStore.cs
Bounded, thread-safe latest-frame storage (one thumbnail + one focused frame per camera).
Assets/Editor/CCTVSetupTool.cs
Smart Parking/Cameras/Author CCTV Camera Network: idempotently (re)builds the network in MainGarage.
Scene: OPERATOR_CCTV_SYSTEM/{CAMERA_REGISTRY, OPERATOR_VIEW, CCTV_CAPTURE_SYSTEM, CAMERA_ANCHORS/CAM_*}. Anchors are plain Transforms. At runtime the capture service adds CCTV_CAPTURE_RUNTIME (two disabled cameras, not saved) under CCTV_CAPTURE_SYSTEM while capturing.
Camera network (14)
Id
Category
Level
Purpose
CAM_GARAGE_EXTERIOR
Exterior
-
Default view: garage, portal and street from the south-east
CAM_CITY_APPROACH
City
-
Street from x 92 west to the portal, both lanes
CAM_CITY_INTERSECTION
City
-
T-junction: inbound turn-in (north leg), outbound turn-out (south leg)
CAM_ENTRANCE
Entrance
1
Mast arm over the street, looking into the portal
CAM_EXIT
Exit
1
South-east pole: departures leaving the portal onto the eastbound lane
CAM_L1_OVERVIEW ... CAM_L3_OVERVIEW
ParkingLevel
1-3
South-west ceiling corner looking across the level
CAM_L4_OVERVIEW
ParkingLevel
4
Parapet pole on the open top deck
CAM_EV_STALLS
EV
2
Head-on view of the full EV row L2_SPACE_029 - 036
CAM_RAMP_L1_L2 / L2_L3 / L3_L4
Ramp
2-4
Ramp heads on the upper level, looking down the up ramps
CAM_TOP_DECK
ParkingLevel
4
High mast over the whole roof deck
Local operator controls
Play Mode keys (Input System): ] next camera, [ previous camera, Home default camera. API (CCTVOperatorView): SelectCamera(id), SelectNextCamera(), SelectPreviousCamera(), RestoreDefaultCamera(), GetCurrentCameraId(), GetAvailableCameras(), SetExternalSource(IOperatorViewSource). Unknown or disabled ids are rejected and the current view is kept. Switching is an instant cut.
Capture service API (CCTVCaptureService)
ListCameras(), TryGetCameraMetadata(id, out CCTVCameraInfo) — immutable snapshots; no scene access needed.
StartCapture(out reason), StopCapture(), IsCapturing — capture is off until started (captureOnStart).
TryGetLatestFrame(id, out CCTVFrame) (thumbnail) / TryGetLatestFrame(id, CCTVFrameKind.Focused, out frame).
SetFocusedCamera(id, out reason), ClearFocusedCamera(), FocusedCameraId.
GetCaptureStatus(), GetFeedStatus(id), ResetStatistics(), ClearFrames().
CCTVFrame: CameraId, Kind, Sequence (strictly increasing per camera and kind), CapturedAtUtc and CapturedRealtime (render time, not encode time), Width, Height, Encoding (image/jpeg), Bytes (read-only; never overwritten after publication), MeanLuma (black-frame indicator), AgeSeconds(now). CCTVFeedHealth: Fresh, Stale (newest frame older than 3 of its intervals), NoFrame, Unavailable (disabled or unknown id).
Sequence numbers are per camera and kind, and survive StopCapture/StartCapture and ClearFrames for the life of the capture service. A new Play session (or player launch) creates a new service, so numbering starts again at 1: a consumer should key frames by Unity session (the unity_session_id the backend link already reports) plus camera and kind, and treat a lower sequence under a new session as a restart. When focus moves, the previous camera's focused frame is removed, so at most one focused frame exists. Freshness: a feed's health follows its thumbnail, which is Stale after 3 s with the default 1 s interval; the focused feed has no separate health state, so judge it by FocusedAgeSeconds / frame age (it is normally under 0.25 s at 10 fps). When capture stops, the retained frames age into Stale.
How capture works (HDRP 17.6 / Unity 6000.6)
Two disabled capture cameras (thumbnail, focused) copy MainCamera's camera and HDRP settings and render through RenderPipeline.SubmitRenderRequest with a StandardRequest into two reusable R8G8B8A8_SRGB RenderTextures.
Exposure: HDRP keeps automatic exposure history per camera. Before every thumbnail the camera is cut with HDCamera.Reset(), so HDRP exposes the frame from its own luminance. The focused camera keeps its history and is reset only when focus moves.
Camera motion blur is disabled on the capture cameras (frame-settings override): jumping between anchors would otherwise be rendered as camera motion. MainCamera is unchanged.
Readback is AsyncGPUReadback (no GPU stall). JPEG encoding uses ImageConversion.EncodeArrayToJPG on the thread pool (thread-safe), with pooled RGBA buffers.
Scheduling: at most one render per frame; focused feed first unless a thumbnail is more than one interval overdue (no starvation); a CPU render budget (token bucket) and caps on in-flight readbacks (3) and pending encodes (4) defer captures rather than queueing them. Under load frames get older; the simulation is never slowed down.
Constraints: Play Mode only; rendering happens in LateUpdate on the main thread (the render-request CPU cost is on the main thread); disabled game cameras keep HDRP history buffers while capture runs and are destroyed by StopCapture.
Measured performance (editor, Play Mode, production presets, 40 s windows)
Main-thread frame time (ProfilerRecorder "CPU Main Thread Frame Time", average / p95):
Traffic
Capture off
Thumbnails (14 feeds, 1 fps)
Thumbnails + focused 720p at 10 fps
None
0.58 / 0.81 ms
0.97 / 4.40 ms
1.36 / 4.70 ms
Normal
1.13 / 1.36 ms
1.67 / 4.91 ms
2.00 / 5.06 ms
Rush Hour
1.34 / 1.54 ms
1.79 / 4.99 ms
2.19 / 5.23 ms
One capture render costs ~3.2 ms main-thread CPU (max seen 17.8 ms during a frame hitch); thumbnails run ~14 renders/s, focused adds 10/s. The p95 rise is the frames that carry a capture.
GPU ("GPU Frame Time" recorder) ~1.9-2.4 ms p95 on capture frames. These cs:26 figures were taken in an editor stepped frame by frame (before Run In Background was enabled) that did not render the Game view, so the main view's GPU time could not be measured; treat GPU figures as indicative.
JPEG encoding runs on worker threads: ~1.15 ms per thumbnail, ~5.6 ms average including focused 720p frames.
Output: thumbnails ~14 KB (q70) → ~193 KiB/s for all 14 feeds; focused 720p ~68-147 KB (q80) at 10 fps → ~1.5 MiB/s total with focus. Measured rates: every feed 0.98-1.01 fps (worst gap 1.22 s); focused 9.96-10.01 fps (worst gap 0.29 s). No deferrals, no out-of-order frames, no errors.
Retained memory: one thumbnail per feed + one focused frame (~0.2-0.35 MB). While capturing: 2 cameras, 2 RenderTextures (426x240 and 1280x720 RGBA8), 3 GameObjects; all released by StopCapture.
Simulation: 0 failures and 0 contacts in every configuration; capture has no simulation dependency.
If capture becomes too expensive on other hardware: raise the thumbnail interval, lower renderBudgetMsPerFrame (the scheduler then defers captures and frames get older), or lower the focused rate/size.
Background execution (Unity not the foreground app)
Dashboards run outside Unity, so Unity must keep running when another application has focus. This comes from one project setting: Player > Resolution and Presentation > Run In Background (runInBackground: 1 in ProjectSettings/ProjectSettings.asset). No script changes it at runtime. With it off, an unfocused Unity stops its player loop entirely: vehicles, backend snapshots and command polling, and CCTV capture all freeze (measured: 0 frames in 60 s), and every feed goes Stale.
Measured with it on (editor Play Mode, production presets, another application in the OS foreground):
Traffic / capture
Unity
Frames
Sim time vs real
Thumbnails per feed
Focused 720p
Worst age thumb / focused
Snapshots
Normal, capture off
unfocused 202 s
138 fps
0.999
-
-
-
0.99/s
Normal, 14 thumbnails
unfocused 203 s
128 fps
1.000
1.00 fps (all 14)
-
1.28 s / -
0.99/s
Normal, thumbnails + focused
unfocused 3 x ~80 s (ENTRANCE, EV_STALLS, CITY_INTERSECTION)
111-114 fps
1.000
1.00-1.01 fps
9.9-10.0 fps
1.12 s / 0.23 s
0.98-1.00/s
Rush Hour, thumbnails + focused
unfocused 303 s
124 fps
1.000
1.00 fps (all 14)
9.99 fps
1.11 s / 0.22 s
0.99/s
Rush Hour, thumbnails + focused
focused 34 s
105 fps
1.000
0.99-1.02 fps
9.97 fps
1.04 s / 0.14 s
0.97/s
Capture rates, frame ages and costs are the same focused and unfocused (no deferrals, readback or encode errors in any window); a capture render still costs ~3.4-3.8 ms of main-thread CPU. Backend commands are delivered and acknowledged within ~0.5 s while Unity is unfocused.
Editor note: if Play Mode is entered while the editor is in the background (for example from a script, when Windows refuses to bring it forward), the first frame can wait until the editor window has been focused once; after that it keeps running unfocused. Press Play from the focused editor.
Players inherit the same Player setting. A standalone build has not been tested yet, nor has a minimized window.
Consumers should still judge freshness from frame age / X-Feed-Health, never from HTTP success: a paused, stopped or frozen Unity keeps serving its last frames, which simply age into Stale.
Proposed dashboard transport contract (for the later integration task)
A backend adapter talks to Unity, never to scene objects. Suggested REST surface on the backend:
Enumerate: GET /api/cameras → [{camera_id, display_name, category, level, enabled, description, coverage, health}] (from ListCameras() + GetFeedStatus()).
Latest frame: GET /api/cameras/{camera_id}/frame?kind=thumbnail|focused → image/jpeg body with headers X-Frame-Sequence, X-Captured-At (UTC ISO-8601), X-Frame-Age-Ms, X-Feed-Health; ETag = sequence so clients can poll with If-None-Match and receive 304 when nothing changed.
Frame age: always from CapturedAtUtc (render time); clients show a stale badge when X-Feed-Health is Stale or age exceeds ~3 thumbnail intervals.
Focus: POST /api/cameras/{camera_id}/focus (lease, e.g. 30 s, renewed by the viewer) → SetFocusedCamera.
Release: DELETE /api/cameras/focus or lease expiry → ClearFocusedCamera (thumbnails always continue).
Unavailable feeds: listed with enabled=false / health=Unavailable; frame requests return 404 (unknown id) or 503 with the last frame's age when no fresh frame exists.
Bandwidth (measured, JPEG q70 426x240 at 1 fps per feed; q80 1280x720 at 10 fps): see the measured figures above (~193 KiB/s for the 14-feed grid, ~1.5 MiB/s with one focused feed). Unity produces each frame once regardless of the number of viewers; the backend should cache the latest frame per feed and fan it out, so viewer count multiplies only backend→browser traffic, not Unity capture work.
Concurrent viewers: one focused feed is supported; several viewers focusing different cameras should be arbitrated by the backend (e.g. most recent request wins, or a short priority lease), never by adding Unity cameras.
Transport options:
Option
Fit
Notes
Periodic JPEG snapshots (HTTP poll + ETag)
Grid thumbnails, prototype
Simplest; matches the 1 fps grid; cacheable
MJPEG (multipart/x-mixed-replace)
Focused view at 5-15 fps
Native <img> support; no client code; one connection per stream
WebSocket binary frames
Grid + focused over one socket
Push, low overhead, needs small client decoder; good next step
WebRTC (H.264)
>15 fps / many viewers / low bandwidth
Real video encoding; much more infrastructure; only if frame rate needs grow
Recommendation for the first integration: Unity pushes encoded frames to the backend (or the backend pulls them over the existing Unity↔backend link), the backend serves JPEG snapshots for the grid and MJPEG or WebSocket for the focused view. Move to WebRTC only if a higher frame rate becomes a requirement.
Future vehicle tracking
CCTVOperatorView.SetExternalSource(IOperatorViewSource) hands the primary camera to a pose provider evaluated every LateUpdate; returning false hands it back to the selected fixed camera. A tracking rig implements IOperatorViewSource (look up the vehicle by id in VehicleSimulationRegistry, compute a follow pose). No per-vehicle cameras and no prefab changes are needed. A tracked feed for the dashboard can reuse the capture service's focused camera by registering the same pose provider as a capture source in a later change.