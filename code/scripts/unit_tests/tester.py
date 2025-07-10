import time
import pytest
from unittest.mock import MagicMock
from autoFrequencyChange_v2 import AdaptiveFrequencyModule, TILT_TOPIC, DISTANCE_TOPIC, VIBRATION_TOPIC


# To test the script run: pytest tester.py -v > ./tests/test_results_ID.txt

@pytest.fixture
def module(mocker):
    mock_client = MagicMock()
    mod = AdaptiveFrequencyModule(min_level=0,
                intermediate_level=6,
                max_level=17,
                offset=3,
                distance_rate_threshold=0.9,
                tilt_x_min_threshold = -100,
                tilt_x_max_threshold = 100,
                tilt_y_min_threshold = -100,
                tilt_y_max_threshold = 100,
                tilt_rate_threshold = 15,
                mqtt_client=mock_client)
    return mod

#########
#
# WaterLevel = 22+offset-(distance)
#
#########

def test_initial_state(module):
    assert module.state == "live_storage"


#### Basic single-transition tests ####

# LS -> Stability (by tilt limit)
def test_tilt_reading_transition_to_stability(module):
    # Simulate initial reading
    initial_msg = {
        "sensors": [{"n": 3, "aX": 1.0, "aY": 1.0, "aZ": 90.00}]
    }

    module.last_tilt_reading_time -= 60
    module.handle_tilt_readings(initial_msg)

    new_msg = {
        "sensors": [{"n": 3, "aX": 120.0, "aY": 120.0, "aZ": 120.0}]
    }
    module.last_tilt_reading_time -= 30
    module.handle_tilt_readings(new_msg)
    assert module.state == "stability"

# LS -> Stability (by tilt limit with 4 nodes)
def test_tilt_reading_transition_to_stability_multi_node(module):
    # Simulate initial reading
    initial_msg = {
        "sensors": [{"n": 1, "aX": 1.0, "aY": 1.0, "aZ": 90.00},
                    {"n": 2, "aX": 1.0, "aY": 1.0, "aZ": 90.00},
                    {"n": 3, "aX": 1.0, "aY": 1.0, "aZ": 90.00},
                    {"n": 4, "aX": 1.0, "aY": 1.0, "aZ": 90.00}]
    }

    module.last_tilt_reading_time = time.time() - 15
    module.handle_tilt_readings(initial_msg)
    assert module.state == "live_storage"

    new_msg = {
        "sensors": [{"n": 1, "aX": 1.0, "aY": 1.0, "aZ": 90.00},
                    {"n": 2, "aX": 120.0, "aY": 120.0, "aZ": 95.00},
                    {"n": 3, "aX": 1.0, "aY": 1.0, "aZ": 90.00},
                    {"n": 4, "aX": 1.0, "aY": 1.0, "aZ": 90.00}]
    }
    module.last_tilt_reading_time = time.time() - 1
    module.handle_tilt_readings(new_msg)
    assert module.state == "stability"

# LS -> Stability (by tilt change rate)
def test_tilt_reading_transition_to_stability_by_tilt_rate(module):
    # Simulate initial reading
    initial_msg = {
        "sensors": [{"n": 1, "aX": 1.0, "aY": 1.0, "aZ": 90.00},
                    {"n": 2, "aX": 1.0, "aY": 1.0, "aZ": 90.00},
                    {"n": 3, "aX": 1.0, "aY": 1.0, "aZ": 90.00},
                    {"n": 4, "aX": 1.0, "aY": 1.0, "aZ": 90.00}]
    }

    module.last_tilt_reading_time = time.time() - 2  # simulate 2 seconds ago
    module.handle_tilt_readings(initial_msg)
    assert module.state == "live_storage"

    new_msg = {
        "sensors": [{"n": 1, "aX": 1.0, "aY": 1.0, "aZ": 90.00},
                    {"n": 2, "aX": 120.0, "aY": 120.0, "aZ": 95.00},
                    {"n": 3, "aX": 1.0, "aY": 1.0, "aZ": 90.00},
                    {"n": 4, "aX": 1.0, "aY": 1.0, "aZ": 90.00}]
    }
    module.last_tilt_reading_time = time.time() - 1
    module.handle_tilt_readings(new_msg)
    assert module.state == "stability"

# LS -> Stability (by fast water level decrease)
def test_tilt_reading_transition_to_stability_by_rate(module):
    module.state = "live_storage"
    module.last_water_level = 5
    module.last_reading_time = time.time() - 0.5  # simulate half a second ago

    test_msg = {
        "distance": 23     # WL = 2
    }
    # Negative AND fast variation = ls to stability
    module.handle_distance_readings(test_msg)
    assert module.state == "stability"

# LS -> full (by water level)
def test_distance_transition_to_full(module):
    module.state = "live_storage"
    module.last_water_level = 9

    first_distance_msg = {
        "distance": 10   # WL = 15
    }
    module.handle_distance_readings(first_distance_msg)
    assert module.state == "full"

