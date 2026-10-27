"""Tests for the OT-2R liquid ledger: composition, volumes and guards."""
import uuid

import pytest

from gdnasynth.ot2r.liquids import (InsufficientVolumeError, LiquidId,
                                   Liquids, UnknownLabwareError,
                                   UnknownWellError, Well, WellCapacities,
                                   WellOverflowError, aspirate, dispense,
                                   liquid_volume, register, volume)

# Two distinct labware of the same model are distinguished by their ids.
PLATE = uuid.UUID("0d1e2f30-1111-4222-8333-444455556666")
OTHER_PLATE = uuid.UUID("0d1e2f30-7777-4888-8999-aaaabbbbcccc")
RESERVOIR = uuid.UUID("fe305793-e2b6-40ce-94d7-2b55549b1b57")
UNREGISTERED = uuid.UUID("c9c762e1-8205-4ccd-be32-6535fd0e9514")

WATER = LiquidId("aaaaaaaa-1111-4111-8111-111111111111")
PBS = LiquidId("bbbbbbbb-2222-4222-8222-222222222222")


def _capacities(rows, columns, capacity_ul):
    """Build a {well: capacity} map for the given rows and columns."""
    return {f"{row}{column}": capacity_ul
            for row in rows for column in columns}


def _plate(labware_id=PLATE, capacity_ul=200.0):
    """Build the well capacities of a 96-well plate, bound to one id."""
    return WellCapacities(
        labware_id=labware_id,
        capacities=_capacities("ABCDEFGH", range(1, 13), capacity_ul))


def _plate_384(labware_id=PLATE, capacity_ul=50.0):
    """Build the well capacities of a 384-well plate, bound to one id."""
    return WellCapacities(
        labware_id=labware_id,
        capacities=_capacities("ABCDEFGHIJKLMNOP", range(1, 25), capacity_ul))


def _empty():
    """Build a ledger with no labware registered."""
    return Liquids(contents={})


def _registered(wells=None):
    """Build a ledger with one labware registered."""
    return register(_empty(), wells or _plate())


def test_liquid_id_is_a_uuid():
    """GIVEN a liquid id
    WHEN: it is built
    THEN: it is a uuid.UUID and a non-UUID string is rejected
    """
    assert isinstance(WATER, uuid.UUID)
    assert str(WATER) == "aaaaaaaa-1111-4111-8111-111111111111"

    with pytest.raises(ValueError):
        LiquidId("water")


@pytest.mark.parametrize(
    "components,capacity",
    [({}, 0.0), ({}, 100.0), ({WATER: 50.0}, 100.0),
     ({WATER: 50.0, PBS: 50.0}, 100.0)])
def test_well_accepts_components_within_capacity(components, capacity):
    """GIVEN components whose total is within capacity
    WHEN: Well(...) is built
    THEN: the components and capacity are stored as given
    """
    well = Well(components=components, capacity_ul=capacity)

    assert dict(well.components) == components
    assert well.capacity_ul == capacity


@pytest.mark.parametrize(
    "components,capacity",
    [({WATER: -1.0}, 100.0), ({WATER: 0.0}, 100.0), ({WATER: 101.0}, 100.0),
     ({WATER: 50.0, PBS: 60.0}, 100.0), ({WATER: 1.0}, -1.0)])
def test_well_rejects_invalid_components(components, capacity):
    """GIVEN negative/zero component volumes or a total above capacity
    WHEN: Well(...) is built
    THEN: ValueError is raised
    """
    with pytest.raises(ValueError):
        Well(components=components, capacity_ul=capacity)


def test_register_seeds_every_well_empty():
    """GIVEN an unregistered labware
    WHEN: register(...) is called with its well capacities
    THEN: every well exists and is empty
    """
    liquids = _registered()

    assert volume(liquids, PLATE, "A9") == 0.0
    assert liquid_volume(liquids, PLATE, "A9", WATER) == 0.0
    assert dict(liquids.contents[PLATE]["A9"].components) == {}


