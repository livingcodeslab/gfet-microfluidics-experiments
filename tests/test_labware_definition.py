"""The custom labware definition must ship with the package."""
import json

from gdnasynth.ot2r import labware_definition_path


def test_the_graphenea_definition_is_bundled():
    """Test that the custom definition resolves from inside the package.

    GIVEN: the package is importable
    WHEN: labware_definition_path(...) is called
    THEN: it points at the bundled Graphenea definition
    """
    path = labware_definition_path(
        "OT2_labware_definition_graphenea_card.json")

    assert path.is_file()
    definition = json.loads(path.read_text(encoding="utf-8"))
    assert definition["namespace"] == "livingcodeslab"
    assert definition["wells"]
