import time
import board
import analogio

import adafruit_ble
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.standard.hid import HIDService

from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode


# =========================
# KONFIGURACJA ADC
# =========================

adc = analogio.AnalogIn(board.A0)

# Ilość próbek do średniej kroczącej
MOVING_AVG_SIZE = 10
samples = []

def read_adc_filtered():
    """Zwraca wygładzone odczyty ADC (moving average)."""
    value = adc.value

    samples.append(value)
    if len(samples) > MOVING_AVG_SIZE:
        samples.pop(0)

    return sum(samples) / len(samples)


# =========================
# PROGI (KALIBRACJA!)
# =========================
# UWAGA: trzeba dostosować do realnych napięć w Mazda RX-8

THRESH_NONE_MAX = 20000      # brak wciśnięcia
THRESH_PREV_MAX = 60000      # PREV
THRESH_NEXT_MAX = 120000     # NEXT

# Histereza (stabilizacja)
HYST = 3000


# =========================
# DEBOUNCE
# =========================
DEBOUNCE_TIME = 0.15  # sekundy

last_state = "NONE"
stable_state = "NONE"
last_change_time = 0


# =========================
# BLE HID (Consumer Control)
# =========================

ble = adafruit_ble.BLERadio()
hid = HIDService()
advertisement = ProvideServicesAdvertisement(hid)

cc = ConsumerControl(hid.devices)


def send_media_key(action):
    """Wysyła pojedynczą komendę multimedialną."""
    if action == "NEXT":
        cc.send(ConsumerControlCode.NEXT_TRACK)
    elif action == "PREV":
        cc.send(ConsumerControlCode.PREVIOUS_TRACK)


# =========================
# DETEKCJA STANU
# =========================

def detect_state(value):
    """
    Mapowanie napięcia ADC -> stan przycisku.
    Zakłada drabinkę rezystorową SWC.
    """

    if value < THRESH_NONE_MAX:
        return "NONE"
    elif value < THRESH_PREV_MAX:
        return "PREV"
    elif value < THRESH_NEXT_MAX:
        return "NEXT"
    else:
        return "NONE"


# =========================
# BLE CONNECT LOOP
# =========================

print("Start BLE HID SWC controller...")

ble.start_advertising(advertisement)

while True:
    # Czekaj na połączenie BLE
    while not ble.connected:
        time.sleep(0.2)

    print("BLE connected!")

    while ble.connected:
        now = time.monotonic()

        # 1. Odczyt i filtracja ADC
        filtered = read_adc_filtered()

        # 2. Detekcja stanu
        current_state = detect_state(filtered)

        # 3. Debounce + stabilizacja
        if current_state != last_state:
            last_change_time = now
            last_state = current_state
        else:
            # stan stabilny przez określony czas
            if (now - last_change_time) > DEBOUNCE_TIME:
                if stable_state != current_state:
                    stable_state = current_state

                    # 4. Reakcja tylko na zbocze (edge trigger)
                    if stable_state == "NEXT":
                        print("NEXT TRACK")
                        send_media_key("NEXT")

                    elif stable_state == "PREV":
                        print("PREV TRACK")
                        send_media_key("PREV")

        time.sleep(0.02)  # ~50 Hz loop

    print("BLE disconnected, advertising again...")
    ble.start_advertising(advertisement)
