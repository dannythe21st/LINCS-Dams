/*
  R Santos  ricardos@lnec.pt
    THE GATEWAY FROM ESPNOW TO UART SERIAL
    ESPNOW -> UART
*/

/*
  D Eugenio 2025
    ACK Mechanism + Bi-directional communication
    ESPNOW <-> UART
*/

#include <ESP8266WiFi.h>
#include <espnow.h>
#include <ArduinoJson.h>
#define ARDUINOJSON_USE_LONG_LONG = 1

// Set the desired new MAC Address
uint8_t newMACAddress[] = { 0X80, 0x7D, 0x3A, 0xB7, 0x76, 0x9C };

uint8_t node1MACAddress[] = { 0xBC, 0xDD, 0xC2, 0x25, 0xEA, 0x7D }; // BC:DD:C2:25:EA:7D
uint8_t node2MACAddress[] = { 0x3C, 0x71, 0xBF, 0x2B, 0x2B, 0xD3 }; // 3C:71:BF:2B:2B:D3
uint8_t node3MACAddress[] = { 0xDC, 0x4F, 0x22, 0x5E, 0x95, 0x42 }; // DC:4F:22:5E:95:42
uint8_t node4MACAddress[] = { 0x3C, 0x71, 0xBF, 0x2B, 0x33, 0x43 }; // 3C:71:BF:2B:33:43

int inc_number = 1;
unsigned long messageInterval = 10000;  //10 seconds
const unsigned long timeoutDuration = messageInterval * 2.5;  // after timeout the values are sent anyway
unsigned long previousMillis = 0;

const int sensors_totalNumber = 1;               // number of sensors in the inclinometer
float incSensVals[sensors_totalNumber][4] = {};  // define an array to store the values and initialize it with zeros

// ESP0 <-> ESP1 <-> ESP2 reliability feature
bool burstMode = false;
int retries = 0;
bool ackReceived = false;
const int maxRetries = 3;
const unsigned long ackTimeout = (messageInterval/2); // Try for half the time between readings (ms) 
const char ack[] = "[ACK] OK";

// Structure example to receive data
// Must match the sender structure
typedef struct struct_message {
  int id;
  float alphaX;
  float alphaY;
  float alphaZ;
  unsigned int readingId;
} struct_message;

// Create a struct_message called myData
struct_message myData;

// for buffer of JSON data as a JSON object
const int capacity = JSON_OBJECT_SIZE(1) + JSON_OBJECT_SIZE(sensors_totalNumber) * 4 * 2;

int count = 0;
/******  ESP-NOW Communication CB functions  ******/

// callback function that will be executed when data is received 
void OnDataRecv(uint8_t *mac, uint8_t *incomingData, uint8_t len) {
  if(len<=sizeof(ack)){ // received ACK from ESP0
    String msg = "";
    for (int i = 0; i < len; i++) {
      msg += (char)incomingData[i];
    }

    if (msg == "[ACK] OK") {
      Serial.println("ACK received from ESP1");
    }
  } else{ // received data from ESP0
    memcpy(&myData, incomingData, sizeof(myData));
    Serial.println("Counter: " + String(count++));
    Serial.println("ID: " + String(myData.id));
    Serial.println("Frequency: " + String(messageInterval));
    Serial.println("alphaX: " + String(myData.alphaX));
    Serial.println("alphaY: " + String(myData.alphaY));
    Serial.println("alphaZ: " + String(myData.alphaZ));
    Serial.println();

    incSensVals[myData.id - 4][0] = myData.id;
    incSensVals[myData.id - 4][1] = myData.alphaX;
    incSensVals[myData.id - 4][2] = myData.alphaY;
    incSensVals[myData.id - 4][3] = myData.alphaZ;

    // Let the ESP0 node that sent the data that ESP1 received it
    if (myData.id == 1)
      esp_now_send(node1MACAddress, (uint8_t*)ack, sizeof(ack));
    else if (myData.id == 2)
      esp_now_send(node2MACAddress, (uint8_t*)ack, sizeof(ack));
    else if (myData.id == 3)
      esp_now_send(node3MACAddress, (uint8_t*)ack, sizeof(ack));
    else
      esp_now_send(node4MACAddress, (uint8_t*)ack, sizeof(ack));
  }
  
  
}

// Callback when data is sent
void OnDataSent(uint8_t *mac_addr, uint8_t sendStatus) {
  Serial.print("Last Packet Send Status: ");
  if (sendStatus == 0){
    Serial.println("Delivery success");
  }
  else{
    Serial.println("Delivery fail");
  }
}

// check if the array is totally full with data from sensors
bool allSensorsData(float arr[sensors_totalNumber][4]) {
  for (int i = 0; i < sensors_totalNumber; i++) {
    for (int j = 0; j < 4; j++) {
      if (arr[i][j] == 0) {
        return false;  // Found a zero, return false immediately
      }
    }
  }

  return true;  // No zero found in the array
}


