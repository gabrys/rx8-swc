import math
import time

import analogio
import board
import microcontroller

import adafruit_ble
from adafruit_ble.services.standard.hid import HIDService
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement

from adafruit_hid.consumer_control import ConsumerControl

import adafruit_dotstar


# LED

dotstar = adafruit_dotstar.DotStar(
    board.DOTSTAR_CLOCK,
    board.DOTSTAR_DATA,
    1,
    brightness=0.15,
)

rainbow_phase = 0.0
flash_until = 0


def set_led(r, g, b):
    # Compensate for the red LED channel being noticeably brighter.
    r = r // 2

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


# ADC

adc = analogio.AnalogIn(board.A4)
reference_voltage = adc.reference_voltage * 1000


def read_adc_voltage_mv():
    raw = adc.value
    return round(raw * reference_voltage / 65535)


print("ADC reference voltage:", round(reference_voltage), "mV")

print(
    "Current voltage:",
    read_adc_voltage_mv(),
    "mV"
)

if reference_voltage > 3400 or reference_voltage < 3200:
    print(
        "Reference voltage out of expected range: "
        "should be 3300 mV"
    )

    set_led(255, 0, 255)

    time.sleep(5)
    microcontroller.reset()


# BLE HID Consumer Control only

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

hid = HIDService(hid_descriptor=CONSUMER_CONTROL_DESCRIPTOR)

advertisement = ProvideServicesAdvertisement(hid)
advertisement.complete_name = "Bulbulator"

cc = ConsumerControl(hid.devices)


last_code_sent = None


def send(code):
    global last_code_sent

    if code == 0x00B1:
        if last_code_sent == 0x00B1:
            return

        flash()

        cc.send(0x00B0)  # PLAY
        cc.send(0x00CD)  # PLAY_PAUSE

    else:
        flash()
        cc.send(code)

    last_code_sent = code


# Steering wheel button state detection

def detect_state(voltage_mv):
    if voltage_mv < 100:
        return "NONE_LO"
    if voltage_mv < 350:
        return "VOL_DOWN"
    if voltage_mv < 675:
        return "VOL_UP"
    if voltage_mv < 1025:
        return "PREV"
    if voltage_mv < 1400:
        return "NEXT"
    return "NONE_HI"


previous_state = "NONE_HI"
voltage_print_counter = 0


# Start BLE advertising

ble.start_advertising(advertisement)
print("BLE advertising started")


try:
    while not ble.connected:
        update_led()
        time.sleep(0.1)

    print("BLE connected")

    while ble.connected:
        time.sleep(0.01)
        update_led()

        voltage_mv = read_adc_voltage_mv()
        state = detect_state(voltage_mv)

        voltage_print_counter += 1

        if voltage_print_counter >= 200:
            print(state, voltage_mv, "mV")
            voltage_print_counter = 0

        if state != previous_state:
            previous_state = state

            print(state, voltage_mv, "mV")

            if state == "NEXT":
                send(0x00B5)  # NEXT_TRACK

            elif state == "PREV":
                send(0x00B6)  # PREV_TRACK

            elif state == "VOL_UP":
                send(0x00B0)  # PLAY

            elif state == "VOL_DOWN":
                send(0x00B1)  # PAUSE

    print("BLE disconnected, resetting...")

    set_led(255, 255, 0)

except Exception as e:
    print("Error:", e)
    print("Resetting...")

    set_led(255, 0, 0)


time.sleep(1)
microcontroller.reset()
