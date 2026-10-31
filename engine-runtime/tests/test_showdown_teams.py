from pokecoach_vgc_bridge.showdown_teams import pokecoach_regulation_to_vgc_reg, snapshot_to_showdown_export


def test_regulation_map():
    assert pokecoach_regulation_to_vgc_reg("M-B") == "mb"


def test_snapshot_raw_blocks():
    snap = {
        "pokemon": [{"rawBlock": f"M{i}\n- Tackle"} for i in range(6)],
    }
    text = snapshot_to_showdown_export(snap)
    assert text.count("M") == 6
