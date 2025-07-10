/*
  R Santos 2023
  
  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files.
  
  The above copyright notice and this permission notice shall be included in all
  copies or substantial portions of the Software.
*/

/*
Sensor (ADXL345) reading and communication via ESPNOW to gateway 1
*/


#include <ESP8266WiFi.h>
#include <espnow.h>
#include "time.h"

// Set your Board ID (ESP Sender #1 = BOARD_ID 1, ESP Sender #2 = BOARD_ID 2, etc)
#define BOARD_ID 1   // <----- CHANGE ME

// for the sensor
#include <Wire.h>
#include <ADXL345_WE.h>
#define ADXL345_I2CADDR 0x53
ADXL345_WE myAcc = ADXL345_WE(ADXL345_I2CADDR);

// REPLACE WITH RECEIVER MAC Address
uint8_t broadcastAddress[] = {0X80, 0x7D, 0x3A, 0xB7, 0x76, 0x9C};

//Structure example to send data
//Must match the receiver structure
typedef struct struct_message {
  int id;
  float alphaX;
  float alphaY;
  float alphaZ;
  unsigned int readingId;
  uint64_t timestamp;
} struct_message;

// Create a struct_message called myData
struct_message myData;

unsigned long lastTime = 0;  
unsigned long timerDelay = 10000;  // send readings timer <----- CHANGE ME

unsigned int readingId = 0;

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

void OnDataRecv(uint8_t * mac, uint8_t *incomingData, uint8_t len) {
  if (len == sizeof(int)) {
    int newFreq;
    memcpy(&newFreq, incomingData, sizeof(int));
    timerDelay = newFreq;
    Serial.print("Received new frequency: ");
    Serial.println(timerDelay);
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
  /* Choose the data rate         Hz
    ADXL345_DATA_RATE_50        50
    ADXL345_DATA_RATE_25        25
    ADXL345_DATA_RATE_12_5      12.5  
    ADXL345_DATA_RATE_6_25       6.25
  */
  myAcc.setDataRate(ADXL345_DATA_RATE_50);
  myAcc.setRange(ADXL345_RANGE_2G);
  /* Uncomment to enable Low Power Mode. It saves power but slightly
    increases noise. LowPower only affetcs Data Rates 12.5 Hz to 400 Hz.
  */
  // myAcc.setLowPower(true);

  // Set device as a Wi-Fi Station
  WiFi.mode(WIFI_STA);

  Serial.print("[DEFAULT] ESP32 Board MAC Address: ");
  Serial.println(WiFi.macAddress());


  // Init ESP-NOW descomentar daqui para baixo
  if (esp_now_init() != 0) {
    Serial.println("Error initializing ESP-NOW");
    return;
  }

  
  // Once ESPNow is successfully Init, we will register for Send CB to
  // get the status of Trasnmitted packet
  esp_now_set_self_role(ESP_NOW_ROLE_CONTROLLER);
  esp_now_register_send_cb(OnDataSent);
  esp_now_register_recv_cb(OnDataRecv);
  
  // Register peer
  esp_now_add_peer(broadcastAddress, ESP_NOW_ROLE_SLAVE, 1, NULL, 0);

  xyzFloat angle;
  myAcc.getAngles(&angle); 

  // unsync data sends based on the boards id, so they don't all send data at the same time to the broker
  delay(BOARD_ID*400);
}
 
void loop() {
  if ((millis() - lastTime) > timerDelay) {
    lastTime = millis();

    const int numberReads = 25;
    xyzFloat angle;
    float xVals[numberReads], yVals[numberReads], zVals[numberReads];

    // Collect readings
    for (int i = 0; i < numberReads; i++) {
      myAcc.getAngles(&angle);
      xVals[i] = angle.x;
      yVals[i] = angle.y;
      zVals[i] = angle.z;
      delay(20);
    }

    // Compute means
    float sumX = 0, sumY = 0, sumZ = 0;
    for (int i = 0; i < numberReads; i++) {
      sumX += xVals[i];
      sumY += yVals[i];
      sumZ += zVals[i];
    }
    float meanX = sumX / numberReads;
    float meanY = sumY / numberReads;
    float meanZ = sumZ / numberReads;

    // Compute standard deviations
    float varX = 0, varY = 0, varZ = 0;
    for (int i = 0; i < numberReads; i++) {
      varX += pow(xVals[i] - meanX, 2);
      varY += pow(yVals[i] - meanY, 2);
      varZ += pow(zVals[i] - meanZ, 2);
    }
    float stdX = sqrt(varX / numberReads);
    float stdY = sqrt(varY / numberReads);
    float stdZ = sqrt(varZ / numberReads);

    // Filter out outliers
    float filteredSumX = 0, filteredSumY = 0, filteredSumZ = 0;
    int filteredCountX = 0, filteredCountY = 0, filteredCountZ = 0;

    for (int i = 0; i < numberReads; i++) {
      if (abs(xVals[i] - meanX) <= stdX) {
        filteredSumX += xVals[i];
        filteredCountX++;
      }
      if (abs(yVals[i] - meanY) <= stdY) {
        filteredSumY += yVals[i];
        filteredCountY++;
      }
      if (abs(zVals[i] - meanZ) <= stdZ) {
        filteredSumZ += zVals[i];
        filteredCountZ++;
      }
    }

    float angleX = (filteredCountX > 0) ? filteredSumX / filteredCountX : meanX;
    float angleY = (filteredCountY > 0) ? filteredSumY / filteredCountY : meanY;
    float angleZ = (filteredCountZ > 0) ? filteredSumZ / filteredCountZ : meanZ;

    // Set values to send
    myData.id = BOARD_ID;
    myData.alphaX = angleX;
    myData.alphaY = angleY;
    myData.alphaZ = angleZ;
    myData.readingId = readingId++;

    // Debug output
    Serial.print("angle-x: "); Serial.println(myData.alphaX);
    Serial.print("angle-y: "); Serial.println(myData.alphaY);
    Serial.print("angle-z: "); Serial.println(myData.alphaZ);
    Serial.print("readingID: "); Serial.println(myData.readingId);

    // Send message via ESP-NOW
    esp_now_send(broadcastAddress, (uint8_t*)&myData, sizeof(myData));
  }
}
