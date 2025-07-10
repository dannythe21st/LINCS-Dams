import json
from math import acos, degrees, sqrt
import paho.mqtt.client as mqtt
from transitions import Machine
import signal
import sys
import time
from functools import partial
from logger import DualLogger
from datetime import datetime
import csv
from math import acos, degrees, sqrt

# State Machine Constants
#states
LIVE_STORAGE = "live_storage"
FULL = "full"
FLOOD = "flood"
STABILITY = "stability"
COLLAPSE = "collapse"

#triggers
TO_LIVE_STORAGE = "to_ls"
TO_FULL = "to_full"
TO_FLOOD = "to_flood"
TO_STABILITY = "to_stability"
TO_COLLAPSE = "to_collapse"

# Output Strings
SUBBED_TO="-> Subscribed to topic"

# MQTT Settings
MQTT_BROKER = "172.XX.XX.X" # CHANGE ME
MQTT_PORT : int = 1883      # Default port
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
LIVE_STORAGE_FREQUENCY = 10000  # every 10 seconds
FULL_FREQUENCY = 5000           # every 5 second
STABILITY_FREQUENCY = 4000      # every 4 second
FLOOD_FREQUENCY = 1000          # every second

# Distance/water level values
DISTANCE_DEFAULT_FREQUENCY = 10000   # every 10 seconds
DISTANCE_ALERT_FREQUENCY = 5000     # every 4 seconds
DISTANCE_ALARM_FREQUENCY = 2000     # every 3 seconds

# Distance between the sensor and the water in cm
MIN_WATER_DISTANCE = 5      # Maximum water level
MAX_WATER_DISTANCE = 22     # Minimum water levelSS

# IPI settings
NUMBER_IPI_NODES = 4    # number of active sensor nodes in the inclinometer

sys.stdout = DualLogger("output_log.txt")