def test_register_sets_the_capacity_of_every_well():
    """GIVEN well capacities
    WHEN: register(...) is called
    THEN: each well carries the capacity from those capacities
    """
    liquids = _registered()

    assert liquids.contents[PLATE]["A9"].capacity_ul == 200.0


def test_register_distinguishes_labware_by_id():
    """GIVEN two labware of the same model with distinct ids
    WHEN: both are registered and one is dispensed into
    THEN: the other is unaffected
    """
    liquids = _registered()
    liquids = register(liquids, _plate(labware_id=OTHER_PLATE))

    liquids = dispense(liquids, PLATE, "A1", WATER, 10.0)

    assert liquid_volume(liquids, PLATE, "A1", WATER) == 10.0
    assert liquid_volume(liquids, OTHER_PLATE, "A1", WATER) == 0.0


def test_register_preserves_existing_contents():
    """GIVEN a well that already holds liquid
    WHEN: its labware is registered again
    THEN: the contents are preserved and new wells are empty
    """
    liquids = Liquids(contents={PLATE: {"A1": Well({WATER: 5.0}, 200.0)}})

    liquids = register(liquids, _plate())

    assert liquid_volume(liquids, PLATE, "A1", WATER) == 5.0
    assert volume(liquids, PLATE, "A2") == 0.0


def test_register_rejects_a_different_well_set_for_the_same_id():
    """GIVEN a registered 96-well plate
    WHEN: the same id is registered with 384-well capacities
    THEN: ValueError is raised (the well sets differ)
    """
    liquids = _registered()

    with pytest.raises(ValueError):
        register(liquids, _plate_384())


def test_volume_returns_the_total_of_all_components():
    """GIVEN a well holding two reagents
    WHEN: volume(...) is called
    THEN: the sum of the component volumes is returned
    """
    liquids = Liquids(contents={
        RESERVOIR: {"A1": Well({WATER: 20.0, PBS: 30.0}, 15000.0)}})

    assert volume(liquids, RESERVOIR, "A1") == 50.0


def test_liquid_volume_returns_one_component():
    """GIVEN a well holding two reagents
    WHEN: liquid_volume(...) is called for each
    THEN: only that reagent's volume is returned
    """
    liquids = Liquids(contents={
        RESERVOIR: {"A1": Well({WATER: 20.0, PBS: 30.0}, 15000.0)}})

    assert liquid_volume(liquids, RESERVOIR, "A1", WATER) == 20.0
    assert liquid_volume(liquids, RESERVOIR, "A1", PBS) == 30.0


def test_liquid_volume_returns_zero_for_an_absent_reagent():
    """GIVEN a well holding only water
    WHEN: liquid_volume(...) is called for pbs
    THEN: 0.0 is returned
    """
    liquids = Liquids(contents={RESERVOIR: {"A1": Well({WATER: 20.0}, 15000.0)}})

    assert liquid_volume(liquids, RESERVOIR, "A1", PBS) == 0.0


def test_volume_raises_for_unknown_labware():
    """GIVEN a labware that was never registered
    WHEN: volume(...) is called
    THEN: UnknownLabwareError is raised
    """
    with pytest.raises(UnknownLabwareError):
        volume(_registered(), UNREGISTERED, "A1")


@pytest.mark.parametrize("well_name", ["M1", "A13", "AA1"])
def test_volume_raises_for_unknown_well(well_name):
    """GIVEN a registered labware and a well that does not exist in it
    WHEN: volume(...) is called
    THEN: UnknownWellError is raised
    """
    with pytest.raises(UnknownWellError):
        volume(_registered(), PLATE, well_name)


def test_dispense_adds_a_component():
    """GIVEN a registered, empty well
    WHEN: dispense(...) is called
    THEN: that reagent's volume is recorded
    """
    after = dispense(_registered(), PLATE, "A1", WATER, 10.0)

    assert liquid_volume(after, PLATE, "A1", WATER) == 10.0
    assert volume(after, PLATE, "A1") == 10.0


