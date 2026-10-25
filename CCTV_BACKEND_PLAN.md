## Context

Implement a backend-only CCTV API for Unity's existing fixed-camera network: all thumbnail feeds, one focused feed, explicit freshness, and bounded latest-frame storage. The user selected an exclusive viewer focus lease: competing viewers receive a conflict until release or expiry. Unity uploading and dashboard rendering are separate-owner integrations; provide a complete backend receiver/control/serving contract without modifying either project. Assume conforming inputs and outputs; keep normal boundary validation and resource bounds, but add no image decoding, simulation rules, recording, database, or authentication.

## Status (2026-10-25)

The backend catalog, latest-JPEG cache, per-kind freshness, conditional GET, session lifecycle, and exclusive focus lease are implemented. Uploads enforce the 2 MiB limit while streaming, reject oversized declared lengths before reading, and require `image/jpeg`.

Camera metadata follows Unity's numeric levels (0-4), not the garage API's L1-L4 enum. A thumbnail interval of 0 uses the backend's 1-second default; the Unity publisher should send effective positive intervals so changes to Unity's capture default do not silently change freshness.

Unity capture exists, but its HTTP publisher/control adapter and the dashboard consumer remain separate integration work. No live Unity/dashboard integration has been verified. The design and verification checklist below are not a claim that every integration scenario has been exercised. Current API references are `Backend/README.md` and `docs/frontend-api.md`.

## Findings

- The sibling `Assets/Scripts/Cameras/CCTV_INTEGRATION.md` and camera source describe 14 thumbnails, normally 426x240 at 1 Hz, and one focused 1280x720 feed at 10 Hz. `CCTVCameraRegistry.cs::CCTVCameraInfo` supplies CameraId, DisplayName, Category, Level, Enabled, AllowFocused, ThumbnailIntervalSeconds, Description, and Coverage. Categories are Exterior, City, Entrance, Exit, ParkingLevel, Ramp, EV. Level 0 means no level; thumbnail interval 0 means the capture-service default, not zero-rate capture.
- `CCTVFrameStore.cs::CCTVFrame` supplies immutable JPEG bytes, per-camera/kind sequence, CapturedAtUtc, Width, Height. Sequences persist through capture stop/start and frame clearing, but restart with a new Play session. `CCTVCaptureService.cs::SetFocusedCamera` and ClearFocusedCamera remove old focused frames. Capture defaults: thumbnail interval 1 second, focused interval 0.1 seconds, staleAfterIntervals 3. The service is off until StartCapture/captureOnStart. No Unity CCTV HTTP sender/control adapter exists yet.
- Backend camera routes/store are implemented. `IntegrationService.accept_snapshot` is the authoritative Unity session switch under its RLock. Its constructor accepts injectable monotonic/UTC clocks. `main.py::create_app` shares the integration-owned CCTV store; `api/deps.py` retrieves it. Imports use modules, e.g. `from smart_parking_backend.services import garage_state`.
- `main.py` permits GET/POST/DELETE/OPTIONS and exposes X-Data-Source plus the camera metadata/ETag headers through CORS. `tests/conftest.py::client` injects FakeClock into IntegrationService and calls create_app(garage, integration). Language-server references returned `No language server found for this action`; targeted source search was used instead.

## Approach

### 1. Define camera-owned contracts and storage

Camera contracts live in `Backend/src/smart_parking_backend/models/cameras.py` and storage in `services/cctv.py`. Keep typed boundaries in Pydantic and internal JPEG storage in a frozen slotted dataclass. Camera levels are integers 0-4, matching Unity's registry; they do not use the garage API's `models.enums.Level`. Use module-qualified imports, as in current routes and services.

Constants in models/cameras.py: `MAX_CAMERAS = 32`, `MAX_FRAME_BYTES = 2 * 1024 * 1024`, `DEFAULT_THUMBNAIL_INTERVAL_SECONDS = 1.0`. CCTV service constant `FOCUS_LEASE_SECONDS = 30.0`. These bound retained JPEG data to (32 thumbnails + 1 focused) * 2 MiB = 66 MiB, not total process/network memory. The application upload buffer is bounded separately; ASGI/network buffers and concurrent requests still consume memory. Do not make a frame history or copy encoded bytes when serving them.

