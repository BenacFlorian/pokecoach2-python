from pokecoach_vgc_bridge.showdown_teams import pokecoach_regulation_to_vgc_reg, snapshot_to_showdown_export
from pokecoach_vgc_bridge.battle_session import _static_builder


def test_regulation_map():
    assert pokecoach_regulation_to_vgc_reg("M-B") == "mb"


def test_snapshot_raw_blocks():
    snap = {
        "pokemon": [{"rawBlock": f"M{i}\n- Tackle"} for i in range(6)],
    }
    text = snapshot_to_showdown_export(snap)
    assert text.count("M") == 6


def test_static_team_builder_returns_packed_team_text():
    class BaseTeamBuilder:
        @staticmethod
        def parse_showdown_team(text):
            return [text]

        @staticmethod
        def join_team(team):
            return f"packed:{team[0]}"

    builder = _static_builder(BaseTeamBuilder, "showdown-team")

    assert builder.yield_team() == "packed:showdown-team"
