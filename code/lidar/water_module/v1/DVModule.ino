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
const char module_code[] = "DVM1"; // Distance Vibration Module 1

/**** MMA7660 Accelerometer object *****/
MMA7660 accelemeter;

/****** WiFi Connection Details *******/
const char* ssid = "NOS-56C6";
const char* password = "G6QYWEZJ";

// const char* ssid = "iPhone de Daniel";
// const char* password = "daniel2002";

/******* MQTT Broker Connection Details *******/
const char* mqtt_server = "raspberrypi.local";
const char* mqtt_username = "daniel";
const char* mqtt_password = "mosquitto";
const int mqtt_port = 1883;

/**** Secure WiFi Connectivity Initialisation *****/
WiFiClient espClient;

/**** MQTT Client Initialisation Using WiFi Connection *****/
PubSubClient client(espClient);
unsigned long lastMsg = 0;
#define MSG_BUFFER_SIZE (512)
char msg[MSG_BUFFER_SIZE];

/**** Data Collection Variables *****/

bool lidar_toggle = true;  //  turn the sensor on or off
bool accel_toggle = false;


int16_t tfDist, tfFlux, tfTemp = 0; // Distance (cm), Signal Strenght, Lidar chip temp

float ax,ay,az;  // acceleration values

unsigned long lastLidarRead = 0;
unsigned long lastAccelRead = 0;

unsigned long lidarInterval = 10000;      // 5 seconds
unsigned long accelInterval = 5000;      // 1 second

unsigned long num_lidar_readings = 5;

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
const int daylightOffset_sec = 3600; // e.g., 3600 for summer time

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
// void reconnect() {
//   // Loop until we're reconnected
//   while (!client.connected()) {
//     Serial.print("Attempting MQTT connection...");
//     String clientId = "DVClient-";  // Create a random client ID (DV = Distance Vibration)
//     clientId += String(random(0xffff), HEX);
//     // Attempt to connect
//     if (client.connect(clientId.c_str(), mqtt_username, mqtt_password)) {
//       Serial.println("Connected!\n");
//       client.subscribe("dvm/accel_freq");  // subscribe to topics here
//       client.subscribe("dvm/lidar_freq");
//     } else {
//       Serial.print("failed, rc=");
//       Serial.print(client.state());
//       Serial.println(" trying again ..");  // Wait before retrying
//       delay(500);
//     }
//   }
// }
void reconnect() {
  int attempt = 0;
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    String clientId = "DVClient-" + String(random(0xffff), HEX);

    if (client.connect(clientId.c_str(), mqtt_username, mqtt_password)) {
      Serial.println("Connected!\n");
      client.subscribe("dvm/accel_freq");
      client.subscribe("dvm/lidar_freq");
      return;
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" trying again ..");
      attempt++;
      delay(500);

      if (attempt >= 5) {
        Serial.println("MQTT failed 5 times — resetting WiFi");
        WiFi.disconnect(true);
        delay(100);
        WiFi.begin(ssid, password);

        int wifiAttempts = 0;
        while (WiFi.status() != WL_CONNECTED && wifiAttempts < 10) {
          delay(500);
          Serial.print(".");
          wifiAttempts++;
        }

        if (WiFi.status() == WL_CONNECTED) {
          Serial.println("\nWiFi reconnected.");
        } else {
          Serial.println("\nWiFi reconnection failed.");
        }

        attempt = 0; // reset MQTT retry counter
      }
    }
  }
}


/***** Call back Method for Receiving MQTT messages and Switching LED ****/
void callback(char* topic, byte* payload, unsigned int length) {
  //String incommingMessage = "";
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

  if (!client.connected()) {
    Serial.println("ERROR: MQTT Client is not connected. Reconnecting...");
    reconnect();
  }
  client.loop();
  //Serial.println("###############################    PUBLISHING MESSAGE    ###############################");
  bool aux = client.publish(topic, payload.c_str(), true);
  if (aux){
    //Serial.println("Message published [" + String(topic) + "] \n");
    //Serial.println("Message published [" + String(topic) + "]: " + payload);
    //Serial.println("###############################    MESSAGE PUBLISHED !!!    ###############################");
  }else{
    Serial.println("ERROR: Message failed to publish!");
  }

}

