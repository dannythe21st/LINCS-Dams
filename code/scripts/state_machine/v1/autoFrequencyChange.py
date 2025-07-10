import json
from math import sqrt
import paho.mqtt.client as mqtt
from transitions import Machine
import signal
import sys
import time
from functools import partial
from logger import DualLogger
from datetime import datetime

MQTT_BROKER = "172.XX.XX.X" # CHANGE ME
MQTT_PORT = 1883            # Default port
BROKER_USERNAME = "username"  # CHANGE ME
BROKER_PW = "password"     # CHANGE ME

# MQTT Topics
TILT_TOPIC = "inc_data/I1"
VIBRATION_TOPIC = "readings/accel_data"
DISTANCE_TOPIC = "lidar_data/"
ENERGY_SAVING_TOPIC = "IPI/lowpower"
IPI_FREQUENCY_UPDATE_TOPIC = "commands/IPI/frequency"
LIDAR_FREQUENCY_UPDATE_TOPIC = "dvm/lidar_freq"
ACCEL_FREQUENCY_UPDATE_TOPIC = "dvm/accel_freq"
WATER_LEVEL_WARNINGS_TOPIC = "warnings/waterlevel"
VIBRATION_WARNINGS_TOPIC = "warnings/vibration"

# IPI frequency "levels"
ENERGY_SAVING_FREQUENCY = 3600000     # every 7 days
BASE_FREQUENCY = 10000             # every 10 seconds
STAGE_1_FREQUENCY = 8000           # every 8 second
STAGE_2_FREQUENCY = 6000           # every 6 second
STAGE_3_FREQUENCY = 4000           # every 4 second
STAGE_4_FREQUENCY = 1000           # every second - emergency situation (fast water level change/vibrations)

# Distance/water level values
DISTANCE_THRESHOLD = 100
DISTANCE_DEFAULT_FREQUENCY = 10000   # every 10 seconds
DISTANCE_ALERT_FREQUENCY = 4000     # every 4 seconds
DISTANCE_ALARM_FREQUENCY = 3000     # every 3 seconds

# Distance between the sensor and the water in cm
MIN_WATER_DISTANCE = 5      # Maximum water level
MAX_WATER_DISTANCE = 22     # Minimum water level

dist_frequency_list = [DISTANCE_DEFAULT_FREQUENCY, DISTANCE_ALERT_FREQUENCY, DISTANCE_ALARM_FREQUENCY]

# Sensor settings
NUMBER_IPI_NODES = 1    # number of active sensor nodes in the inclinometer

# Thresholds
IPI_THRESHOLD_LOW = 0.35
IPI_THRESHOLD_MID = 0.55
IPI_THRESHOLD_HIGH = 0.7

DISTANCE_RATE_LOW = 0.35
DISTANCE_RATE_MID = 0.7

sys.stdout = DualLogger("output_log.txt")