Define these models/types (request models use extra=forbid; metadata is immutable after validation):

- `CameraCategory(str, Enum)` values Exterior, City, Entrance, Exit, ParkingLevel, Ramp, EV; enum members uppercase snake_case.
- `FrameKind(str, Enum)` values thumbnail, focused, members THUMBNAIL/FOCUSED. These lowercase wire values deliberately map Unity's Thumbnail/Focused enum.
- `FeedHealth(str, Enum)` values Fresh, Stale, NoFrame, Unavailable; uppercase snake_case members.
- `CameraDefinition`: camera_id str (1..128 chars), display_name str, category CameraCategory, level int (0..4, required), enabled bool, allow_focused bool, thumbnail_interval_seconds float >=0, description str="", coverage str="". Level 0 means not level-specific. During catalog replacement the backend resolves thumbnail interval 0 to its 1-second default. Publishers should send the actual effective interval, especially if Unity's default is changed. Serialize category names, not Unity's numeric enum ordinals. Do not transmit pose, HDRP settings, or scene objects.
- `CameraCatalogRequest`: unity_session_id str (1..64), focused_interval_seconds float >0, cameras list[CameraDefinition] max_length=32 (empty allowed). This is a full replacement catalog, not a patch.
- `FrameUpload`: unity_session_id str (1..64), kind FrameKind, sequence int >=1, captured_at timezone-aware datetime, width int >0, height int >0, focus_generation str|None=None. It describes query parameters for an independent image/jpeg body. Use Pydantic AwareDatetime for captured_at.
- `FeedStatus`: health FeedHealth, sequence int|None=None, captured_at datetime|None=None, age_ms int|None=None, width int|None=None, height int|None=None.
- `CameraView(CameraDefinition)`: thumbnail FeedStatus, focused FeedStatus. These are separate per-kind health values, not Unity's thumbnail-only overall health.
- `FocusRequest`: lease_id str|None=None.
- `FocusState`: camera_id str|None=None, focus_generation str|None=None, expires_at datetime|None=None; null fields mean no desired focus.
- `FocusLease(FocusState)`: lease_id str (present only in successful owner responses).
- `CameraControl`: unity_session_id str, backend_instance_id str, focus FocusState. Never expose the viewer's lease_id here.

Define frozen `StoredFrame` in services/cctv.py with session_id str, camera_id str, kind FrameKind, sequence int, captured_at datetime, width int, height int, data bytes, received_mono float, initial_age_seconds float, focus_generation str|None, etag str. All metadata is already validated. No JPEG decode/transcode, base64, Pillow, python-multipart, or new dependencies.

Implement `CCTVService(clock: Callable[[], float]=time.monotonic, utcnow: Callable[[], datetime]=...)` with one RLock and these concrete methods:

- `reset_for_session(session_id: str) -> None`: clear catalog, JPEGs, sequence watermarks, focus token/state and deadlines; set active session. Do not clear on garage simulation reset or mere integration timeout.
- `replace_catalog(catalog: CameraCatalogRequest) -> None`: require matching established session (409 otherwise); atomically replace metadata and effective focused interval. Preserve latest frames/watermarks only for retained enabled camera IDs; purge removed/disabled entries. If focused camera disappears, is disabled, or disallows focus, revoke lease and remove focused bytes. Replacing with [] empties it. No seeded camera definitions.
- `publish_frame(camera_id: str, metadata: FrameUpload, data: bytes) -> None`: expire lease first, verify session, catalog ID, enabled state; focused uploads additionally require active matching camera + focus_generation. Reject sequence <= last accepted for the camera/kind with conflict and no mutation; watermarks survive focus switching/lease expiry, matching Unity's continuously increasing sequences. Replace one thumbnail slot or the single global focused slot atomically; never queue frames. Unknown camera 404, disabled camera 503, old session/sequence/generation 409. Thumbnail focus_generation is ignored and stored as None.
- `list_cameras() -> list[CameraView]`: expire lease, return registry order and per-kind status under lock. Initially [] with no seeded cameras.
- `get_frame(camera_id: str, kind: FrameKind) -> tuple[StoredFrame, FeedStatus]`: expire lease, unknown ID 404, disabled 503 Unavailable, absent frame 503 NoFrame. Focused requests without a matching live desired focus are 503 Unavailable; allow_focused=false also Unavailable. Return stale retained images with Stale status rather than discarding them. No lock may be held while HTTP sends data.
- `acquire_focus(camera_id: str, lease_id: str|None) -> FocusLease`, `release_focus(lease_id: str|None) -> None`, `focus_state() -> FocusState`, `control(session_id: str) -> FocusState` follow step 3; control requires matching established session. All expire leases on entry.