void setup() {
  
  Serial.begin(115200);  
  while (!Serial) delay(1);

  setup_wifi();
  esp_wifi_set_ps(WIFI_PS_NONE); // prevent WiFi from sleeping - ver se e preciso

  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
  client.setKeepAlive(30);

  Serial2.begin(115200, SERIAL_8N1, 16, 17); // Initialize TFMPLus device serial port.
  delay(20);
  tfmP.begin( &Serial2);

  accelemeter.init(); 
  // Reset the device on start
  // if( tfmP.sendCommand( SOFT_RESET, 0))
  //     Serial.println( "reset passed.");
  // else tfmP.printReply();
  // delay(500);

  if( tfmP.sendCommand( SET_FRAME_RATE, FRAME_2))
      Serial.println( "Updated frame rate");
  else tfmP.printReply();

  // Init and get time
  configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
  Serial.println("Waiting for time sync...");
  delay(2000); // Give time for sync
  
}

void loop() {
  
  //get_distance_accel_readings();
  get_distance_accel_readings_with_filter();
  //delay(1000);

}

// void get_distance_readings() {
//   if (!client.connected()){
//     if (reconnect())
//       delay(200);
//   } 
//   client.loop();

//   if( tfmP.getData( tfDist, tfFlux, tfTemp)){
//       Serial.print( "Dist: ");
//       Serial.println(tfDist);
//       Serial.println( "Flux: ");
//       Serial.println(tfFlux);
//       Serial.println( "Temp: ");
//       Serial.println(tfTemp);
//       Serial.println( "\r\n");
//       ship_lidar_data(tfDist, tfFlux, tfTemp);
//   }
//   else
//       tfmP.printFrame();  // display the error and HEX data

//   delay(5000);
// }

int counter = 0;

void get_distance_accel_readings() {

  if (!client.connected()) 
    reconnect();
  else 
    client.loop();
  
  //Serial.println("Current LiDAR Frequency: " + String(lidarInterval));
  int current_num_readings = 0;
  int sumDist = 0.0;
  int sumFlux = 0;
  int sumTemp = 0;

  unsigned long now = millis();

  if (lidar_toggle){
    if (now - lastLidarRead  >= lidarInterval) {
      // TODO why is this overflowing the sensor after a few iterations???
      // while (current_num_readings < num_lidar_readings) {
      //   if( tfmP.getData( tfDist, tfFlux, tfTemp)){
      //     sumDist += tfDist;
      //     sumFlux += tfFlux;
      //     sumTemp += tfTemp;
      //     current_num_readings++;
      //     sleep(10);
      //   }
      //   else{
      //     Serial.println("Failed getting distance readings on iteration " + String(current_num_readings));
      //     tfmP.printFrame();  // display the error and HEX data
      //     break; // to avoid getting stuck on the loop indefinetely, ultimately resulting in a permanent connection loss to the broker
      //   }
      // }

      if(tfmP.getData( tfDist, tfFlux, tfTemp)){
        time_t timestamp = time(nullptr); // current timestamp
        uint64_t timestamp_ns = (uint64_t)timestamp * 1000000000ULL; // in ns to match telegraf timestamp units
        ship_lidar_data(tfDist, tfFlux, tfTemp,timestamp_ns);
        Serial.println("Counter: " + String(counter++));
        Serial.println("Dist: " + String(tfDist));
        Serial.println("Flux: " + String(tfFlux));
        Serial.println("Temp: " + String(tfTemp));
        Serial.print("Current freq: " + String(lidarInterval));
        Serial.println( "\r\n");
      } else{
        Serial.println("Couldn't send lidar readings.");
      }

      client.loop();
      
      lastLidarRead = now;

      // float avgDist = (float)sumDist / current_num_readings;
      // float avgFlux = (float)sumFlux / current_num_readings;
      // float avgTemp = (float)sumTemp / current_num_readings;

      // ship_lidar_data(avgDist, avgFlux, avgTemp);

    }
  }
  
  
  
  if (accel_toggle){
    if (now - lastAccelRead >= accelInterval) {
      if (lastLidarRead == now) // to avoid sending 2 readings at the same time
        delay(50);
      if (accelemeter.getAcceleration(&ax,&ay,&az)) {
        Serial.println("aX: " + String(ax) + " g");
        Serial.println("aY: " + String(ay) + " g");
        Serial.println("aZ: " + String(az) + " g");
        Serial.println("*************\n\n");
        ship_accel_data(ax, ay, az);
        lastAccelRead = now;
      }
      else
        Serial.println("Something went wrong. Couldn't get acceleration data.");
    }
  }
  

  // **********  TODO sort the sleep situation out  ********** //
  // ********************************************************* //

  // unsigned long nextAccelDue = accelInterval - (now - lastAccelRead);
  // unsigned long nextLidarDue = lidarInterval - (now - lastLidarRead);
  // unsigned long sleepTime = 0;

  // // Calculate how long until the next task
  // if (lidar_toggle && accel_toggle){
  //   sleepTime = min(nextAccelDue, nextLidarDue);
  // } else{
  //   sleepTime = (lidar_toggle) ? nextLidarDue : nextAccelDue;
  // }
  

  // Convert ms for esp_sleep
  //esp_sleep_enable_timer_wakeup((uint64_t)sleepTime * 1000);
  //esp_light_sleep_start();

  // unsigned long margin = 50; // ms
  // sleepTime = (sleepTime > margin) ? sleepTime - margin : 0;

  // if (client.connected() && WiFi.status() == WL_CONNECTED && sleepTime > 1500) {
  //   client.loop();
  //   delay(50);
  //   esp_sleep_enable_timer_wakeup(sleepTime * 1000);
  //   esp_light_sleep_start();
  // }
}