def test_dispense_of_two_reagents_tracks_both():
    """GIVEN a registered, empty well
    WHEN: two reagents are dispensed into it
    THEN: both components are tracked and the total is their sum
    """
    liquids = dispense(_registered(), PLATE, "A1", WATER, 2.0)
    liquids = dispense(liquids, PLATE, "A1", PBS, 3.0)

    assert liquid_volume(liquids, PLATE, "A1", WATER) == 2.0
    assert liquid_volume(liquids, PLATE, "A1", PBS) == 3.0
    assert volume(liquids, PLATE, "A1") == 5.0


def test_dispense_of_the_same_reagent_accumulates():
    """GIVEN a well already holding water
    WHEN: more water is dispensed
    THEN: the component volume is the sum
    """
    liquids = dispense(_registered(), PLATE, "A1", WATER, 2.0)
    liquids = dispense(liquids, PLATE, "A1", WATER, 3.0)

    assert liquid_volume(liquids, PLATE, "A1", WATER) == 5.0


def test_dispense_leaves_the_original_untouched():
    """GIVEN a ledger
    WHEN: dispense(...) is called
    THEN: the original ledger is unchanged
    """
    liquids = _registered()

    dispense(liquids, PLATE, "A1", WATER, 10.0)

    assert volume(liquids, PLATE, "A1") == 0.0


def test_dispense_up_to_capacity_is_allowed():
    """GIVEN a well whose components total exactly to capacity
    WHEN: the last reagent fills it to capacity
    THEN: it is accepted
    """
    liquids = dispense(_registered(), PLATE, "A1", WATER, 100.0)
    liquids = dispense(liquids, PLATE, "A1", PBS, 100.0)

    assert volume(liquids, PLATE, "A1") == 200.0


@pytest.mark.parametrize("already,requested",
                         [(195.0, 10.0), (200.0, 0.5), (0.0, 200.01)])
def test_dispense_beyond_capacity_raises(already, requested):
    """GIVEN a well that cannot hold the requested volume
    WHEN: dispense(...) is called
    THEN: WellOverflowError is raised
    """
    liquids = _registered()
    if already:
        liquids = dispense(liquids, PLATE, "A1", WATER, already)

    with pytest.raises(WellOverflowError):
        dispense(liquids, PLATE, "A1", PBS, requested)


@pytest.mark.parametrize("requested", [0.0, -5.0])
def test_dispense_rejects_non_positive_volume(requested):
    """GIVEN a non-positive volume
    WHEN: dispense(...) is called
    THEN: ValueError is raised
    """
    with pytest.raises(ValueError):
        dispense(_registered(), PLATE, "A1", WATER, requested)


def test_dispense_raises_for_unknown_labware():
    """GIVEN a labware that was never registered
    WHEN: dispense(...) is called
    THEN: UnknownLabwareError is raised
    """
    with pytest.raises(UnknownLabwareError):
        dispense(_registered(), UNREGISTERED, "A1", WATER, 10.0)


@pytest.mark.parametrize("well_name", ["M1", "A13"])
def test_dispense_raises_for_unknown_well(well_name):
    """GIVEN a registered labware and a well that does not exist in it
    WHEN: dispense(...) is called
    THEN: UnknownWellError is raised
    """
    with pytest.raises(UnknownWellError):
        dispense(_registered(), PLATE, well_name, WATER, 10.0)


def test_aspirate_reduces_the_only_component():
    """GIVEN a well holding a single reagent
    WHEN: aspirate(...) is called
    THEN: that component is reduced
    """
    liquids = dispense(_registered(), PLATE, "A1", WATER, 50.0)

    after = aspirate(liquids, PLATE, "A1", 10.0)

    assert liquid_volume(after, PLATE, "A1", WATER) == 40.0
    assert volume(after, PLATE, "A1") == 40.0