Use `garage_state.NotFoundError` for 404. Add `CameraConflictError` for 409 session/sequence/lease/generation conflicts and `FeedUnavailableError(message: str, health: FeedHealth, age_ms: int|None=None)` for 503. Use existing domain-exception/JSONResponse pattern, not HTTP exceptions inside the service.

Freshness: at ingest compute initial_age_seconds=max(0, (utcnow()-captured_at).total_seconds()); subsequent age is initial_age_seconds + (clock()-received_mono), clamped >=0, converted to integer milliseconds for output. Compare unrounded seconds: Fresh iff age <= 3 * effective interval; otherwise Stale. Use each camera's thumbnail interval and the catalog's focused interval independently. This preserves render-time age across network delay and monotonic progression after receipt. Unity/backend UTC clocks must be synchronized. Do not let JPEG uploads update garage integration last-seen time; camera freshness is independent of snapshot connectivity. Disabled/no active focus takes precedence over frame age; enabled absent frames are NoFrame.

Construct one quoted strong ETag when accepting bytes by SHA-256 hashing the small identity string `session_id + '\0' + camera_id + '\0' + kind.value + '\0' + str(sequence) + '\0' + (focus_generation or '')`; never hash the entire JPEG on each read. A new Unity session or focus generation cannot reuse the old identity.

### 2. Wire session changes without coupling camera I/O to snapshots

In `services/integration.py`, add module import for cctv and append a keyword-only constructor argument `cctv_service: cctv.CCTVService | None = None` after existing clock/utcnow arguments (preserve all existing positional parameters). Set public `self.cctv_service` to the supplied instance or a new CCTVService using the same clock/utcnow. This gives injected IntegrationService instances and normal app startup exactly the same camera lifecycle without creating two stores.

In accept_snapshot's new_session branch, call `self.cctv_service.reset_for_session(snapshot.unity_session_id)` under the existing integration lock. Same-session snapshots, rejected stale snapshots, and command ResetSimulation do not reset cameras. Lock order is integration -> CCTV only; CCTVService never imports/calls IntegrationService.

In `main.py::create_app`, assign `app.state.cctv_service = app.state.integration_service.cctv_service`; preserve the create_app signature and existing test fixtures. Add `api/deps.py::get_cctv(request: Request) -> cctv.CCTVService`. Before constructor edits try LSP references again, then use the recorded grep fallback if unavailable. Do not add observers/events, background tasks, or a repository/DI framework.

### 3. Implement exclusive renewable focus as desired state

Lease state is synchronous backend desired capture state, not an acknowledged simulation command. It must not enter IntegrationService's FIFO or create a CommandType.

- New acquisition with no live lease and no supplied token generates two distinct UUID4 hex strings: secret viewer lease_id and non-secret focus_generation. Expiry is clock()+30, expires_at=utcnow()+30 seconds. Validate catalog ID (404), enabled/allow_focused (503 Unavailable), then ownership. No active Unity snapshot connection: route returns existing UnityOfflineError/503 before acquiring or renewing focus.
- While held, only a matching lease_id can renew or switch. A renewal of the same camera extends the lease without changing generation or removing focused bytes. Switching by the same owner preserves lease_id but creates a new focus_generation and removes the previous focused image. A caller with no/wrong token receives 409 and changes nothing, even if it requests the same camera. A supplied token when no lease exists (expired, revoked, old session) receives 409; reacquisition must omit it.
- Expiry at clock() >= deadline revokes focus/token and removes focused bytes immediately on the next CCTV operation. It never deletes thumbnails. Keep per-camera/kind sequence watermarks until registry purge or session reset.
- Release requires the matching X-Focus-Lease-Id while a lease exists; missing/wrong value gets 409. If no lease exists, release succeeds with 204. Release works even when snapshot integration is offline.
- GET focus state and Unity control return camera/generation/expires_at, not lease_id. All readers may view the one focused image; exclusive lease controls selection, not private access. There is still no authentication, so this remains a trusted local/demo API.