// VERSAO COM FILTRO 

void get_distance_accel_readings_with_filter() {
  if (!client.connected()) 
    reconnect();
  else 
    client.loop();

  unsigned long now = millis();

  bool didLidar = false;
  bool didAccel = false;

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

      // Step 3: Filter values within ±1 stddev
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

        // Ver se deixo tambem a media movel
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

        ship_lidar_data(finalValue, tfFlux, tfTemp, timestamp_ns);

        Serial.println("Counter: " + String(counter++));
        Serial.println("Filtered Dist (stddev): " + String(finalValue));
        Serial.print("Current freq: " + String(lidarInterval));
        Serial.println("\r\n");

        didLidar = true;
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
      didAccel = true;
    } else {
      Serial.println("Something went wrong. Couldn't get acceleration data.");
    }
  }

  // Sleep logic
  now = millis();
  unsigned long nextLidarDue = lidar_toggle ? lidarInterval - (now - lastLidarRead) : ULONG_MAX;
  unsigned long nextAccelDue = accel_toggle ? accelInterval - (now - lastAccelRead) : ULONG_MAX;
  unsigned long sleepTime = min(nextLidarDue, nextAccelDue);

  unsigned long margin = 50;
  sleepTime = (sleepTime > margin) ? sleepTime - margin : 0;
  Serial.println("Sleep time: " + String(sleepTime));

  // if (sleepTime > 100 && sleepTime < 30000) {
  //   client.loop();
  //   delay(10);
  //   esp_sleep_enable_timer_wakeup((uint64_t)sleepTime * 1000ULL);
  //   esp_light_sleep_start();
  //   if (!client.connected()) {
  //     reconnect();
  //   }
  //   client.loop();
  // }

  if (sleepTime > 100 && sleepTime < 30000) {
    client.loop();  // flush pending messages

    // disconnect before sleep to be safe (optional)
    client.disconnect();  // clean shutdown

    esp_sleep_enable_timer_wakeup((uint64_t)sleepTime * 1000ULL);
    esp_light_sleep_start();
    //client.loop();
    // after waking, reconnect WiFi and MQTT
    if (WiFi.status() != WL_CONNECTED) {
      setup_wifi();
    }

    if (!client.connected()) {
      Serial.println("ERROR: MQTT Client is not connected. Reconnecting...");
      reconnect();
    } else {
      client.loop();
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

  // int resultSize = strlen(prefix) + strlen(inc_code) + 1;  // Calculate the size of the resulting array
  // char topic_pub[resultSize];                              // Allocate memory for the new array
  // strcpy(topic_pub, prefix);                               // Copy the prefix into concatenatedString
  // strcat(topic_pub, inc_code);

  Serial.print("TOPIC: ");
  Serial.println(topic_pub);

  // {"distance":219,"signal_strength":2196,"temperature":30}
  Serial.print("MESSAGE: ");
  Serial.println(mqtt_message);

  publishMessage(topic_pub, mqtt_message, true);  // publish the msg to topic
}
