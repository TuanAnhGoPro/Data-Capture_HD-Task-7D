// Task 7H - Arduino sketch v2 (hardening). Changes compared with the Task 4P version:
// 1) PIR uses an interrupt -> counts EVERY motion event during the 5-minute cycle, not just one read at send time
// 2) No long delay() -> the loop keeps running and does not miss events
// 3) DHT22 is read up to 3 times before an error is reported
// 4) Sequence number (seq) added -> the PC can detect lost lines even if the PC clock drifts
// Output: seq,temperature,humidity,motion_any,motion_count,dht_retries
//     or: ERR,seq,dht_fail
#include <DHT.h>

#define DHTPIN 2
#define DHTTYPE DHT22
#define PIRPIN 3
const unsigned long INTERVAL_MS = 300000UL;   // 5 minutes per sample

DHT dht(DHTPIN, DHTTYPE);
volatile unsigned int motionCount = 0;
unsigned long lastSend = 0;
unsigned long seq = 0;

void onMotion() { motionCount++; }             // ISR: only increments the counter, kept as short as possible

void setup() {
  Serial.begin(9600);
  dht.begin();
  pinMode(PIRPIN, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIRPIN), onMotion, RISING);
  delay(2000);                                  // let the sensors stabilise
  lastSend = millis();
}

void loop() {
  if (millis() - lastSend < INTERVAL_MS) return;   // non-blocking
  lastSend += INTERVAL_MS;                          // keep a steady cycle without drifting
  seq++;

  float t = NAN, h = NAN;
  int retries = 0;
  while (retries < 3) {
    t = dht.readTemperature();
    h = dht.readHumidity();
    if (!isnan(t) && !isnan(h)) break;
    retries++;
    delay(2000);                                    // DHT22 needs >= 2 s between two reads
  }

  noInterrupts();                                   // read and reset the counter safely
  unsigned int count = motionCount;
  motionCount = 0;
  interrupts();
  // PIR still HIGH at send time (someone is moving) also counts as motion
  int motionAny = (count > 0 || digitalRead(PIRPIN) == HIGH) ? 1 : 0;

  if (isnan(t) || isnan(h)) {
    Serial.print("ERR,"); Serial.print(seq); Serial.println(",dht_fail");
    return;                                         // keep the rhythm: the next sample is still sent on time
  }
  Serial.print(seq); Serial.print(",");
  Serial.print(t, 1); Serial.print(",");
  Serial.print(h, 1); Serial.print(",");
  Serial.print(motionAny); Serial.print(",");
  Serial.print(count); Serial.print(",");
  Serial.println(retries);
}