### 4. Add independent camera HTTP surfaces

Create `api/routes/cameras.py` (router prefix /api/cameras) and `api/routes/camera_integration.py` (prefix /api/integration/cameras). Import their models/services by module, reuse Depends(deps.get_cctv/get_integration), and register both from main.py. Keep binary responses out of generic JSON envelopes.

| Method/path | Exact contract |
| --- | --- |
| POST /api/integration/cameras | CameraCatalogRequest JSON; 204 on replacement; 409 wrong/unestablished session. |
| POST /api/integration/cameras/{camera_id}/frames | Query FrameUpload plus raw image/jpeg body; 204 accepted; 409 stale session/sequence/focus generation; 404 unknown; 413 over 2 MiB; 415 wrong/missing media type; 503 disabled. |
| GET /api/integration/cameras/control?unity_session_id=... | CameraControl, 200; 409 wrong/unestablished session. No lease token. |
| GET /api/cameras | list[CameraView], 200; [] until registered. |
| GET /api/cameras/focus | FocusState, 200, all-null when unheld. Register before dynamic camera routes. |
| POST /api/cameras/{camera_id}/focus | Optional FocusRequest JSON; absent body or {} acquires; lease_id renews/switches. FocusLease, 200. 409 held/stale token; 503 offline/unavailable; 404 unknown. |
| DELETE /api/cameras/focus | Optional X-Focus-Lease-Id header; 204 released/none, 409 competing owner. |
| GET /api/cameras/{camera_id}/frame?kind=thumbnail\|focused | Default thumbnail, image/jpeg 200 or bodyless 304; 404 unknown; 503 NoFrame/Unavailable. Stale retained bytes still return 200/304 with current health. |

Upload route: async, parse metadata through `Annotated[FrameUpload, Query()]` and read `Request.stream()` into a bounded buffer, rejecting >MAX_FRAME_BYTES as 413 while streaming (also reject oversized Content-Length early when present). Require image/jpeg media type (allow MIME parameters), otherwise 415. One conversion to immutable bytes before publish; no multipart or JSON image strings. Do not hold a service lock while reading the upload. Expose raw JPEG requestBody in OpenAPI with `openapi_extra` because streaming Request does not generate it. Existing Pydantic 422 behavior is retained; add no custom malformed-JPEG validation. Empty/invalid image content is outside conforming-input scope; resource bounds are still enforced.

GET frame: get an immutable stored reference + fresh FeedStatus under the service lock, then send a normal Response outside it. Headers on 200 and 304: ETag, Cache-Control: private, no-cache, X-Unity-Session-Id, X-Frame-Sequence, X-Captured-At (UTC ISO8601), X-Frame-Age-Ms, X-Feed-Health, X-Frame-Width, X-Frame-Height. Respect If-None-Match including comma-separated tags, optional W/ prefix and wildcard *; compare only once current availability/health was computed. An unchanged JPEG can age from Fresh to Stale while returning 304; status headers must still update. Return no X-Data-Source for cameras; it describes garage projection, not capture freshness. Browser clients retain their last displayed JPEG on 304 and update health badges from headers.

Register main.py handlers: CameraConflictError -> 409 {success:false,message}; FeedUnavailableError -> 503 {success:false,message,health,age_ms}, also X-Feed-Health and X-Frame-Age-Ms when available. Do not change existing generic 503/409 handlers. Route-bound 413/415 can use FastAPI HTTPException/detail, consistent with other HTTP boundary validation.

CORS: preserve origins and credentials policy, add DELETE to allow_methods, and expose existing X-Data-Source plus ETag and every X-*camera response header above. Existing allow_headers=["*"] covers If-None-Match and X-Focus-Lease-Id. No wildcard origins.

