/*
  R Santos  ricardos@lnec.pt
  THE GATEWAY TO MQTT
  UART -> MQTT
*/

#ifdef ESP8266
#include <ESP8266WiFi.h>
#else
#include <WiFi.h>
#endif

//MQTT
#include <PubSubClient.h>      // mqtt client

// (de)serielize Json objects
#include <ArduinoJson.h>

/****** WiFi Connection Details *******/
const char* ssid = "networkname";   // CHANGE ME
const char* password = "password";  // CHANGE ME

/******* MQTT Broker Connection Details *******/
const char* mqtt_server = "172.XX.XX.X";  // CHANGE ME
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


/****** general inclinometer settings *******/
const uint inc_number = 1;      //inclinometer number
const char inc_code[] = "I1";   //inclinometer designator
const char inc_description[] =  //inclinometer description
  "Test inclinometer n. 1";
const int sensors_totalNumber = 1;               // number of sensors in the inclinometer 

const int capacity = JSON_OBJECT_SIZE(1) + JSON_OBJECT_SIZE(sensors_totalNumber) * 4 * 2 + JSON_OBJECT_SIZE(12) * 1.5;  // some buffer safety is considered!

const int led = LED_BUILTIN;

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

  // Check if WiFi is connected
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
      client.subscribe("commands/IPI/frequency");
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

/***** Call back Method for Receiving MQTT messages and Switching LED ****/
void callback(char* topic, byte* payload, unsigned int length) {
  String incommingMessage = "";
  for (int i = 0; i < length; i++) incommingMessage += (char)payload[i];

  Serial.println("Message arrived [" + String(topic) + "]" + incommingMessage);

  //--- check the incomming message
  if (strcmp(topic, "led_state") == 0) {
    if (incommingMessage.equals("0")) {
      digitalWrite(led, HIGH);  // Turn the LED on
    } else {
      digitalWrite(led, LOW);  // Turn the LED off
    }
  }
  else if (strcmp(topic, "commands/IPI/frequency") == 0) {
    // int intValue = atoi(incommingMessage);
    update_reading_frequency(incommingMessage);
  }
  else if (strcmp(topic, "commands/IPI/getreading") == 0){
    //TODO
  }
  else if (strcmp(topic, "commands/IPI/toggle") == 0){
    //TODO
  }
  else if (strcmp(topic, "status")){
    //TODO
  }
  else{
    Serial.println("Unknown topic.");
  }

}

void update_reading_frequency(String frequency) {
  String prefix = "[COMMAND] [FREQ] ";
  prefix += frequency;
  Serial.println(prefix); // example message: "[COMMAND] [FREQ] 10000"
}


/**** Method for Publishing MQTT Messages **********/
void publishMessage(const char* topic, String payload, boolean retained) {

  if (!client.connected()) {
    Serial.println("ERROR: MQTT Client is not connected. Reconnecting...");
    return;
  }

  client.loop();
  bool aux = client.publish(topic, payload.c_str(), true);
  if (aux)
    Serial.println("Message published [" + String(topic) + "]: " + payload);
  else
    Serial.println("ERROR: Message failed to publish!");
}


void setup() {

  Serial.begin(9600);
  while (!Serial) delay(1);

  pinMode(led, OUTPUT);
  digitalWrite(led, HIGH);

  setup_wifi();

  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
  client.setBufferSize(512);
}

/**** Method for joining two json objects  **********/
void merge(JsonObject dest, JsonObjectConst src) {
  for (JsonPairConst kvp : src) {
    dest[kvp.key()] = kvp.value();
  }
}


/**** Method to deal with msg received from Serial port **********/
void receiveJSONData() {
  if (!client.connected()) reconnect();
  client.loop();

  if (!Serial.available()) return;

  String jsonIncString = Serial.readStringUntil('\n');
  jsonIncString.trim(); // remove whitespace + newline

  //  Abort if empty, too small or invalid
  if (jsonIncString.length() < 10 || jsonIncString.charAt(0) != '{') {
    return;
  }

  DynamicJsonDocument jsonInc(capacity);
  DeserializationError error = deserializeJson(jsonInc, jsonIncString);
  if (error) {
    Serial.print(" Failed to parse JSON: ");
    Serial.println(error.c_str());
    return;
  }

  DynamicJsonDocument jsonIncSets(capacity);
  jsonIncSets["inc_number"] = inc_number;
  jsonIncSets["inc_code"] = inc_code;

  merge(jsonIncSets.as<JsonObject>(), jsonInc.as<JsonObject>());
  char mqtt_message[capacity];
  serializeJson(jsonIncSets, mqtt_message);

  const char prefix[] = "inc_data/";
  char topic_pub[32];
  strcpy(topic_pub, prefix);
  strcat(topic_pub, inc_code);

  publishMessage(topic_pub, mqtt_message, true);
}


void loop() {
  receiveJSONData();
}