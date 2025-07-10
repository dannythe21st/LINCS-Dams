#include <TFMPlus.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <algorithm> 
#include "MMA7660.h"
#include "esp_sleep.h"
#include "time.h"
extern "C" {
  #include "esp_wifi.h"
}


/**** TFMini Plus object *****/
TFMPlus tfmP;     // learn about it here -> https://github.com/budryerson/TFMini-Plus
const char module_code[] = "DVM1"; // Distance Vibration Module 1 (CHANGE ME)

/**** MMA7660 Accelerometer object *****/
MMA7660 accelemeter;

/****** WiFi Connection Details *******/
const char* ssid = "name_or_ip_addr"; // CHANGE ME
const char* password = "password";        // CHANGE ME

/******* MQTT Broker Connection Details *******/
const char* mqtt_server = "RPI_hostname_or_ip_addr";  // CHANGE ME
const char* mqtt_username = "username";     // CHANGE ME
const char* mqtt_password = "password";  // CHANGE ME
const int mqtt_port = 1883;   // Default port

/**** Secure WiFi Connectivity Initialisation *****/
WiFiClient espClient;

/**** MQTT Client Initialisation Using WiFi Connection *****/
PubSubClient client(espClient);
unsigned long lastMsg = 0;
#define MSG_BUFFER_SIZE (512)
char msg[MSG_BUFFER_SIZE];

/**** Data Collection Variables *****/

//  sensor toggle switches
bool lidar_toggle = true;
bool accel_toggle = false;

int16_t tfDist, tfFlux, tfTemp = 0; // Distance (cm), Signal Strenght, Lidar chip temp

float ax,ay,az;  // acceleration values

unsigned long lastLidarRead = 0;
unsigned long lastAccelRead = 0;

// reading frequencies (CHANGE ME)
unsigned long lidarInterval = 30000;
unsigned long accelInterval = 5000;

// Low-pass filter settings
#define NUM_READINGS 5
#define MOVING_AVG_WINDOW 3

uint16_t movingAvgBuffer[MOVING_AVG_WINDOW] = {0};
int movingAvgIndex = 0;
bool useMovingAverage = false;

/**** JSON Message capacity *****/
const int capacity = JSON_OBJECT_SIZE(5) * 1.5; 


/**** NTP server config *****/
const char* ntpServer = "pool.ntp.org";
const long gmtOffset_sec = 0;      // UTC offset in seconds
const int daylightOffset_sec = 3600; // 3600 for summer time

/************* Connect to WiFi ***********/
void setup_wifi() {
  delay(10);
  Serial.print("\nConnecting to ");
  Serial.println(ssid);

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  randomSeed(micros());
  Serial.println("\nWiFi connected\nIP address: ");
  Serial.println(WiFi.localIP());
}

/************* Connect to MQTT Broker ***********/
void reconnect() {
  int attempt = 0;

  // Check if WiFi is not connected
  if (WiFi.status() != WL_CONNECTED || client.state() == -2) {

    WiFi.disconnect(true);
    delay(100);
    WiFi.begin(ssid, password);

    int wifiAttempts = 0;
    while (WiFi.status() != WL_CONNECTED && wifiAttempts < 20) {
      delay(500);
      Serial.print(".");
      wifiAttempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
      Serial.println("\nWiFi reconnected.");
    } else {
      Serial.println("\nWiFi reconnection failed. Aborting MQTT reconnect.");
      return;
    }
  }

  // Connect to MQTT after WiFi is confirmed
  while (!client.connected()) {
    String clientId = "DVClient-" + String(random(0xffff), HEX);

    if (client.connect(clientId.c_str(), mqtt_username, mqtt_password)) {
      Serial.println("MQTT Connected!\n");
      client.subscribe("dvm/accel_freq");
      client.subscribe("dvm/lidar_freq");
      return;
    } else {
      int reason_code = client.state();
      Serial.print("failed, rc=");
      Serial.print(reason_code);
      Serial.println(". Trying again in 500ms...");
      delay(500);

      attempt++;
      if (attempt >= 5) {
        Serial.println("Failed MQTT reconnect after 5 tries. Aborting.");
        break;
      }
    }
  }
}