def test_aspirate_exactly_the_available_volume_empties_the_well():
    """GIVEN a well holding exactly the requested volume
    WHEN: aspirate(...) is called
    THEN: the well has no components left
    """
    liquids = dispense(_registered(), PLATE, "A1", WATER, 50.0)

    after = aspirate(liquids, PLATE, "A1", 50.0)

    assert dict(after.contents[PLATE]["A1"].components) == {}
    assert volume(after, PLATE, "A1") == 0.0


def test_aspirate_from_a_mixture_removes_proportionally():
    """GIVEN a well holding 2 uL of water and 3 uL of pbs
    WHEN: 2 uL is aspirated
    THEN: each component is reduced by the same fraction (well-mixed)
    """
    liquids = dispense(_registered(), PLATE, "A1", WATER, 2.0)
    liquids = dispense(liquids, PLATE, "A1", PBS, 3.0)

    after = aspirate(liquids, PLATE, "A1", 2.0)

    assert liquid_volume(after, PLATE, "A1", WATER) == pytest.approx(0.8)
    assert liquid_volume(after, PLATE, "A1", PBS) == pytest.approx(1.2)
    assert volume(after, PLATE, "A1") == pytest.approx(3.0)


def test_aspirate_leaves_the_original_untouched():
    """GIVEN a ledger
    WHEN: aspirate(...) is called
    THEN: the original ledger is unchanged
    """
    liquids = dispense(_registered(), PLATE, "A1", WATER, 50.0)

    aspirate(liquids, PLATE, "A1", 10.0)

    assert volume(liquids, PLATE, "A1") == 50.0


def test_aspirate_preserves_the_capacity():
    """GIVEN a well with a known capacity
    WHEN: aspirate(...) is called
    THEN: the well's capacity is unchanged
    """
    liquids = dispense(_registered(), PLATE, "A1", WATER, 50.0)

    after = aspirate(liquids, PLATE, "A1", 10.0)

    assert after.contents[PLATE]["A1"].capacity_ul == 200.0


@pytest.mark.parametrize("available,requested",
                         [(0.0, 10.0), (9.99, 10.0), (50.0, 50.01)])
def test_aspirate_more_than_available_raises(available, requested):
    """GIVEN a well holding less than the requested volume
    WHEN: aspirate(...) is called
    THEN: InsufficientVolumeError is raised
    """
    liquids = _registered()
    if available:
        liquids = dispense(liquids, PLATE, "A1", WATER, available)

    with pytest.raises(InsufficientVolumeError):
        aspirate(liquids, PLATE, "A1", requested)


@pytest.mark.parametrize("requested", [0.0, -5.0])
def test_aspirate_rejects_non_positive_volume(requested):
    """GIVEN a non-positive volume
    WHEN: aspirate(...) is called
    THEN: ValueError is raised
    """
    liquids = dispense(_registered(), PLATE, "A1", WATER, 50.0)

    with pytest.raises(ValueError):
        aspirate(liquids, PLATE, "A1", requested)


def test_aspirate_only_affects_the_target_well():
    """GIVEN several registered wells across two labware
    WHEN: aspirate(...) is called on one well
    THEN: every other well is unchanged
    """
    liquids = register(_registered(), _plate(labware_id=OTHER_PLATE))
    liquids = dispense(liquids, PLATE, "A1", WATER, 50.0)
    liquids = dispense(liquids, PLATE, "A2", PBS, 60.0)
    liquids = dispense(liquids, OTHER_PLATE, "A1", WATER, 5.0)

    after = aspirate(liquids, PLATE, "A1", 10.0)

    assert volume(after, PLATE, "A1") == 40.0
    assert volume(after, PLATE, "A2") == 60.0
    assert liquid_volume(after, OTHER_PLATE, "A1", WATER) == 5.0


def test_aspirate_raises_for_unknown_labware():
    """GIVEN a labware that was never registered
    WHEN: aspirate(...) is called
    THEN: UnknownLabwareError is raised
    """
    with pytest.raises(UnknownLabwareError):
        aspirate(_registered(), UNREGISTERED, "A1", 10.0)
