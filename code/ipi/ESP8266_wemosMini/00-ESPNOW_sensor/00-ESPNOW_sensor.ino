// /*
//   R Santos 2023
  
//   Permission is hereby granted, free of charge, to any person obtaining a copy
//   of this software and associated documentation files.
  
//   The above copyright notice and this permission notice shall be included in all
//   copies or substantial portions of the Software.
// */


// /*
//   D Eugénio 2025

//   Extension of the previously developed work by R Santos.
  
//   Permission is hereby granted, free of charge, to any person obtaining a copy
//   of this software and associated documentation files.
  
//   The above copyright notice and this permission notice shall be included in all
//   copies or substantial portions of the Software.
// */

// Set your Board ID (ESP Sender #1 = BOARD_ID 1, ESP Sender #2 = BOARD_ID 2, etc)
#define BOARD_ID 1   // <----- CHANGE ME

// for the sensor
#include <Wire.h>
#include <ADXL345_WE.h>
#define ADXL345_I2CADDR 0x53
ADXL345_WE myAcc = ADXL345_WE(ADXL345_I2CADDR);

// REPLACE WITH RECEIVER MAC Address
uint8_t broadcastAddress[] = {0X80, 0x7D, 0x3A, 0xB7, 0x76, 0x9C};

// ESP0 <-> ESP1 reliability feature
bool ackReceived = false;
unsigned int lastSentReadingId = 0;
const int maxRetries = 3;
const unsigned long ackTimeout = 300; // ms
const char ack[] = "[ACK] OK";

const char* ssid = "ssid";
const char* password = "password";

// Structure to send data (must match the receiver structure)
typedef struct struct_message {
  int id;
  float alphaX;
  float alphaY;
  float alphaZ;
  unsigned int readingId;
} struct_message;

// Create a struct_message called myData
struct_message myData;

unsigned long lastTime = 0;
unsigned long timerDelay = 10000;  // send readings timer <----- CHANGE ME
const int numberReads = 25;   // number of samples for a single reading
int filterMode = 1; // 0 - just average | 1 - standard deviation
unsigned int readingId = 0;

void OnDataSent(uint8_t *mac_addr, uint8_t sendStatus) {
  Serial.print("Last Packet Send Status: ");
  if (sendStatus == 0){
    Serial.println("Delivery success");
  }
  else{
    Serial.println("Delivery fail");
  }
}

void OnDataRecv(uint8_t * mac, uint8_t *incomingData, uint8_t len) {
  if (len == sizeof(int)) {
    int newVal;
    memcpy(&newVal, incomingData, sizeof(int));
    if (newVal > 1){ // received frequency value
      timerDelay = newVal;
      Serial.print("Received new frequency: ");
      Serial.println(timerDelay);
    }
    else{

    }
    // Send ACK back to ESP1
    esp_now_send(broadcastAddress, (uint8_t*)ack, sizeof(ack));
  } else {
    // Accept ACK message
    String msg = "";
    for (int i = 0; i < len; i++) {
      msg += (char)incomingData[i];
    }

    if (msg == "[ACK] OK") {
      ackReceived = true;
      Serial.println("ACK received from ESP1");
    }
  }
}

void setup() {
  // Init Serial Monitor
  Serial.begin(9600);

  // for I2C communication with ADXL345
  Wire.begin(4,5);  // () for lolin C3;  (4, 5) for wemos D1 mini
  if (!myAcc.init()) {
    Serial.println("ADXL345 not connected!");
  }
  myAcc.setDataRate(ADXL345_DATA_RATE_50);
  myAcc.setRange(ADXL345_RANGE_2G);

  Serial.println("micros:" + micros());

  // Set device as a Wi-Fi Station
  WiFi.mode(WIFI_STA);

  // Init ESP-NOW
  if (esp_now_init() != 0) {
    Serial.println("Error initializing ESP-NOW");
    return;
  }

  esp_now_set_self_role(ESP_NOW_ROLE_CONTROLLER);
  esp_now_register_send_cb(OnDataSent);
  esp_now_register_recv_cb(OnDataRecv);
  
  // Register peer
  esp_now_add_peer(broadcastAddress, ESP_NOW_ROLE_SLAVE, 1, NULL, 0);

  delay(BOARD_ID*400);  // desynchronize the data sending from the ESPs based on their ID to avoid simultaneous transmission
}

