import math
import time

import analogio
import board
import digitalio

import adafruit_ble
from adafruit_ble.services.standard.hid import HIDService
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement

from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode

import adafruit_dotstar


# ============================================================
# LED
# ============================================================

dotstar = adafruit_dotstar.DotStar(
    board.DOTSTAR_CLOCK,
    board.DOTSTAR_DATA,
    1,
    brightness=0.15,
)

rainbow_phase = 0.0
flash_until = 0


def set_led(r, g, b):
    dotstar[0] = (r, g, b)


def rainbow():
    global rainbow_phase

    rainbow_phase += 0.03

    r = int((math.sin(rainbow_phase) + 1) * 127.5)
    g = int((math.sin(rainbow_phase + 2.094) + 1) * 127.5)
    b = int((math.sin(rainbow_phase + 4.188) + 1) * 127.5)

    set_led(r, g, b)


def flash():
    global flash_until
    flash_until = time.time() + 0.08


def update_led():
    now = time.time()

    if now < flash_until:
        set_led(255, 255, 255)
        return

    if ble.connected:
        rainbow()
    else:
        set_led(0, 0, 255)


# ============================================================
# BLE HID - Consumer Control only
# ============================================================

CONSUMER_CONTROL_DESCRIPTOR = bytes(
    (
        0x05, 0x0C,       # Usage Page (Consumer)
        0x09, 0x01,       # Usage (Consumer Control)
        0xA1, 0x01,       # Collection (Application)

        0x85, 0x01,       # Report ID (1)

        0x75, 0x10,       # Report Size (16 bits)
        0x95, 0x01,       # Report Count (1)

        0x15, 0x01,       # Logical Minimum (1)
        0x26, 0x8C, 0x02, # Logical Maximum (652)

        0x19, 0x01,       # Usage Minimum (1)
        0x2A, 0x8C, 0x02, # Usage Maximum (652)

        0x81, 0x00,       # Input (Data, Array, Absolute)

        0xC0,             # End Collection
    )
)


ble = adafruit_ble.BLERadio()
ble.name = "Bulbulator"

hid = HIDService(
    hid_descriptor=CONSUMER_CONTROL_DESCRIPTOR
)

advertisement = ProvideServicesAdvertisement(hid)
advertisement.complete_name = "Bulbulator"

cc = ConsumerControl(hid.devices)


def send(action):
    if action == "NEXT":
        cc.send(ConsumerControlCode.SCAN_NEXT_TRACK)

    elif action == "PREV":
        cc.send(ConsumerControlCode.SCAN_PREVIOUS_TRACK)

    elif action == "PLAY":
        cc.send(ConsumerControlCode.PLAY)

    elif action == "PAUSE":
        cc.send(ConsumerControlCode.PAUSE)

    elif action == "PLAYPAUSE":
        cc.send(ConsumerControlCode.PLAY_PAUSE)


# ============================================================
# ADC
# ============================================================

adc = analogio.AnalogIn(board.A4)

reference_voltage = adc.reference_voltage


def read_adc_voltage_mv():
    raw = adc.value

    # Zawsze zwracamy mV
    return raw * reference_voltage * 1000 / 65535


# ============================================================
# Steering wheel thresholds
# Wszystkie wartości w mV
# ============================================================

THRESH_PREV = 650
THRESH_NEXT = 1000
THRESH_NONE = 1400


def detect_state(voltage_mv):
    if voltage_mv < THRESH_PREV:
        return "PREV"

    if voltage_mv < THRESH_NEXT:
        return "NEXT"

    if voltage_mv < THRESH_NONE:
        return "NONE"

    return "NONE"


# ============================================================
# Physical button
# ============================================================

button = digitalio.DigitalInOut(board.SWITCH)
button.direction = digitalio.Direction.INPUT
button.pull = digitalio.Pull.UP

button_last = False
button_debounce_time = 0
BUTTON_DEBOUNCE = 0.12


# ============================================================
# State
# ============================================================

last_state = "NONE"
stable_state = "NONE"

last_change_time = time.time()
last_voltage_print = time.time()


# ============================================================
# Start BLE
# ============================================================

ble.start_advertising(advertisement)

set_led(0, 0, 255)


# ============================================================
# Main loop
# ============================================================

while True:

    try:

        # ----------------------------------------------------
        # Waiting for BLE connection
        # ----------------------------------------------------

        while not ble.connected:
            update_led()
            time.sleep(0.1)

        # ----------------------------------------------------
        # Connected
        # ----------------------------------------------------

        while ble.connected:

            now = time.time()

            # LED / rainbow effect
            update_led()

            # ------------------------------------------------
            # Read voltage
            # ------------------------------------------------

            voltage_mv = read_adc_voltage_mv()

            # Raportowanie napięcia co sekundę
            if now - last_voltage_print >= 1.0:
                print("Voltage:", round(voltage_mv), "mV")
                last_voltage_print = now

            # ------------------------------------------------
            # Physical button -> PLAY/PAUSE
            # ------------------------------------------------

            button_pressed = not button.value

            if button_pressed and not button_last:
                if now - button_debounce_time >= BUTTON_DEBOUNCE:
                    flash()
                    send("PLAYPAUSE")
                    button_debounce_time = now

            button_last = button_pressed

            # ------------------------------------------------
            # Steering wheel buttons
            # ------------------------------------------------

            state = detect_state(voltage_mv)

            if state != last_state:
                last_state = state
                last_change_time = now

            # Bez debounce SWC.
            # Reagujemy natychmiast na zmianę stanu.

            if state != stable_state:
                stable_state = state

                print(
                    stable_state,
                    round(voltage_mv),
                    "mV"
                )

                if stable_state == "NEXT":
                    flash()
                    send("NEXT")

                elif stable_state == "PREV":
                    flash()
                    send("PREV")

        # ----------------------------------------------------
        # Disconnected
        # ----------------------------------------------------

        set_led(0, 0, 255)

        ble.start_advertising(advertisement)

        last_state = "NONE"
        stable_state = "NONE"
        button_last = False

        last_change_time = time.time()
        last_voltage_print = time.time()

    except Exception as e:

        print("Error:", e)

        set_led(255, 0, 0)

        time.sleep(5)

        try:
            ble.stop_advertising()
        except Exception:
            pass

        last_state = "NONE"
        stable_state = "NONE"
        button_last = False

        last_change_time = time.time()
        last_voltage_print = time.time()

        set_led(0, 0, 255)

        ble.start_advertising(advertisement)
