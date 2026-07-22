import math
import sys
import time

import analogio
import board
import digitalio
import microcontroller

import adafruit_ble
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.standard.hid import HIDService
import adafruit_dotstar
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode


# =========================================================
# DOTSTAR LED
# =========================================================

led = adafruit_dotstar.DotStar(
    board.APA102_SCK,
    board.APA102_MOSI,
    1,
    brightness=0.08
)


def set_led(r, g, b):
    # kompensacja czerwonego kanału
    r = int(r / 2)
    led[0] = (r, g, b)


# =========================================================
# LED ENGINE
# =========================================================

rainbow_phase = 0.0

in_flash = False
flash_until = 0


def rainbow():
    """
    Płynna tęcza.
    """

    global rainbow_phase

    r = (math.sin(rainbow_phase) + 1) * 127
    g = (math.sin(rainbow_phase + 2.094) + 1) * 127
    b = (math.sin(rainbow_phase + 4.188) + 1) * 127

    rainbow_phase += 0.03

    return int(r), int(g), int(b)


def update_led():
    global in_flash

    now = time.monotonic()

    # flash ma priorytet
    if in_flash and now < flash_until:
        return

    in_flash = False

    if ble.connected:
        set_led(*rainbow())
    else:
        # oczekiwanie na BLE
        set_led(0, 0, 255)


def flash(duration=0.2):
    global in_flash, flash_until

    in_flash = True
    flash_until = time.monotonic() + duration

    set_led(255, 255, 255)


# =========================================================
# BLE HID
# =========================================================

ble = adafruit_ble.BLERadio()
ble.name = "Bulbulator"

hid = HIDService()

advertisement = ProvideServicesAdvertisement(hid)
advertisement.complete_name = "Bulbulator"

cc = ConsumerControl(hid.devices)


def send(action):
    print("Sending", action)
    if action == "NEXT":
        cc.send(ConsumerControlCode.SCAN_NEXT_TRACK)
    elif action == "PREV":
        cc.send(ConsumerControlCode.SCAN_PREVIOUS_TRACK)
    elif action == "PLAY":
        cc.send(0x00B0)
    elif action == "PAUSE":
        cc.send(0x00B1)
    elif action == "PLAYPAUSE":
        cc.send(ConsumerControlCode.PLAY_PAUSE)


# =========================================================
# ADC SWC
# =========================================================

adc = analogio.AnalogIn(board.A4)

reference_voltage = adc.reference_voltage
print("ADC reference voltage:", reference_voltage, "V")
print("Current voltage:", adc.value * reference_voltage / 65535, "V")


if reference_voltage > 3.4 or reference_voltage < 3.2:
    print("Reference voltage out of expected range: should be 3.3V")
    set_led(255, 0, 0)
    time.sleep(5)
    microcontroller.reset()

MOVING_AVG_SIZE = 3
samples = []


def read_adc_filtered():
    """
    Odczyt ADC -> mV
    """
    raw = adc.value
    samples.append(raw)

    if len(samples) > MOVING_AVG_SIZE:
        samples.pop(0)

    avg = sum(samples) / len(samples)
    voltage_mv = avg * reference_voltage * 1000 / 65535
    return voltage_mv


# =========================================================
# MAZDA RX-8 SWC
# =========================================================

THRESH_PREV = 650
THRESH_NEXT = 1000
THRESH_NONE = 1400

DEBOUNCE_TIME = 0.12
DOUBLE_PRESS_TIME = 0.4


def detect_state(voltage_mv):
    if voltage_mv > THRESH_NONE:
        return "NONE_HI"
    elif voltage_mv > THRESH_NEXT:
        return "NEXT"
    elif voltage_mv > THRESH_PREV:
        return "PREV"
    else:
        return "NONE_LOW"


# =========================================================
# USER BUTTON
# =========================================================

button = digitalio.DigitalInOut(board.SWITCH)

button.direction = digitalio.Direction.INPUT
button.pull = digitalio.Pull.UP

button_last = False
button_debounce_time = 0
BUTTON_DEBOUNCE = 0.12


# =========================================================
# START
# =========================================================

print("Bulbulator start")

ble.start_advertising(advertisement)

rainbow_phase = 0.0

last_state = "NONE"
stable_state = "NONE"
last_next_press = 0.0
last_prev_press = 0.0

last_change_time = time.monotonic()
button_last = False

# =========================================================
# MAIN LOOP
# =========================================================

try:
    # reset board on any exception below:
    while True:

        # -----------------------------------------------------
        # Czekanie na BLE
        # -----------------------------------------------------

        while not ble.connected:
            update_led()
            time.sleep(0.1)

        print("BLE connected")

        # -----------------------------------------------------
        # Połączony
        # -----------------------------------------------------

        while ble.connected:
            now = time.monotonic()
            update_led()

            # -------------------------------------------------
            # USER BUTTON -> PLAYPAUSE
            # -------------------------------------------------

            button_state = button.value

            if not button_state and button_last:
                if now - button_debounce_time > BUTTON_DEBOUNCE:
                    print("USER BUTTON -> PLAYPAUSE")

                    flash()
                    send("PLAYPAUSE")
                    button_debounce_time = now

            button_last = button_state

            # -------------------------------------------------
            # ADC SWC
            # -------------------------------------------------

            voltage = read_adc_filtered()
            state = detect_state(voltage)

            # debounce kierownicy

            if state != last_state:
                last_state = state
                last_change_time = now

            if (now - last_change_time) > DEBOUNCE_TIME:
                if state != stable_state:
                    stable_state = state
                    print(stable_state, round(voltage), "mV")

                    if stable_state == "NEXT":
                        flash()

                        if now - last_next_press > DOUBLE_PRESS_TIME:
                            send("PLAY")
                        else:
                            send("NEXT")

                        last_next_press = now

                    elif stable_state == "PREV":
                        flash()

                        if now - last_prev_press > DOUBLE_PRESS_TIME:
                            send("PAUSE")
                        else:
                            send("PREV")

                        last_prev_press = now

            time.sleep(0.007)

        # -----------------------------------------------------
        # Rozłączenie
        # -----------------------------------------------------

        print("BLE disconnected")
        ble.start_advertising(advertisement)

except Exception as e:
    print(type(e).__name__, e)

    try:
        set_led(255, 0, 0)
    except Exception:
        pass

    time.sleep(5)
    microcontroller.reset()