/******  UART Data Transfer Function  ******/
void sendJSONData() {

  DynamicJsonDocument jsonInc(capacity);

  for (int i = 0; i < sensors_totalNumber; ++i) {
    jsonInc["sensors"][i]["n"] = incSensVals[i][0];
    jsonInc["sensors"][i]["aX"] = incSensVals[i][1];
    jsonInc["sensors"][i]["aY"] = incSensVals[i][2];
    jsonInc["sensors"][i]["aZ"] = incSensVals[i][3];
    jsonInc["sensors"][i]["timestamp"] = myData.timestamp;

  }

  // Serialize the JSON data to a String
  String jsonIncString;
  serializeJson(jsonInc, jsonIncString);

  // make sure ESP2 received the message
  while (retries < maxRetries && !ackReceived) {
    Serial.flush();                 // wait until all is gone from buffer
    Serial.println(jsonIncString);  // Send the JSON data over UART
    
    unsigned long start = millis();
    String ack = "";
    while (millis() - start < ackTimeout) {
      if (Serial.available()) {
        ack = Serial.readStringUntil('\n');
        ack.trim();
        if (ack == "[ACK] OK") {
          ackReceived = true;
          break;
        }
      }
      delay(100); // avoid WDT reset
    }

    if (!ackReceived) {
      retries++;
      Serial.println("ACK not received, retrying...");
    }
  }

  if (!ackReceived) 
    Serial.println("ERROR: Failed to get ACK from ESP2 after retries");
  else 
    Serial.println("ACK received from ESP2");
  
  retries = 0;
  ackReceived = false;
}

void setup() {
  // Initialize Serial Monitor
  Serial.begin(9600);
  while (!Serial) continue;  // continue once Serial is available

  // Set device as a Wi-Fi Station
  WiFi.mode(WIFI_STA);
  wifi_set_macaddr(STATION_IF, &newMACAddress[0]);

  // Init ESP-NOW
  if (esp_now_init() != 0) {
    Serial.println("Error initializing ESP-NOW");
    return;
  }

  esp_now_add_peer(node1MACAddress, ESP_NOW_ROLE_SLAVE, 1, NULL, 0);
  esp_now_add_peer(node2MACAddress, ESP_NOW_ROLE_SLAVE, 1, NULL, 0);
  esp_now_add_peer(node3MACAddress, ESP_NOW_ROLE_SLAVE, 1, NULL, 0);
  esp_now_add_peer(node4MACAddress, ESP_NOW_ROLE_SLAVE, 1, NULL, 0);

  // Once ESPNow is successfully Init, we will register for recv CB to
  // get recv packer info
  esp_now_set_self_role(ESP_NOW_ROLE_SLAVE);
  esp_now_register_recv_cb(OnDataRecv);
  esp_now_register_send_cb(OnDataSent);
}

void loop() {
  
  receive_frequency_updates();
  unsigned long currentMillis = millis();
  
  // Send the message if the condition is true, or timeout if it's false
  if (allSensorsData(incSensVals)) {
    //burstMode = false;
    if (currentMillis - previousMillis >= messageInterval) {
      previousMillis = currentMillis;

      // Send the message over Serial
      sendJSONData();

      // Set all elements to 0
      memset(incSensVals, 0, sizeof(incSensVals));

      // Perform other actions based on the condition (if needed)

    }
  } else {
    if (currentMillis - previousMillis >= timeoutDuration) {
      previousMillis = currentMillis;

      // Send the message over Serial anyway
      sendJSONData();

      // Perform other actions based on the timeout (if needed)

    }
  }

  //Serial.println("I'm awake, but I'm going into deep sleep mode for 30 seconds");
  //ESP.deepSleep(30e6);
}

void receive_frequency_updates() {

  if (Serial.available()) {
    String incoming = Serial.readStringUntil('\n'); // Read until newline

    incoming.trim(); // Remove newline and spaces
    if (incoming.length() == 0) return; // Ignore noise

    if (incoming.startsWith("[COMMAND] ")) {
      String commandType = incoming.substring(10);

      Serial.println("Command received:");
      Serial.println(commandType);

      if (commandType.startsWith("[FREQ] ")) {
        String frequencyValue = commandType.substring(7);
        Serial.print("Frequency value string: ");
        Serial.println(frequencyValue);
        int freqValNum = frequencyValue.toInt();

        // Send the new value to ESP0 via ESP-NOW
        esp_now_send(node1MACAddress, (uint8_t *)&freqValNum, sizeof(int));
        esp_now_send(node2MACAddress, (uint8_t *)&freqValNum, sizeof(int));
        esp_now_send(node3MACAddress, (uint8_t *)&freqValNum, sizeof(int));
        esp_now_send(node4MACAddress, (uint8_t *)&freqValNum, sizeof(int));
        
        // let ESP2 know ESP1 got the new frequency
        Serial.println("[ACK] FREQ_OK");

        messageInterval = freqValNum+15;

        Serial.println("##############################################");
        Serial.print("New frequency value int: ");
        Serial.println(freqValNum);
        Serial.println("##############################################\n\n");
      }

      if (commandType.startsWith("[FILTER] ")){
        String filterModeString = commandType.substring(9);
        Serial.print("Filter mode: ");
        Serial.println(frequencyValue);
        int filterMode = filterModeString.toInt();

        // Send the new value to ESP0 via ESP-NOW
        esp_now_send(node1MACAddress, (uint8_t *)&filterMode, sizeof(int));
        esp_now_send(node2MACAddress, (uint8_t *)&filterMode, sizeof(int));
        esp_now_send(node3MACAddress, (uint8_t *)&filterMode, sizeof(int));
        esp_now_send(node4MACAddress, (uint8_t *)&filterMode, sizeof(int));
        
        // let ESP2 know ESP1 got the new frequency
        Serial.println("[ACK] OK");
      }
    }

  }

}