class AdaptiveFrequencyModule:

    states = [LIVE_STORAGE, STABILITY, FULL, FLOOD, COLLAPSE]

    last_water_level = None

    start_time = time.time()

    # Readings timestamps
    last_lidar_reading_time = 0
    last_tilt_reading_time = 0

    # flag to avoid iterating over structure multiple times
    first_tilt_read = True

    # Trigger flags
    isFast = False
    within_tilt_limits = True
    isMoving = False

    # Set state machine thresholds here
    def __init__(self,min_level=6,
                 intermediate_level=10,
                 max_level=12,
                 offset=3,
                 distance_rate_threshold = 100,
                 tilt_x_min_threshold = -9,
                 tilt_x_max_threshold = 10,
                 tilt_y_min_threshold = -1,
                 tilt_y_max_threshold = 6,
                 max_tilt_change = 5,
                 tilt_rate_threshold = 1500,
                 mqtt_client=None):
        
        print("\n\n########## [BEHAVIORAL MODULE SETUP] ##########\n")
        print("-> Booting up the script...")

        
        # Water level thresholds
        self.MIN_LEVEL = min_level
        self.INTERMEDIATE_LEVEL = intermediate_level
        self.MAX_LEVEL = max_level

        # To account for LiDAR initial error
        self.OFFSET = offset
        
        # Max water level change rate
        self.DISTANCE_RATE_THRESHOLD = distance_rate_threshold
        
        # Angle limits for each axis
        self.TILT_X_MIN_THRESHOLD = tilt_x_min_threshold
        self.TILT_X_MAX_THRESHOLD = tilt_x_max_threshold
        self.TILT_Y_MIN_THRESHOLD = tilt_y_min_threshold
        self.TILT_Y_MAX_THRESHOLD = tilt_y_max_threshold
        self.MAX_TILT_CHANGE = max_tilt_change

        # Max IPI tilt change rate
        # 15% margin, only triggers alarm if the rate of deformation is 15% over the defined limit
        self.TILT_RATE_THRESHOLD = tilt_rate_threshold*1.15 

        print(f"-> Script Settings\n")
        print(f"[Water Level Thresholds]: Min = {min_level} | Mid = {intermediate_level} | Max = {max_level} | Max_rate = {distance_rate_threshold} | Offset = {offset} \n")
        print(f"[IPI Thresholds]: Min_x = {tilt_x_min_threshold} | Max_x = {tilt_x_max_threshold} | Min_y = {tilt_y_min_threshold} | Max_y = {tilt_y_max_threshold} | \
              Max_change = {max_tilt_change} | Max_rate = {tilt_rate_threshold} \n\n")

        # MQTT Client start
        self.client = mqtt_client or mqtt.Client(protocol=mqtt.MQTTv5)
        self.client.username_pw_set(BROKER_USERNAME, BROKER_PW)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            print(f"-> Connected successfully to the MQTT broker running on {MQTT_BROKER}:{MQTT_PORT}.")
        except Exception as e:
            print(f"-> Failed to connect - {e}")
        
        self.client.loop_start()

        # IPI reading matrix [1,2,3,4][x,y,z]
        self.last_tilt_reading_mat = [[0.0 for _ in range(3)] for _ in range(NUMBER_IPI_NODES)]
        self.base_tilt_reading_mat = [[0.0 for _ in range(3)] for _ in range(NUMBER_IPI_NODES)]
        self.reading_frequency = LIVE_STORAGE_FREQUENCY

        self.dist_frequency = DISTANCE_DEFAULT_FREQUENCY

        self.frequency_log = []
        self.water_level_log = []
        self.ipi_log = []

        self.machine = Machine(model=self, states=self.states, initial=LIVE_STORAGE)
 
        # State transitions definition
        # Source - Live Storage state
        self.machine.add_transition(trigger=TO_FULL, source=LIVE_STORAGE, dest=FULL)
        self.machine.add_transition(trigger=TO_FLOOD, source=LIVE_STORAGE, dest=FLOOD)
        self.machine.add_transition(trigger=TO_STABILITY, source=LIVE_STORAGE, dest=STABILITY)

        # Source - Full state
        self.machine.add_transition(trigger=TO_FLOOD, source=FULL, dest=FLOOD)
        self.machine.add_transition(trigger=TO_LIVE_STORAGE, source=FULL, dest=LIVE_STORAGE)
        
        # Source - Stability state
        self.machine.add_transition(trigger=TO_LIVE_STORAGE, source=STABILITY, dest=LIVE_STORAGE)
        
        # Source - Flood state
        self.machine.add_transition(trigger=TO_FULL, source=FLOOD, dest=FULL)


        # Register functions triggered on entering the states
        self.machine.on_enter_live_storage(partial(self.update_reading_frequency, LIVE_STORAGE_FREQUENCY))
        self.machine.on_enter_live_storage(partial(self.update_lidar_frequency, DISTANCE_DEFAULT_FREQUENCY))

        self.machine.on_enter_full(partial(self.update_reading_frequency, FULL_FREQUENCY))
        self.machine.on_enter_full(partial(self.update_lidar_frequency, DISTANCE_ALERT_FREQUENCY))

        self.machine.on_enter_flood(partial(self.update_reading_frequency, FLOOD_FREQUENCY))
        self.machine.on_enter_flood(partial(self.update_lidar_frequency, DISTANCE_ALARM_FREQUENCY))

        self.machine.on_enter_stability(partial(self.update_reading_frequency, STABILITY_FREQUENCY))
        self.machine.on_enter_stability(partial(self.update_lidar_frequency, DISTANCE_ALERT_FREQUENCY))

        # Send default frequencies via MQTT at script start
        self.update_reading_frequency(LIVE_STORAGE_FREQUENCY)
        self.update_lidar_frequency(DISTANCE_DEFAULT_FREQUENCY)
        
        print("-> State Machine setup finished.")
        print("-> Script setup finished.\n")


    def update_reading_frequency(self, newFreq):
        self.client.publish(topic=IPI_FREQUENCY_UPDATE_TOPIC, payload=str(newFreq), qos=2, retain=True)
        self.reading_frequency = newFreq

    def update_lidar_frequency(self, newFreq):
        self.client.publish(topic=LIDAR_FREQUENCY_UPDATE_TOPIC, payload=str(newFreq), qos=2, retain=True)
        self.dist_frequency = newFreq

    def update_accel_frequency(self, newFreq):
        self.client.publish(topic=ACCEL_FREQUENCY_UPDATE_TOPIC, payload=str(newFreq), qos=2, retain=True)


    def publish_warning(self, tpc, message):
        payload_data = {"message": message}
        self.client.publish(topic=tpc, payload=json.dumps(payload_data), qos=2, retain=True)

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    def on_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe(TILT_TOPIC)
        print(f"{SUBBED_TO}: {TILT_TOPIC}")
        client.subscribe(ENERGY_SAVING_TOPIC)
        print(f"{SUBBED_TO}: {ENERGY_SAVING_TOPIC}\n")
        client.subscribe(DISTANCE_TOPIC)
        print(f"{SUBBED_TO}: {DISTANCE_TOPIC}")
        client.subscribe(VIBRATION_TOPIC)
        print(f"{SUBBED_TO}: {VIBRATION_TOPIC}")
        print("\n########## [BEHAVIORAL MODULE SETUP COMPLETE] ##########\n\n")


    def on_message(self, client, userdata, message):
        try:
            elapsed = time.time() - self.start_time
            print(f"Current time: {datetime.now().strftime("%H:%M:%S")} || Started {elapsed:.1f}s ago.\n")
            data = json.loads(message.payload.decode())

            if message.topic == TILT_TOPIC:
                self.handle_tilt_readings(data)

            elif message.topic == DISTANCE_TOPIC:
                self.handle_distance_readings(data)

            else: # topic = readings/accel_data
                self.handle_vibration_readings(data)

        except Exception as e:
            print(f"Error processing MQTT message: {e}\n")

    # store new readings AND check if the new reading exceeds the limit thresholds
    # -> tilt change limit
    def populate_new_readings_mat(self, new_readings_arr, timestamp):
        new_tilt_readings_mat = [[0.0 for _ in range(3)] for _ in range(NUMBER_IPI_NODES)]
        self.within_tilt_limits = True
        for node_data_json in new_readings_arr:
            node_number = node_data_json.get("n", None)
            node_ax = node_data_json.get("aX", None)
            node_ay = node_data_json.get("aY", None)
            node_az = node_data_json.get("aZ", None)
            new_tilt_readings_mat[node_number-1][0] = node_ax if node_ax is not None else print("Node " + node_number + " has an invalid aX value (None)")
            new_tilt_readings_mat[node_number-1][1] = node_ay if node_ay is not None else print("Node " + node_number + " has an invalid aY value (None)")
            new_tilt_readings_mat[node_number-1][2] = node_az if node_az is not None else print("Node " + node_number + " has an invalid aZ value (None)")

            base_reading = self.base_tilt_reading_mat[node_number-1]
            if not self.first_tilt_read:
                if (abs(node_ax-base_reading[0]) >= self.TILT_X_MAX_THRESHOLD) or \
                    (abs(node_ay-base_reading[1]) >= self.TILT_Y_MAX_THRESHOLD):
                    self.within_tilt_limits = False
                    print(f"Change on X: {abs(node_ax-base_reading[0])} | Change on Y: {abs(node_ay-base_reading[1])}")
                    print(f"Node {node_number} exceeded safety bounds!!")

            # Insert readings in log file
            self.ipi_log.append((timestamp, node_number, node_ax, node_ay, node_az))

        return new_tilt_readings_mat

    # compare 2 consecutive readings -> tilt change rate
    def compare_readings(self, new_tilt_readings_mat, last_tilt_reading_mat, current_reading_time):
        angle_diffs = [0.0] * NUMBER_IPI_NODES
        self.isMoving = False

        for pos in range(NUMBER_IPI_NODES):
            last_reading = last_tilt_reading_mat[pos]
            new_reading = new_tilt_readings_mat[pos]

            # a1 and a2 are vectors like [angle_x, angle_y, angle_z]
            abs_diff_to_last = [abs(new_reading[i] - last_reading[i]) for i in range(3)]
            angle_diffs[pos] = max(abs_diff_to_last)

            time_diff = current_reading_time - self.last_tilt_reading_time
            time_diff_minutes = (time_diff/60)
            
            angle_change_rate_per_minute = max(abs_diff_to_last)/time_diff_minutes

            if time_diff_minutes != 0.0 and angle_change_rate_per_minute >= self.TILT_RATE_THRESHOLD:
                self.isMoving = True
                print(f"Node {pos} exceeded safe rate!!")

        print(f"Time since last reading: {time_diff:.2f} seconds / {time_diff_minutes:.2f} minutes.\n")

        maxVal = max(angle_diffs)
        if abs(maxVal)==0.0:
            print(f"No change happened since last reading.\n")
        
        print(f"Biggest change was {maxVal:.2f} degrees on node {angle_diffs.index(maxVal)+1}")
        print(f"Biggest change rate was {angle_change_rate_per_minute:.2f} degrees/min on node {angle_diffs.index(maxVal)+1}\n")

    
    def handle_tilt_readings(self, data):
        # Readings come as:
        # {"inc_number":1,"inc_code":"I1","inc_description":"Test inclinometer n. 1","sensors":[{"n":1,"aX":18.19878,"aY":-62.85292,"aZ":-19.18011}]}

        new_tilt_reading_list = data.get("sensors", None) # JSON array

        if new_tilt_reading_list is None:
            print("Received an invalid (empty) message on topic readings/inc_data.\n")
            print("#################################\n\n")
            return
    
        current_tilt_reading_time = time.time()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # If it's the first reading (last readings matrix only has 0's), just store it
        if all(val == 0.0 for row in self.last_tilt_reading_mat for val in row) :
            self.base_tilt_reading_mat = self.populate_new_readings_mat(new_tilt_reading_list, timestamp)
            self.last_tilt_reading_mat = self.base_tilt_reading_mat
            self.last_tilt_reading_time = current_tilt_reading_time
            self.first_tilt_read = False
            print(f"Initial IPI reading received!\n")
            print("#################################\n\n")
            return
        
        new_tilt_reading_mat = self.populate_new_readings_mat(new_tilt_reading_list, timestamp)
        print(new_tilt_reading_mat)
        self.compare_readings(new_tilt_reading_mat, self.last_tilt_reading_mat, current_tilt_reading_time)

        # 2 conditions
            # 1. Threshold limits exceeded
            # 2. Tilt change rate exceeded by over (1.5deg/min)+15%

        if self.machine.get_state(self.state).name == LIVE_STORAGE and (not self.within_tilt_limits or self.isMoving):
                self.trigger(TO_STABILITY)
        elif self.machine.get_state(self.state).name == STABILITY and self.within_tilt_limits and not (self.isMoving and self.isFast):
            self.trigger(TO_LIVE_STORAGE)

        self.last_tilt_reading_mat = new_tilt_reading_mat
        self.last_tilt_reading_time = current_tilt_reading_time
        newFreq = self.reading_frequency/1000
        self.frequency_log.append((timestamp, newFreq))
        
        print(f" > Current state is {self.machine.get_state(self.state).name.upper()}.\n")
        print(f" > New readings every {newFreq} seconds.\n")
        print("#################################\n\n")
    

    def handle_distance_readings(self, data):
        # Readings come as:
        # {"mod_code":"DVM1", "distance":37, "signal_strength":9715, "temperature":33}
        new_dist_reading = data.get("distance", None)

        if new_dist_reading is None:
            print("Received an invalid (empty) message on topic readings/lidar_data.\n")
            print("#################################\n\n")
            return

        new_dist_reading = int(new_dist_reading)

        current_reading_time = time.time()

        new_water_level = 22+self.OFFSET-(new_dist_reading)
        
        print(f"New water level reading - {new_water_level} cm.")
        print(f"Last water level reading - {self.last_water_level} cm.")

        # If it's the first reading, just store it
        if self.last_water_level is None:
            self.last_water_level = new_water_level
            if self.INTERMEDIATE_LEVEL <= new_water_level < self.MAX_LEVEL:
                self.trigger(TO_FULL)

            elif new_water_level >= self.MAX_LEVEL:
                self.trigger(TO_FLOOD)
            self.last_lidar_reading_time = current_reading_time
            print(f"Initial water level received!\n")
            print(f" > New IPI reading every {self.reading_frequency/1000} seconds.\n")
            print(f" > New distance readings every {self.dist_frequency/1000} seconds. \n")
            print("#################################\n\n")
            return

        elapsed = current_reading_time- self.start_time

        ### WATER LEVEL TRANSITIONS ###
        if self.MIN_LEVEL <= new_water_level < self.INTERMEDIATE_LEVEL:
            if self.machine.get_state(self.state).name == FULL:
                self.trigger(TO_LIVE_STORAGE)

        elif self.INTERMEDIATE_LEVEL <= new_water_level < self.MAX_LEVEL:
            if self.machine.get_state(self.state).name == LIVE_STORAGE or self.machine.get_state(self.state).name == FLOOD:
                self.trigger(TO_FULL)
            message = f"[+{elapsed:.1f}s][WARNING] Water level is close to its maximum safe value."
            self.publish_warning(WATER_LEVEL_WARNINGS_TOPIC, message)
            print(message)

        elif new_water_level >= self.MAX_LEVEL:
            if self.machine.get_state(self.state).name == FULL or self.machine.get_state(self.state).name == LIVE_STORAGE:
                self.trigger(TO_FLOOD)
            message = f"[+{elapsed:.1f}s][ALARM] Water levels are critically HIGH."
            self.publish_warning(WATER_LEVEL_WARNINGS_TOPIC, message)
            print(message)

        else: # water level below minimum value
            message = f"[+{elapsed:.1f}s][INFO] Water level is below to its minimum value -> Dead Storage reached."
            self.publish_warning(WATER_LEVEL_WARNINGS_TOPIC, message)


        ### WATER LEVEL CHANGE RATE TRANSITIONS ###
        if self.machine.get_state(self.state).name == LIVE_STORAGE or self.machine.get_state(self.state).name == FULL or \
            self.machine.get_state(self.state).name == STABILITY:

            # change-rate measured in cm/min
            time_diff = current_reading_time - self.last_lidar_reading_time
            time_diff_minutes = (time_diff/60)
            print(f"Time diff: {time_diff_minutes:.2f} minutes")
            distance_change_rate = (new_water_level-self.last_water_level)/time_diff_minutes
            print(f" > Distance change rate {distance_change_rate:.2f} cm/min.\n")

            if distance_change_rate != 0:
                self.last_lidar_reading_time = current_reading_time

            if abs(distance_change_rate) <= self.DISTANCE_RATE_THRESHOLD and not self.isMoving and self.within_tilt_limits:
                if self.machine.get_state(self.state).name == STABILITY:
                    self.isFast = False
                    self.trigger(TO_LIVE_STORAGE)
            if abs(distance_change_rate) >= self.DISTANCE_RATE_THRESHOLD:
                self.isFast = True
                if distance_change_rate < 0 and self.machine.get_state(self.state).name == LIVE_STORAGE:
                    self.trigger(TO_STABILITY)
                elif  distance_change_rate > 0 and self.machine.get_state(self.state).name == FULL:
                    self.trigger(TO_FLOOD)
                
        self.last_water_level = new_water_level

        # Adding data to log files
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        newFreq = self.reading_frequency/1000
        self.water_level_log.append((timestamp, new_dist_reading, new_water_level))
        self.frequency_log.append((timestamp, newFreq))

        print(f" > Current state is {self.machine.get_state(self.state).name.upper()}\n")
        print(f" > New IPI reading every {newFreq} seconds.\n")
        print(f" > New distance readings every {self.dist_frequency/1000} seconds. \n")
        print("#################################\n\n")
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

     # Write frequency log
    try:
        with open("../Docs/Test_data/Teste9/ipi_frequency_log.csv", mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["Timestamp", "IPI Frequency (ms)"])
            writer.writerows(adaptive_frequency_module.frequency_log)
        print("-> Frequency log saved to ipi_frequency_log.csv\n")
    except Exception as e:
        print(f"-> Failed to save frequency log: {e}")

    # Write water level log
    try:
        with open("../Docs/Test_data/Teste9/water_level_log.csv", mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["Timestamp", "Distance", "Water Level"])
            writer.writerows(adaptive_frequency_module.water_level_log)
        print("-> Water level measurements saved to water_level_log.csv\n")
    except Exception as e:
        print(f"-> Failed to save water level log: {e}")

    # Write IPI readings log
    try:
        with open("../Docs/Test_data/Teste9/ipi_readings_log.csv", mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["Timestamp", "Node number", "aX", "aY", "aZ"])
            writer.writerows(adaptive_frequency_module.ipi_log)
        print("-> IPI measurements saved to ipi_readings_log.csv\n")
    except Exception as e:
        print(f"-> Failed to save IPI readings log: {e}")

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