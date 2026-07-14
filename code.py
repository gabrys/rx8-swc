import time
import board
import analogio
import adafruit_ble
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.standard.hid import HIDService
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode

# =========================
# ADC
# =========================

adc = analogio.AnalogIn(board.A0)
print("ADC reference voltage:", adc.reference_voltage, "V")

# =========================
# FILTR ADC
# =========================

MOVING_AVG_SIZE = 10
samples = []


def read_adc_filtered():
    """
    Zwraca uśrednione napięcie ADC w mV.
    """
    value = adc.value
    samples.append(value)
    if len(samples) > MOVING_AVG_SIZE:
        samples.pop(0)
    avg = sum(samples) / len(samples)
    voltage_mv = avg * adc.reference_voltage * 1000 / 65535
    return voltage_mv


# =========================
# PROGI MAZDA RX-8 SWC
#
# napięcia po dzielniku 1:1
#
# 2200 mV  NONE
# 1600 mV  PREV
# 1200 mV  NEXT
#
# 850 mV i 500 mV ignorowane
# =========================

THRESH_NONE = 1900  # mV
THRESH_PREV = 1400  # mV
THRESH_NEXT = 1000  # mV

# =========================
# DEBOUNCE
# =========================

DEBOUNCE_TIME = 0.15
last_state = "NONE"
stable_state = "NONE"
last_change_time = 0

# =========================
# BLE HID
# =========================

ble = adafruit_ble.BLERadio()
hid = HIDService()
advertisement = ProvideServicesAdvertisement(hid)
cc = ConsumerControl(hid.devices)


def send_media_key(action):
    if action == "NEXT":
        cc.send(ConsumerControlCode.NEXT_TRACK)
    elif action == "PREV":
        cc.send(ConsumerControlCode.PREVIOUS_TRACK)

# =========================
# DETEKCJA
# =========================

def detect_state(voltage_mv):
    """
    Mapowanie napięcia [mV] -> przycisk.
    """
    if voltage_mv > THRESH_NONE:
        return "NONE"
    elif voltage_mv > THRESH_PREV:
        return "PREV"
    elif voltage_mv > THRESH_NEXT:
        return "NEXT"
    else:
        # pozostałe poziomy drabinki
        return "NONE"


# =========================
# TEST NAPIĘCIA STARTOWEGO
# =========================

time.sleep(0.5)
startup_voltage = read_adc_filtered()
print("Initial SWC voltage:", round(startup_voltage, 1), "mV")

# =========================
# START BLE
# =========================

print("Mazda RX-8 BLE SWC controller start")
ble.start_advertising(advertisement)

# =========================
# MAIN LOOP
# =========================

while True:
    while not ble.connected:
        time.sleep(0.2)
    print("BLE connected")
    while ble.connected:
        now = time.monotonic()
        voltage = read_adc_filtered()
        current_state = detect_state(voltage)
        if current_state != last_state:
            last_change_time = now
            last_state = current_state
        else:
            if (now - last_change_time) > DEBOUNCE_TIME:
                if stable_state != current_state:
                    stable_state = current_state
                    if stable_state == "NEXT":
                        print("NEXT TRACK", round(voltage, 0), "mV")
                        send_media_key("NEXT")
                    elif stable_state == "PREV":
                        print("PREV TRACK", round(voltage, 0), "mV")
                        send_media_key("PREV")
        time.sleep(0.02)
    print("BLE disconnected")
    ble.start_advertising(advertisement)