/***** Call back Method for Receiving MQTT messages ****/
void callback(char* topic, byte* payload, unsigned int length) {
  String incommingMessage = "";
  for (int i = 0; i < length; i++) incommingMessage += (char)payload[i];

  Serial.println("Message arrived [" + String(topic) + "]" + incommingMessage);

  if (strcmp(topic, "dvm/accel_freq") == 0 || strcmp(topic, "dvm/lidar_freq") == 0){
    int intValue = incommingMessage.toInt();
    (strcmp(topic, "dvm/accel_freq") == 0) ? (accelInterval = intValue) : (lidarInterval = intValue);
  }
}

/**** Method for Publishing MQTT Messages **********/
void publishMessage(const char* topic, String payload, boolean retained) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WIFI not connected" );
    WiFi.reconnect();
    delay(500);
  }

  if (!client.connected()) {
    Serial.println("ERROR: MQTT Client is not connected. Reconnecting...");
    reconnect();
    delay(500);
  } else{
    client.loop();
  }

  bool aux = client.publish(topic, payload.c_str(), true);
  if (!aux)
    Serial.println("ERROR: Message failed to publish!");
  else
    Serial.println("Published!\n\n");
  
}

void setup() {
  
  Serial.begin(115200);  
  while (!Serial) delay(10);

  setup_wifi();
  WiFi.setSleep(false);

  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
  client.setKeepAlive(30);

  Serial2.begin(115200, SERIAL_8N1, 16, 17); // Initialize TFMPLus device serial port
  delay(20);
  tfmP.begin( &Serial2);

  accelemeter.init(); 

  if( tfmP.sendCommand( SET_FRAME_RATE, FRAME_2))
      Serial.println( "Updated frame rate");
  else tfmP.printReply();

  // Init and get time
  configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
  Serial.println("Waiting for time sync...");
  delay(2000); // Give time to sync
  
}

void loop() {
  get_distance_accel_readings_with_filter();
}

int counter = 0;

void get_distance_accel_readings_with_filter() {
  // reconnect after sleeping
  if (!client.connected()) 
    reconnect();
  else 
    client.loop();

  unsigned long now = millis();

  if (lidar_toggle && (now - lastLidarRead >= lidarInterval)) {
    
    uint16_t readings[NUM_READINGS];
    int validReadings = 0;

    for (int i = 0; i < NUM_READINGS; ++i) {
      if (tfmP.getData(tfDist, tfFlux, tfTemp)) {
        readings[validReadings++] = tfDist;
        delay(10);
      } else {
        Serial.println("Failed to get LiDAR reading " + String(i));
        tfmP.printFrame();
      }
    }

    if (validReadings >= 3) {
      // Step 1: Calculate mean
      float sum = 0;
      for (int i = 0; i < validReadings; i++) {
        sum += readings[i];
      }
      float mean = sum / validReadings;

      // Step 2: Calculate standard deviation
      float varianceSum = 0;
      for (int i = 0; i < validReadings; i++) {
        varianceSum += pow(readings[i] - mean, 2);
      }
      float stddev = sqrt(varianceSum / validReadings);

      // Step 3: Filter values within +-1 stddev
      int filteredCount = 0;
      float filteredSum = 0;
      for (int i = 0; i < validReadings; i++) {
        if (abs(readings[i] - mean) <= stddev) {
          filteredSum += readings[i];
          filteredCount++;
        }
      }

      if (filteredCount == 0) {
        Serial.println("All readings were outliers, skipping...");
      } else {
        int filteredAvg = filteredSum / filteredCount;

        int finalValue = filteredAvg;

        // You can use this here if you want
        // or get less raw data and process it later
        if (useMovingAverage) {
          movingAvgBuffer[movingAvgIndex] = filteredAvg;
          movingAvgIndex = (movingAvgIndex + 1) % MOVING_AVG_WINDOW;

          int count = 0;
          int sumAvg = 0;
          for (int i = 0; i < MOVING_AVG_WINDOW; i++) {
            if (movingAvgBuffer[i] > 0) {
              sumAvg += movingAvgBuffer[i];
              count++;
            }
          }
          if (count > 0)
            finalValue = sumAvg / count;
        }

        time_t timestamp = time(nullptr);
        uint64_t timestamp_ns = (uint64_t)timestamp * 1000000000ULL;

        Serial.println("Counter: " + String(counter++));
        Serial.println("Final Dist: " + String(finalValue));
        Serial.println("Current freq: " + String(lidarInterval));

        ship_lidar_data(finalValue, tfFlux, tfTemp, timestamp_ns);

        lastLidarRead = now;
      }

    } else {
      Serial.println("Not enough valid LiDAR readings.");
    }
  }

  if (accel_toggle && (now - lastAccelRead >= accelInterval)) {
    if (lastLidarRead == now) delay(50);
    if (accelemeter.getAcceleration(&ax, &ay, &az)) {
      Serial.println("aX: " + String(ax) + " g");
      Serial.println("aY: " + String(ay) + " g");
      Serial.println("aZ: " + String(az) + " g");
      Serial.println("*************\n\n");
      ship_accel_data(ax, ay, az);
      lastAccelRead = now;
    } else {
      Serial.println("Something went wrong. Couldn't get acceleration data.");
    }
  }

  // Sleep logic
  bool sleep = false;
  if (sleep){

    now = millis();

    // when working with both sensors, their frequencies may not match
    // this calculates the next reading time in that case
    // so the esp wakes up in time

    unsigned long nextLidarDue = lidar_toggle ? lidarInterval - (now - lastLidarRead) : ULONG_MAX;
    unsigned long nextAccelDue = accel_toggle ? accelInterval - (now - lastAccelRead) : ULONG_MAX;
    unsigned long sleepTime = min(nextLidarDue, nextAccelDue);

    if (sleepTime > 100) {

      // must break connections before sleeping or 
      // cores may be dumped after sleep
      WiFi.disconnect(true);
      client.disconnect();
      delay(100);
      esp_sleep_enable_timer_wakeup((uint64_t) sleepTime * 1000ULL);
      esp_light_sleep_start();
      delay(250);
    }
  }
  
}