void loop() {
  if ((millis() - lastTime) > timerDelay) {
    lastTime = millis();
    Serial.println("lasttime:"+ lastTime);

    // Step 1: Get sensor data
    xyzFloat angle;
    float xVals[numberReads], yVals[numberReads], zVals[numberReads];
    for (int i = 0; i < numberReads; i++) {
      myAcc.getAngles(&angle);
      xVals[i] = angle.x;
      yVals[i] = angle.y;
      zVals[i] = angle.z;
      delay(20);
    }

    // Step 2: Compute Averages
    float sumX = 0, sumY = 0, sumZ = 0;
    for (int i = 0; i < numberReads; i++) {
      sumX += xVals[i];
      sumY += yVals[i];
      sumZ += zVals[i];
    }

    float meanX = sumX / numberReads;
    float meanY = sumY / numberReads;
    float meanZ = sumZ / numberReads;

    float finalValueX = 0;
    float finalValueY = 0;
    float finalValueZ = 0;

    if(filterMode == 1){
      float varianceSumX = 0;
      float varianceSumY = 0;
      float varianceSumZ = 0;

      for (int i = 0; i < numberReads; i++) {
          varianceSumX += pow(xVals[i] - meanX, 2);
          varianceSumY += pow(yVals[i] - meanY, 2);
          varianceSumZ += pow(zVals[i] - meanZ, 2);
      }

      float stddevX = sqrt(varianceSumX / numberReads);
      float stddevY = sqrt(varianceSumY / numberReads);
      float stddevZ = sqrt(varianceSumZ / numberReads);

      // Step 3: Filter values within +-1 stddev
        int filteredCountX = 0;
        float filteredSumX = 0;

        int filteredCountY = 0;
        float filteredSumY = 0;

        int filteredCountZ = 0;
        float filteredSumZ = 0;

        for (int i = 0; i < validReadings; i++) {
          if (abs(xVals[i] - meanX) <= stddev) {
            filteredSumX += xVals[i];
            filteredCountX++;
          }

          if (abs(yVals[i] - meanY) <= stddev) {
            filteredSumY += yVals[i];
            filteredCountY++;
          }

          if (abs(zVals[i] - meanZ) <= stddev) {
            filteredSumZ += zVals[i];
            filteredCountZ++;
          }
        }

        if (filteredCountX == 0 || filteredCountY == 0)
          Serial.println("All readings were outliers, skipping...");
        else{
          int filteredAvgX = filteredSumX / filteredCountX;
          int filteredAvgY = filteredSumY / filteredCountY;
          int filteredAvgZ = filteredSumZ / filteredCountZ;

          finalValueX = filteredAvgX;
          finalValueY = filteredAvgY;
          finalValueZ = filteredAvgZ;

        }
    }
    // Fill myData with sensor data
    myData.id = BOARD_ID;
    myData.alphaX = (filterMode == 0) meanX : finalValueX;
    myData.alphaY = (filterMode == 0) meanY : finalValueY;
    myData.alphaZ = (filterMode == 0) meanZ : finalValueZ;
    myData.readingId = readingId++;

    // Debug output
    Serial.print("angle-x: "); Serial.println(myData.alphaX);
    Serial.print("angle-y: "); Serial.println(myData.alphaY);
    Serial.print("angle-z: "); Serial.println(myData.alphaZ);
    Serial.print("readingID: "); Serial.println(myData.readingId);
    Serial.print("timestamp: "); Serial.println(myData.timestamp);

    // Send data via ESP-NOW and wait for ACK
    ackReceived = false;
    int attempts = 0;

    while (attempts < maxRetries && !ackReceived) {
      esp_now_send(broadcastAddress, (uint8_t*)&myData, sizeof(myData));

      unsigned long start = millis();
      while (millis() - start < ackTimeout) {
        if (ackReceived) break;
        delay(100); // Avoid watch dog timer
      }

      if (!ackReceived) {
        attempts++;
        Serial.println("ACK not received, retrying...");
        delay(500);
      }
    }

    if (!ackReceived) 
      Serial.println("ERROR: Failed to get ACK from ESP1 after retries.");
    
    ackReceived = false;
    attempts = 0;
  }
  delay(1000);
}