# full -> flood (by water level)
def test_distance_transition_to_flood(module):
    module.state = "full"
    module.last_water_level = 16

    new_msg = {
        "distance": 3   # WL = 22
    }

    module.handle_distance_readings(new_msg)
    assert module.state == "flood"

# full -> flood (by water level rate)
def test_distance_transition_to_flood_by_rate(module):
    module.state = "full"
    module.last_water_level = 8
    module.last_reading_time = time.time() - 0.5

    test_msg = {
        "distance": 9   # WL = 16
    }

    module.handle_distance_readings(test_msg)
    assert module.state == "flood"

# flood -> full (by water level)
def test_distance_flood_to_full(module):
    module.state = "flood"
    new_msg = {
        "distance": 14   # WL = 11
    }
    module.handle_distance_readings(new_msg)
    assert module.state == "full"

# full -> ls (by water level)
def test_distance_full_to_ls(module):
    module.state = "full"
    module.last_water_level = 10
    new_msg = {
        "distance": 20   # WL = 5
    }
    module.handle_distance_readings(new_msg)
    assert module.state == "live_storage"

# Stability -> ls (by tilt)
def test_tilt_stability_to_ls(module):
    module.state = "stability"

    # Set 1st reading as base for comparison
    initial_msg = {
        "sensors": [{"n": 3, "aX": 1.0, "aY": 1.0, "aZ": 90.00}]
    }

    module.last_tilt_reading_time = time.time() - 60
    module.handle_tilt_readings(initial_msg)
    # make sure initial state is set as stability
    assert module.state == "stability"

    # same reading = stable situation
    new_msg = {
        "sensors": [{"n": 3, "aX": 1.0, "aY": 1.0, "aZ": 90.00}]
    }
    module.last_tilt_reading_time = time.time() - 30
    module.handle_tilt_readings(new_msg)
    assert module.state == "live_storage"

# Stability -> ls (by stable water level change rate)
def test_distance_stability_to_ls(module):
    module.state = "stability"
    module.last_water_level = 4
    module.last_reading_time = time.time() - 75 # last reading 1m15s ago

    test_msg = {
        "distance": 20   # WL = 5
    }

    module.handle_distance_readings(test_msg)
    assert module.state == "live_storage"

    # same reading = stable situation
    new_msg = {
        "sensors": [{"n": 3, "aX": 1.0, "aY": 1.0, "aZ": 90.00}]
    }
    module.handle_tilt_readings(new_msg)
    assert module.state == "live_storage"



# First reading already exceeds "full" limit
def test_distance_transition_to_full_first_reading(module):
    module.state = "live_storage"
    module.last_water_level = None
    module.last_reading_time = module.start_time

    new_msg = {
        "distance": 14
    }
    module.handle_distance_readings(new_msg)
    assert module.state == "full"

# First reading already exceeds "flood" limit
def test_distance_transition_to_full_first_reading(module):
    module.state = "live_storage"
    module.last_water_level = None
    module.last_reading_time = module.start_time

    new_msg = {
        "distance": 3   # WL = 22
    }
    module.handle_distance_readings(new_msg)
    assert module.state == "flood"

#### Multi-transition tests ####

def test_tilt_ls_stability_ls(module):
    module.state = "live_storage"
    initial_msg = {
        "sensors": [{"n": 3, "aX": 1.0, "aY": 1.0, "aZ": 90.00}]
    }
    module.last_tilt_reading_time = time.time() - 60
    module.handle_tilt_readings(initial_msg)

    new_msg = {
        "sensors": [{"n": 3, "aX": 120.0, "aY": 120.0, "aZ": 120.0}]
    }
    module.last_tilt_reading_time = time.time() - 30
    module.handle_tilt_readings(new_msg)
    assert module.state == "stability"

    # same message twice, so variation is 0 = stable situation and go back to ls
    module.last_tilt_reading_time = time.time() - 10
    module.handle_tilt_readings(new_msg)
    assert module.state == "live_storage"

def test_distance_ls_full_flood(module):
    module.state = "live_storage"
    module.last_water_level = None

    first_distance_msg = {
        "distance": 10
    }
    module.handle_distance_readings(first_distance_msg)
    assert module.state == "full"

    new_msg = {
        "distance": 3
    }
    module.handle_distance_readings(new_msg)
    assert module.state == "flood"


# def test_vibration_behavior(module):
#     module.state = "live_storage"
#     mild_vibration = {"aX": 0.3, "aY": 0.3, "aZ": 0.3}
#     module.handle_vibration_readings(mild_vibration)

#     strong_vibration = {"aX": 1.0, "aY": 1.0, "aZ": 1.0}
#     module.handle_vibration_readings(strong_vibration)

    # Since "emergency_frequency" isn't a defined state in your FSM yet, this test is illustrative.
    # You can assert side effects like publish being called or log messages instead