### 5. Define the adapter handoff as part of the API contract

Use the existing `docs/frontend-api.md` as the dashboard-facing contract and Backend/README.md's integration section for Unity publishing; no new handoff-document hierarchy. Explicitly distinguish CCTV's synchronous 200/204 control/ingest endpoints from simulation commands' 202 queue semantics. The API is functional with an HTTP publisher; do not call it live Unity streaming before a separate adapter is installed.

The Unity owner's exact sequence is: publish an ordinary garage snapshot to establish session; POST the catalog with effective thumbnail/focus intervals; StartCapture; upload new thumbnail frames independently of snapshots; poll camera control approximately every 0.5 seconds. For a non-null desired focus call SetFocusedCamera(camera_id), and echo focus_generation on every focused upload; when null call ClearFocusedCamera. Tag the captured work with the generation at capture, not a later current selection; never relabel an older focused frame after switching/reacquiring. Drop completed uploads older than latest and never queue a backlog: at most one in-flight upload per camera/kind, next send uses the latest available sequence. A 409 old session requires the ordinary snapshot/session handshake and catalog publication; a 409 old focused generation requires reading current control, not retrying stale bytes. Capture stop leaves last frames to age; backend restart requires catalog republishing. No new Unity code is included here.

The current Unity `CCTVFrame` does not carry backend `focus_generation`, and `SetFocusedCamera` accepts only the camera ID. Capture-time generation association must be provided by the Unity integration; simply attaching whichever generation is current when uploading is unsafe, including when focus leaves and returns to the same camera. Effective thumbnail/focused intervals also need to be reported from Unity's configured capture settings.

This backend serves polled JPEGs for both thumbnails and focused viewing. The Unity document's MJPEG/WebSocket suggestions remain alternatives, not implemented transports. Confirm the implemented wire contract with the Unity owner before connecting the adapter. Stale retained images remain readable with updated health headers; the backend does not turn a stale image into a 503 merely because it is old.

Dashboard contract: poll visible thumbnails about 1 Hz and focused view about 10 Hz without overlapping requests; conditional JPEG GET and object URLs permit reading headers; no production dashboard changes here. Acquire focus without a token, keep returned lease_id in the viewer, renew with it every 10 seconds, use it to switch and release, stop renewals on viewer teardown; expiry handles crashes. Show 409 as focus owned by another viewer, not a camera outage; do not automatically steal focus. Inspect per-kind health even on HTTP success/304. Focus selection is desired state, not proof of Unity applying it. Vehicle-tracking cameras are a local Unity operator view and not an additional network feed in this contract.

## Verification

Create `Backend/tests/test_cameras.py` using the current client/unity/clock fixtures and a small inline valid JPEG fixture (fixed decoded bytes, no image library). Helpers publish catalogs and raw frames through HTTP; do not grow FakeUnity into a camera/physics simulator. Use two cameras with thumbnail interval 1 second, focused interval 0.1 second, plus disabled/non-focusable variants where relevant. Permanently test consumer-visible transitions/bounds, not forwarding-only copies or implementation source:

1. Initial [] catalog; registered enabled camera has NoFrame and frame GET 503; unknown 404; disabled Unavailable/503. Catalog replacement removes IDs/frames and revokes removed/disabled focus; same retained ID keeps latest image.
2. A newer thumbnail supersedes the previous frame; equal/lower sequence returns 409 and does not replace it. Independent kind sequences. Old session uploads/control/catalog return 409. A new ordinary Unity session clears camera metadata, frames, watermarks and lease; after re-registration, sequence 1 is accepted with a different ETag from the prior session's sequence 1.
3. Health transitions with FakeClock: fresh thumbnail at age 0; focus at age 0.31 is Stale while thumbnail remains Fresh; thumbnail at age >3 is Stale. Include delayed captured_at at upload to prove capture-time age, not upload time, matters. Same-session snapshots and repeated GET/304 do not refresh frame age. Uploading JPEGs does not refresh IntegrationStatus snapshot connectivity. Stale JPEG retrieval remains 200 with Stale headers.
4. Conditional GET returns 304 with no body for matching strong/weak/list/wildcard If-None-Match, updated health/age headers, and a new ETag/200 after a newer frame. An expired focused lease returns 503, never 304 from an old ETag.
5. Viewer A acquires/renews; viewer B/no-token gets 409; A switches camera and new generation rejects late old uploads while thumbnails persist. Wrong release token conflicts; correct release succeeds and clears focused bytes. At exactly 30 seconds without renewal another viewer may acquire, gets a new token/generation, and expired tokens cannot renew/release it. Renewal of the same camera preserves generation and image. Public focus/control never leak lease_id. Keep snapshot connection fresh before lease POSTs in tests that advance >5 seconds.
6. At-most-one-focused invariant: switching back to a previous camera cannot expose bytes from an old generation; watermarks reject old sequence even after focus reset. Same-session garage reset/snapshot does not clear catalog/lease. Two concurrent direct acquire_focus calls with no token yield one success/one CameraConflictError, demonstrating atomic exclusive ownership.
7. Resource boundaries: catalog >32 gets existing Pydantic 422 without replacing prior catalog; streamed JPEG >2 MiB gets 413 without replacing previous frame; many accepted newer frames replace slots rather than growing retained history (inspect retained slot counts/bytes in a narrowly scoped service test, asserting the stated memory invariant, not internal wiring). No malformed-JPEG tests.
8. A browser-origin CORS request can use DELETE, If-None-Match, and X-Focus-Lease-Id and read frame metadata/ETag headers; retain current origin restrictions. Existing simulation commands/snapshots continue to function while catalogs/images are accepted.

From Backend run `uv run pytest -q tests/test_cameras.py` and then `uv run pytest -q` after integration. Existing Ruff gates apply automatically; do not change dependency versions for this task.

Actual runtime proof: launch `uv run uvicorn smart_parking_backend.main:app --host 127.0.0.1 --port 18083` from Backend, choosing another free loopback port if occupied (never stop a user process). A throwaway httpx publisher first posts an ordinary Unity snapshot using /api/spaces inventory and an Idle/Normal report (reuse tests/fake_unity.py::body's schema), then registers all 14 camera IDs from the Unity document with effective intervals 1/0.1. Use a real JPEG sample; available local sample `/home/joshua/projects/CEN4090L/SmartParkingGarage/Assets/Environment/City/Textures/T_Image_9.jpg` was located during planning, but inspect actual dimensions and byte size first; if too large use the inline valid test JPEG fixture with its correct dimensions. This is sample content, not a live camera capture.

Upload thumbnail sequence 1, GET and compare bytes, then conditional GET -> 304. Acquire focus as viewer A, show viewer B ->409, poll Unity control and confirm no owner token, upload focused sequence 1 tagged with generation, GET focused bytes. Renew and release A; old-generation upload ->409 and focused GET ->503 while thumbnail remains available. Keep ordinary snapshots current during the smoke. Post a new Unity session and re-register/upload sequence 1: old ETag must yield 200 with a different tag. Observe X-Feed-Health/age progression and exact CORS headers on real HTTP responses. Fetch /openapi.json and verify raw image/jpeg upload plus typed JSON controls and no new command enum. Stop only the smoke server. Report HTTP protocol proof separately from unperformed Unity capture/dashboard rendering verification.

## Assumptions & contingencies

- Backend-only scope and exclusive focus ownership are explicit user choices. Lease duration 30 seconds and renewal every 10 seconds follow Unity's suggested lease cadence. If the Unity team needs a different wire contract, obtain that agreement before changing the implemented API; do not add compatibility aliases or a second transport.
- Unity and backend share synchronized UTC for initial capture age; monotonic progression handles backend wall-clock changes after receipt. Frames can be fresh while garage snapshots are stale; keep those statuses independent, while requiring a live snapshot connection for new/renewed focus.
- One backend process remains required for this process-local cache/lease/queue. Multiple workers would split viewer ownership and frames and are not supported by this change.
- Unity has no HTTP camera publisher yet and capture is off until started. That does not block exercising every backend API with a real HTTP publisher, but live scene visuals and camera scheduling require the Unity owner's separate adapter. Never claim live camera integration based on fixture uploads.