void ship_lidar_data(int tfDist, int tfFlux, int tfTemp, uint64_t timestamp) {
  char mqtt_message[capacity];
  DynamicJsonDocument jsonLidar(capacity);
  jsonLidar["mod_code"] = module_code;
  jsonLidar["distance"] = tfDist;
  jsonLidar["signal_strength"] = tfFlux;
  jsonLidar["temperature"] = tfTemp;
  jsonLidar["timestamp"] = timestamp;
  serializeJson(jsonLidar, mqtt_message);

  // set the topic (require concatenation)
  const char topic_pub[] = "lidar_data/";

  Serial.print("TOPIC: ");
  Serial.println(topic_pub);

  // {"distance":219,"signal_strength":2196,"temperature":30}
  Serial.print("MESSAGE: ");
  Serial.println(mqtt_message);

  if (WiFi.status() != WL_CONNECTED) {
    WiFi.disconnect();
    delay(100);
    WiFi.reconnect();
    delay(500);
  }

  if (!client.connected()) {
    Serial.println("ERROR: MQTT Client is not connected. Reconnecting...");
    reconnect();
    delay(500);
  } else {
    client.loop();
  }

  publishMessage(topic_pub, mqtt_message, true);  // publish the msg to topic
}

void ship_accel_data(float ax, float ay, float az) {
  char mqtt_message[capacity];
  DynamicJsonDocument jsonAccel(capacity);
  jsonAccel["mod_code"] = module_code;
  jsonAccel["aX"] = ax;
  jsonAccel["aY"] = ay;
  jsonAccel["aZ"] = az;
  serializeJson(jsonAccel, mqtt_message);

  // set the topic (require concatenation)
  const char topic_pub[] = "accel_data/";

  if (WiFi.status() != WL_CONNECTED) {
    WiFi.disconnect();
    delay(100);
    WiFi.reconnect();
    delay(250);
  }

  if (!client.connected()) {
    Serial.println("ERROR: MQTT Client is not connected. Reconnecting...");
    reconnect();
  } else {
    client.loop();
  }

  Serial.print("TOPIC: ");
  Serial.println(topic_pub);

  // {"distance":219,"signal_strength":2196,"temperature":30}
  Serial.print("MESSAGE: ");
  Serial.println(mqtt_message);
  delay(100);

  publishMessage(topic_pub, mqtt_message, true);  // publish the msg to topic
}