class AdaptiveFrequencyModule:

    states = ["energy_saving", "base_frequency", "low_frequency", "high_frequency", "max_frequency", "emergency_frequency"]

    dist_frequency_list_current = 0

    start_time = time.time()

    def __init__(self):
        print("\n\n########## [BEHAVIORAL MODULE SETUP] ##########\n")
        print("-> Booting up the script...")

        # MQTT Client start
        self.client = mqtt.Client(protocol=mqtt.MQTTv5)
        self.client.username_pw_set(BROKER_USERNAME, BROKER_PW)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            print(f"-> Connected successfully to the MQTT broker running on {MQTT_BROKER}:{MQTT_PORT}.")
        except Exception as e:
            print(f"-> Failed to connect - {e}")
        
        self.client.loop_start()

        self.last_tilt_reading_mat = [[0.0 for _ in range(3)] for _ in range(NUMBER_IPI_NODES)]
        self.reading_frequency = BASE_FREQUENCY

        self.last_dist_reading = None
        self.dist_frequency = DISTANCE_DEFAULT_FREQUENCY

        self.machine = Machine(model=self, states=self.states, initial="base_frequency")
 
        # State transitions definition
        # Source - base frequency state
        self.machine.add_transition(trigger="small_inc", source="base_frequency", dest="low_frequency")
        self.machine.add_transition(trigger="medium_inc", source="base_frequency", dest="high_frequency")
        self.machine.add_transition(trigger="big_inc", source="base_frequency", dest="max_frequency")
        self.machine.add_transition(trigger="emergency_situation", source="base_frequency", dest="emergency_frequency")

        # Source - low frequency state
        self.machine.add_transition(trigger="small_inc", source="low_frequency", dest="high_frequency")
        self.machine.add_transition(trigger="medium_inc", source="low_frequency", dest="max_frequency")
        self.machine.add_transition(trigger="big_inc", source="low_frequency", dest="max_frequency")
        self.machine.add_transition(trigger="small_dec", source="low_frequency", dest="base_frequency")
        self.machine.add_transition(trigger="emergency_situation", source="low_frequency", dest="emergency_frequency")

        # Source - high frequency state
        self.machine.add_transition(trigger="small_inc", source="high_frequency", dest="max_frequency")
        self.machine.add_transition(trigger="medium_inc", source="high_frequency", dest="max_frequency")
        self.machine.add_transition(trigger="big_inc", source="high_frequency", dest="max_frequency")
        self.machine.add_transition(trigger="emergency_situation", source="high_frequency", dest="emergency_frequency")

        self.machine.add_transition(trigger="small_dec", source="high_frequency", dest="low_frequency")
        self.machine.add_transition(trigger="medium_dec", source="high_frequency", dest="base_frequency")
        self.machine.add_transition(trigger="big_dec", source="high_frequency", dest="base_frequency")

        # Source - max frequency state
        self.machine.add_transition(trigger="small_dec", source="max_frequency", dest="high_frequency")
        self.machine.add_transition(trigger="medium_dec", source="max_frequency", dest="low_frequency")
        self.machine.add_transition(trigger="big_dec", source="max_frequency", dest="base_frequency")
        self.machine.add_transition(trigger="small_inc", source="max_frequency", dest="emergency_frequency")
        self.machine.add_transition(trigger="emergency_situation", source="max_frequency", dest="emergency_frequency")

        # Source - emergency frequency state
        # Leave it at a high frequency for safety, if the situation really is stable the frequency decreases over time by itself
        self.machine.add_transition(trigger="small_dec", source="emergency_frequency", dest="high_frequency") 

        # Energy savings state transition
        self.machine.add_transition(trigger="lowpower", source=["base_frequency","low_frequency", "high_frequency", "max_frequency"], dest="energy_saving")
        self.machine.add_transition(trigger="normalmode", source="energy_saving", dest="base_frequency")

        self.machine.add_transition(trigger="medium_inc", source="energy_saving", dest="high_frequency")
        self.machine.add_transition(trigger="big_inc", source="energy_saving", dest="max_frequency")
        self.machine.add_transition(trigger="emergency_situation", source="energy_saving", dest="emergency_frequency")

        # Register functions triggered on entering the states
        self.machine.on_enter_energy_saving(partial(self.update_reading_frequency, ENERGY_SAVING_FREQUENCY))
        self.machine.on_enter_base_frequency(partial(self.update_reading_frequency, BASE_FREQUENCY))
        self.machine.on_enter_low_frequency(partial(self.update_reading_frequency, STAGE_1_FREQUENCY))
        self.machine.on_enter_high_frequency(partial(self.update_reading_frequency, STAGE_2_FREQUENCY))
        self.machine.on_enter_max_frequency(partial(self.update_reading_frequency, STAGE_3_FREQUENCY))
        self.machine.on_enter_emergency_frequency(partial(self.update_reading_frequency, STAGE_4_FREQUENCY))

        print("-> State Machine setup finished.")
        print("-> Script setup finished.\n")


    def update_reading_frequency(self, newFreq):
        self.client.publish(topic=IPI_FREQUENCY_UPDATE_TOPIC, payload=str(newFreq), qos=2, retain=False)
        self.reading_frequency = newFreq

    def update_lidar_frequency(self, newFreq):
        self.client.publish(topic=LIDAR_FREQUENCY_UPDATE_TOPIC, payload=str(newFreq), qos=2, retain=False)
        self.dist_frequency = newFreq

    def update_accel_frequency(self, newFreq):
        self.client.publish(topic=ACCEL_FREQUENCY_UPDATE_TOPIC, payload=str(newFreq), qos=2, retain=False)
        self.dist_frequency = newFreq

    def publish_warning(self, tpc, message):
        payload_data = {"message": message}
        self.client.publish(topic=tpc, payload=json.dumps(payload_data), qos=2, retain=False)


    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    def on_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe(TILT_TOPIC)
        print(f"-> Subscribed to topic: {TILT_TOPIC}")
        client.subscribe(ENERGY_SAVING_TOPIC)
        print(f"-> Subscribed to topic: {ENERGY_SAVING_TOPIC}\n")
        client.subscribe(DISTANCE_TOPIC)
        print(f"-> Subscribed to topic: {DISTANCE_TOPIC}")
        client.subscribe(VIBRATION_TOPIC)
        print(f"-> Subscribed to topic: {VIBRATION_TOPIC}")
        print("\n########## [BEHAVIORAL MODULE SETUP COMPLETE] ##########\n\n")


    def on_message(self, client, userdata, message):
        try:
            elapsed = time.time() - self.start_time
            print(f"Current time: {datetime.now().strftime("%H:%M:%S")} || Started {elapsed:.1f} ago.\n")
            data = json.loads(message.payload.decode())
            if message.topic == ENERGY_SAVING_TOPIC:
                self.handle_low_energy_mode(data)

            elif message.topic == TILT_TOPIC:
                self.handle_tilt_readings(data)

            elif message.topic == DISTANCE_TOPIC:
                self.handle_distance_readings(data)

            else: # topic = readings/accel_data
                self.handle_vibration_readings(data)

        except Exception as e:
            print(f"Error processing MQTT message: {e}\n")


    def populate_new_readings_mat(self, new_readings_arr):
        new_tilt_readings_mat = [[0.0 for _ in range(3)] for _ in range(NUMBER_IPI_NODES)]
        #TODO REPOR NUMBER-1
        for node_data_json in new_readings_arr:
            node_number = node_data_json.get("n", None)
            node_ax = node_data_json.get("aX", None)
            node_ay = node_data_json.get("aY", None)
            node_az = node_data_json.get("aZ", None)
            new_tilt_readings_mat[node_number-1][0] = node_ax if node_ax is not None else print("Node " + node_number + " has an invalid aX value (None)")
            new_tilt_readings_mat[node_number-1][1] = node_ay if node_ay is not None else print("Node " + node_number + " has an invalid aY value (None)")
            new_tilt_readings_mat[node_number-1][2] = node_az if node_az is not None else print("Node " + node_number + " has an invalid aZ value (None)")

        return new_tilt_readings_mat

    # To calculate the difference between two consecutive readings the Euclidean distance between two 3D vectors is used.
    # It's a single scalar value that tells you how much has the sensor’s perceived direction of gravity changed.
    # This value is computed for each node in the inclinometer. The highest value is returned, as it represents the biggest
    # change in inclination in the whole system.
    def compare_readings(self, new_tilt_readings_mat, last_tilt_reading_mat):
        delta_calc = [0.0] * NUMBER_IPI_NODES
        for pos in range(0,NUMBER_IPI_NODES):
            delta_calc[pos] = sqrt((new_tilt_readings_mat[pos][0] - last_tilt_reading_mat[pos][0])** 2 + 
                                   (new_tilt_readings_mat[pos][1] - last_tilt_reading_mat[pos][1])** 2 + 
                                   (new_tilt_readings_mat[pos][2] - last_tilt_reading_mat[pos][2])** 2)
        print(f"Old readings: {last_tilt_reading_mat}\n")
        print(f"New Readings: {new_tilt_readings_mat}\n")
        return max(delta_calc)
    
    def handle_low_energy_mode(self, data):
        toggleLowFrequency = data.get("toggle", None)

        if toggleLowFrequency is None:
            print("Received an empty message on topic IPI/lowpower.")
            return

        toggleLowFrequency = parse_boolean(toggleLowFrequency)

        print("[UPDATE - Low-frequency mode]")
        if toggleLowFrequency > 0:
            if self.machine.get_state(self.state).name == "energy_saving":
                print(f"Low-frequency mode is already ON.\n\n")

            self.trigger("lowpower")
            print(f"Low-frequency mode ON. New readings every {self.reading_frequency/86400} days.\n\n")
        elif toggleLowFrequency == 0:
            if self.machine.get_state(self.state).name != "energy_saving":
                print(f"Low-frequency mode is already OFF.\n\n")

            self.trigger("normalmode")
            print("Low-frequency mode OFF. Returning to base frequency.\n")
        else:
            print("Invalid value.\n")
        return
        
    def handle_tilt_readings(self, data):
        # Readings come as:
        # {"inc_number":1,"inc_code":"I1","inc_description":"Test inclinometer n. 1","sensors":[{"n":1,"aX":18.19878,"aY":-62.85292,"aZ":-19.18011}]}
        
        print("[UPDATE - New INC Reading]")
        new_tilt_reading_list = data.get("sensors", None) # JSON array
        if new_tilt_reading_list is None:
            print("Received an invalid (empty) message on topic readings/inc_data.\n")
            return

        if all(val == 0.0 for row in self.last_tilt_reading_mat for val in row) :
            self.last_tilt_reading_mat = self.populate_new_readings_mat(new_tilt_reading_list)
            print(f"Initial IPI reading received!\n")
            return
        
        new_tilt_reading_mat = self.populate_new_readings_mat(new_tilt_reading_list)
        print(new_tilt_reading_mat)
        biggestChange:float = self.compare_readings(new_tilt_reading_mat, self.last_tilt_reading_mat)

        print(f"Largest vectorial change: {biggestChange}\n\n")
        
        # State change logic
        # First if-statement - If the situation is relatively stable we can reduce the frequency
        # On the outer else-statement, small changes between 0.15 and 0.35 do NOT trigger the system to automatically leave the low-power mode,
        # only differences over 0.35 force the system out of this mode. This is done to compromise between safety and energy efficiency.
        if 0 <= biggestChange < IPI_THRESHOLD_LOW:
            if self.machine.get_state(self.state).name != "base_frequency" and self.machine.get_state(self.state).name != "energy_saving":
                self.trigger("small_dec")
        else:
            if self.machine.get_state(self.state).name != "emergency_frequency": # because you cant go higher than emergency frequency state
                if self.machine.get_state(self.state).name == "max_frequency":   # because from max freq you can only have a small inc to the last state
                    self.trigger("small_inc")
                else:
                    if biggestChange < IPI_THRESHOLD_MID and self.machine.get_state(self.state).name != "energy_saving":
                        self.trigger("small_inc")
                    elif IPI_THRESHOLD_MID <= biggestChange < IPI_THRESHOLD_HIGH:
                        self.trigger("medium_inc")
                    else:
                        self.trigger("big_inc")

        self.last_tilt_reading_mat = new_tilt_reading_mat
        print(f" > Current state is {self.machine.get_state(self.state).name.upper()}.\n")
        print(f" > New readings every {self.reading_frequency/1000} seconds.\n")
        print("#################################\n\n")


    def handle_distance_readings(self, data):
        # Readings come as:
        # {"mod_code":"DVM1", "distance":37, "signal_strength":9715, "temperature":33}
        new_dist_reading = data.get("distance", None)

        if new_dist_reading is None:
            print("Received an invalid (empty) message on topic readings/lidar_data.\n")
            return

        new_dist_reading = int(new_dist_reading)
        print(f"New distance reading - {new_dist_reading} cm.")
        print(f"Last distance reading - {self.last_dist_reading} cm.")

        # If it's the first reading, just store it
        if self.last_dist_reading is None:
            self.last_dist_reading = new_dist_reading
            print(f"Initial distance reading received!\n")
            return
        
        elapsed = time.time() - self.start_time
        nivel_pleno_armazenamento = True if (new_dist_reading == MIN_WATER_DISTANCE) else False
        nivel_maxima_cheia = True if (new_dist_reading < MIN_WATER_DISTANCE) else False

        if new_dist_reading >= MAX_WATER_DISTANCE: # Max distance = lowest safe water level
            message = f"[+{elapsed:.1f}s][WARNING] Water levels are critically LOW."
            self.publish_warning(WATER_LEVEL_WARNINGS_TOPIC, message)
        elif nivel_pleno_armazenamento: # Min distance = highest safe water level
            message = f"[+{elapsed:.1f}s][WARNING] Water level has reached its maximum safe value."
            self.publish_warning(WATER_LEVEL_WARNINGS_TOPIC, message)
            if self.machine.get_state(self.state).name != "emergency_frequency":
                    self.trigger("emergency_situation")
            print(message)
        elif nivel_maxima_cheia: #new_dist_reading > MIN_WATER_DISTANCE -- Over the safe water-level limit
            message = f"[+{elapsed:.1f}s][ALARM] Water levels are critically HIGH."
            self.publish_warning(WATER_LEVEL_WARNINGS_TOPIC, message)
            if self.machine.get_state(self.state).name != "emergency_frequency":
                self.trigger("emergency_situation")
            print(message)
            

        # change-rate measured in cm/min
        distance_change_rate = (new_dist_reading-self.last_dist_reading)/((self.dist_frequency/1000)*60)
        print(f" > Distance change rate {distance_change_rate} cm/min.\n")

        alarm_rate_limit = 0

        if distance_change_rate >= 0 : # Filling the tank - max rate = 1.9 cm/s
            alarm_rate_limit = 1.75
        else: # Emptying the tank - max rate = 1.36 cm/s
            alarm_rate_limit = 1.25

        if not (nivel_pleno_armazenamento and nivel_maxima_cheia):
            if 0 <= distance_change_rate < DISTANCE_RATE_LOW: # Stable situation
                if self.dist_frequency_list_current > 0:
                    self.dist_frequency_list_current -= 1
                    newFreq = dist_frequency_list[self.dist_frequency_list_current] # Lower lidar frequenct
                    self.dist_frequency = newFreq
                    self.update_lidar_frequency(newFreq)
                    print(f" > Current state is {self.machine.get_state(self.state).name.upper()}.\n")
                    print(f" > Lowering distance readings rate to {self.dist_frequency/1000} seconds, as the situation is stable. \n\n")

            else:
                if distance_change_rate < DISTANCE_RATE_MID:
                    if self.dist_frequency_list_current < 2:
                        self.dist_frequency_list_current+=1 # Increase lidar frequency
                        newFreq = dist_frequency_list[self.dist_frequency_list_current]
                        self.dist_frequency = newFreq
                        self.update_lidar_frequency(newFreq)

                elif DISTANCE_RATE_MID <= distance_change_rate < alarm_rate_limit:
                    if self.dist_frequency_list_current < 2:
                        self.dist_frequency_list_current+=1 # Increase lidar frequency
                        newFreq = dist_frequency_list[self.dist_frequency_list_current]
                        self.dist_frequency = newFreq
                        self.update_lidar_frequency(newFreq)

                    # Increase IPI frequency as water level is rising at a 
                    # slightly concerning rate
                    if self.machine.get_state(self.state).name != "emergency_frequency":
                        self.trigger("small_inc")
                    
                    print(f" > Current state is {self.machine.get_state(self.state).name.upper()} due to a slightly concerning water level change.\n")

                else:
                    if self.dist_frequency_list_current < 2:
                        self.dist_frequency_list_current+=1 # Increase lidar frequency
                        newFreq = dist_frequency_list[self.dist_frequency_list_current]
                        self.dist_frequency = newFreq
                        self.update_lidar_frequency(newFreq)
                    
                    # Greatly increase IPI frequency as water level is rising at an alarming rate
                    if self.machine.get_state(self.state).name != "emergency_frequency":
                        self.trigger("emergency_situation")
                    
                    print(f" > Current state is {self.machine.get_state(self.state).name.upper()} due to a concerningly fast water level change.")
                
        print(f" > New IPI reading every {self.reading_frequency/1000} seconds.\n")
        print(f" > New distance readings every {self.dist_frequency/1000} seconds. \n")
        print("#################################\n\n")
        self.last_dist_reading = new_dist_reading
        return

    def handle_vibration_readings(self, data):
        # Reading come as 
        # DVM1,host=51f801b5d916,topic=accel_data/ aX=-0.857143,aY=-0.095238,aZ=0,mod_code="DVM1" 1742816476743282844

        aX = data.get("aX", None)
        aY = data.get("aY", None)
        aZ = data.get("aZ", None)

        if aX is None or aY is None or aZ is None:
            print("Received an invalid (empty) message on topic readings/accel_data.\n")
            return
        
        aX = float(aX)
        aY = float(aY)
        aZ = float(aZ)

        # Subtract 1 as in a perfectly still environment, the sensor will still pick up gravity
        net_vibration = sqrt(aX**2 + aY**2 + aZ**2) - 1.0

        if net_vibration <= 0.3:
            print("Minor vibration detected.")
        elif 0.3 < net_vibration <= 0.5:
            if self.machine.get_state(self.state).name != "emergency_frequency":    
                self.trigger("small_inc")
                print(f" > Current state is {self.machine.get_state(self.state).name.upper()} due to the mild vibrations felt.\
                          New IPI reading every {self.reading_frequency/3600} hours.\n\n")
        else: # net_vibration > 0.5
            if self.machine.get_state(self.state).name != "emergency_frequency":
                    self.trigger("emergency_situation")
                    print(f" > Current state is {self.machine.get_state(self.state).name.upper()} due to the strong vibrations felt.\
                          New IPI reading every {self.reading_frequency/3600} hours.\n\n")
        return

# Auxiliary function to parse values posted on the low-frequency toggling topic. Used to support
# different types of "true" values, written in different ways (capital letters or not, whitespaces on both ends).
def parse_boolean(val: str):
    if val.strip().lower() == "false":
        return 0
    elif val.strip().lower() == "true":
        return 1
    return -1

def graceful_exit(signum, frame):
        print("->[BEHAVIORAL MODULE]: Shutting down...\n")
        adaptive_frequency_module.client.loop_stop()
        adaptive_frequency_module.client.disconnect()
        sys.exit(0)

if __name__ == "__main__":
    adaptive_frequency_module = AdaptiveFrequencyModule()
    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)

    # Keep script alive until ctrl+c 
    try:
        while True:
            time.sleep(1)  
    except KeyboardInterrupt:
        graceful_exit(None, None)


class DistanceMeasurement:
    timestamp: int
    value: float