def test_baseline_garage_inventory(client):
    response = client.get("/api/garage")
    assert response.status_code == 200
    garage = response.json()
    assert garage["total_physical_spaces"] == 414
    assert garage["operational_spaces"] == 406
    assert garage["available"] == 406
    assert garage["occupied"] == 0 and garage["reserved"] == 0
    assert garage["out_of_service"] == 8
    assert garage["by_space_type"] == {"Standard": 406, "EV": 8}
    levels = {level["level"]: level for level in garage["levels"]}
    assert list(levels) == ["L1", "L2", "L3", "L4"]
    expected = {
        "L1": (91, 87, 4),
        "L2": (101, 101, 0),
        "L3": (111, 111, 0),
        "L4": (111, 107, 4),
    }
    for level, (total, available, out_of_service) in expected.items():
        actual = levels[level]
        assert (actual["total"], actual["available"], actual["out_of_service"]) == (
            total,
            available,
            out_of_service,
        )
