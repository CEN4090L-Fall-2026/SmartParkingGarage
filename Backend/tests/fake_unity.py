"""
A stand-in for Unity's backend integration client for exercising the REST contract.

It mirrors the simulation rules used by the client: Start needs Idle, Pause needs Running,
Resume needs ArrivalPaused, Drain needs Running/ArrivalPaused, manual spawns are refused
while Draining, and Reset restores the baseline while keeping the mode.
"""

from datetime import UTC, datetime


class FakeUnity:
    def __init__(self, client, session="SESSION_A"):
        self.client = client
        self.session = session
        self.sequence = 0
        self.spaces = [
            dict(s, assigned_vehicle_id=None, reserved_by=None)
            for s in client.get("/api/spaces").json()
        ]
        self.sim = {
            "state": "Idle",
            "scenario_mode": "Normal",
            "elapsed_seconds": 0.0,
            "total_spawned": 0,
            "total_completed": 0,
            "total_failed": 0,
            "active_vehicles": 0,
            "parked_vehicles": 0,
        }
        self.vehicles = []
        self.processed = {}
        self.executions = []

    def body(self, sequence=None):
        self.sequence += 1
        self.sim["active_vehicles"] = len(self.vehicles)
        self.sim["parked_vehicles"] = sum(
            1 for v in self.vehicles if v["lifecycle_state"] == "Parked"
        )
        return {
            "unity_session_id": self.session,
            "sequence": self.sequence if sequence is None else sequence,
            "timestamp": datetime.now(UTC).isoformat(),
            "simulation": dict(self.sim),
            "spaces": self.spaces,
            "vehicles": self.vehicles,
        }

    def snapshot(self, sequence=None):
        return self.client.post("/api/integration/state", json=self.body(sequence))

    def poll(self, limit=10):
        response = self.client.get(
            "/api/integration/commands",
            params={"unity_session_id": self.session, "limit": limit},
        )
        assert response.status_code == 200, response.text
        return response.json()["commands"]

    def ack(self, command_id, success, message="", vehicle_id=None):
        return self.client.post(
            f"/api/integration/commands/{command_id}/ack",
            json={
                "unity_session_id": self.session,
                "success": success,
                "message": message,
                "vehicle_id": vehicle_id,
            },
        )

    def step(self):
        """Fetch, execute each command at most once, acknowledge, then publish a snapshot."""
        handled = []
        for command in self.poll():
            command_id = command["command_id"]
            if command_id in self.processed:
                success, message, vehicle_id = self.processed[command_id]
            else:
                success, message, vehicle_id = self.execute(command)
                self.processed[command_id] = (success, message, vehicle_id)
                self.executions.append(command_id)
            self.ack(command_id, success, message, vehicle_id)
            handled.append(command_id)
        assert self.snapshot().status_code == 200
        return handled

    def execute(self, command):
        kind, payload, state = (
            command["command_type"],
            command["payload"],
            self.sim["state"],
        )
        if kind == "StartSimulation":
            if state != "Idle":
                return False, "Simulation must be Idle before it can start.", None
            self.sim.update(
                state="Running",
                elapsed_seconds=0.0,
                total_spawned=0,
                total_completed=0,
                total_failed=0,
            )
        elif kind == "PauseArrivals":
            if state != "Running":
                return False, "Arrivals can only be paused while Running.", None
            self.sim["state"] = "ArrivalPaused"
        elif kind == "ResumeArrivals":
            if state != "ArrivalPaused":
                return False, "Arrivals can only resume from ArrivalPaused.", None
            self.sim["state"] = "Running"
        elif kind == "BeginDrain":
            if state not in ("Running", "ArrivalPaused"):
                return False, "Drain requires Running or ArrivalPaused.", None
            self.sim["state"] = "Draining" if self.vehicles else "Idle"
        elif kind == "ResetSimulation":
            for space in self.spaces:
                if space["state"] != "OutOfService":
                    space.update(
                        state="Available", assigned_vehicle_id=None, reserved_by=None
                    )
            self.vehicles.clear()
            self.sim.update(
                state="Idle",
                elapsed_seconds=0.0,
                total_spawned=0,
                total_completed=0,
                total_failed=0,
            )
        elif kind == "SetScenarioMode":
            self.sim["scenario_mode"] = payload["scenario_mode"]
        elif kind == "SpawnVehicle":
            if state == "Draining":
                return False, "Manual arrivals are disabled while draining.", None
            wanted = payload["request_type"]
            level = payload.get("preferred_level")
            pool = [
                s
                for s in self.spaces
                if s["state"] == "Available" and s["space_type"] == wanted
            ]
            preferred = [s for s in pool if level is None or s["level"] == level]
            chosen = (preferred or pool or [None])[0]
            if chosen is None:
                return False, "No matching available space.", None
            number = self.sim["total_spawned"] + 1
            vehicle_id, requester = f"VEH_{number:04d}", f"SIM_VEH_{number:04d}"
            chosen.update(
                state="Reserved", assigned_vehicle_id=vehicle_id, reserved_by=requester
            )
            self.vehicles.append(
                {
                    "vehicle_id": vehicle_id,
                    "requester_id": requester,
                    "request_type": wanted,
                    "lifecycle_state": "DrivingToStall",
                    "assigned_space_id": chosen["space_id"],
                    "preferred_level": level,
                    "failure_reason": None,
                }
            )
            self.sim["total_spawned"] = number
            return True, f"Spawned {vehicle_id}.", vehicle_id
        else:
            return False, f"Unknown command {kind}.", None
        return True, "Executed.", None
