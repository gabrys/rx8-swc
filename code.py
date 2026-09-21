import math
import time

import analogio
import board
import digitalio
import microcontroller

import adafruit_ble
import adafruit_dotstar

from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.standard.hid import HIDService

from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode


# =========================================================
# CONFIGURATION
# =========================================================

DEVICE_NAME = "Bulbulator"

# ADC
ADC_PIN = board.A4
MOVING_AVG_SIZE = 3

# Mazda RX-8 SWC thresholds
THRESH_PREV = 650
THRESH_NEXT = 1000
THRESH_NONE = 1400

# Debounce
DEBOUNCE_TIME = 0.12
BUTTON_DEBOUNCE = 0.12

# Double press
DOUBLE_PRESS_TIME = 0.4


# =========================================================
# BLE HID REPORT DESCRIPTOR
# =========================================================
#
# IMPORTANT:
#
# The default CircuitPython HIDService contains:
#   - Keyboard
#   - Mouse
#   - Consumer Control
#
# We don't want Keyboard or Mouse.
#
# This descriptor exposes ONLY:
#
#   HID
#     └── Consumer Control
#
# Report:
#   - Report ID: 1
#   - 16-bit Consumer Control usage
#
# This is the same Consumer Control part used by the
# standard Adafruit HID descriptor, but without the
# keyboard and mouse collections.
#
# =========================================================

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


# =========================================================
# DOTSTAR LED
# =========================================================

led = adafruit_dotstar.DotStar(
    board.APA102_SCK,
    board.APA102_MOSI,
    1,
    brightness=0.08,
)


def set_led(r, g, b):
    # Kompensacja czerwonego kanału
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

    # Flash ma priorytet
    if in_flash and now < flash_until:
        return

    in_flash = False

    if ble.connected:
        set_led(*rainbow())
    else:
        # Oczekiwanie na BLE
        set_led(0, 0, 255)


def flash(duration=0.2):
    global in_flash
    global flash_until

    in_flash = True
    flash_until = time.monotonic() + duration

    set_led(255, 255, 255)


# =========================================================
# BLE HID
# =========================================================

ble = adafruit_ble.BLERadio()

ble.name = DEVICE_NAME

# IMPORTANT:
# Use a custom HID report descriptor containing ONLY
# Consumer Control.
hid = HIDService(
    hid_descriptor=CONSUMER_CONTROL_DESCRIPTOR
)

advertisement = ProvideServicesAdvertisement(hid)
advertisement.complete_name = DEVICE_NAME

# Adafruit ConsumerControl automatically finds the HID
# device with Usage Page 0x0C / Usage 0x01.
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

adc = analogio.AnalogIn(ADC_PIN)

reference_voltage = adc.reference_voltage

print("ADC reference voltage:", reference_voltage, "V")
print(
    "Current voltage:",
    adc.value * reference_voltage / 65535,
    "V"
)

if reference_voltage > 3.4 or reference_voltage < 3.2:
    print(
        "Reference voltage out of expected range: "
        "should be 3.3V"
    )

    set_led(255, 0, 0)

    time.sleep(5)

    microcontroller.reset()


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

    voltage_mv = (
        avg * reference_voltage * 1000 / 65535
    )

    return voltage_mv


# =========================================================
# MAZDA RX-8 SWC
# =========================================================

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

button_last = True
button_debounce_time = 0


# =========================================================
# START
# =========================================================

print()
print("========================================")
print("Bulbulator")
print("BLE HID Consumer Control")
print("========================================")
print()

print("BLE name:", DEVICE_NAME)
print("HID: Consumer Control only")
print("Mouse: disabled")
print("Keyboard: disabled")
print()

ble.start_advertising(advertisement)

rainbow_phase = 0.0

last_state = "NONE"
stable_state = "NONE"

last_next_press = 0.0
last_prev_press = 0.0

last_change_time = time.monotonic()


# =========================================================
# MAIN LOOP
# =========================================================

try:

    while True:

        # -------------------------------------------------
        # Czekanie na BLE
        # -------------------------------------------------

        while not ble.connected:

            update_led()

            time.sleep(0.1)

        print("BLE connected")

        # -------------------------------------------------
        # Połączony
        # -------------------------------------------------

        while ble.connected:

            now = time.monotonic()

            update_led()

            # -------------------------------------------------
            # USER BUTTON -> PLAY/PAUSE
            # -------------------------------------------------

            button_state = button.value

            # Falling edge:
            # HIGH -> LOW
            if not button_state and button_last:

                if (
                    now - button_debounce_time
                    > BUTTON_DEBOUNCE
                ):

                    print("USER BUTTON -> PLAYPAUSE")

                    flash()

                    send("PLAYPAUSE")

                    button_debounce_time = now

            # IMPORTANT:
            # Update previous button state every loop.
            button_last = button_state

            # -------------------------------------------------
            # ADC SWC
            # -------------------------------------------------

            voltage = read_adc_filtered()

            state = detect_state(voltage)

            # -------------------------------------------------
            # Debounce kierownicy
            # -------------------------------------------------

            if state != last_state:

                last_state = state

                last_change_time = now

            if (
                now - last_change_time
                > DEBOUNCE_TIME
            ):

                if state != stable_state:

                    stable_state = state

                    print(
                        stable_state,
                        round(voltage),
                        "mV"
                    )

                    # -----------------------------------------
                    # NEXT
                    # -----------------------------------------

                    if stable_state == "NEXT":

                        flash()

                        # First press:
                        # PLAY
                        #
                        # Second press within
                        # DOUBLE_PRESS_TIME:
                        # NEXT TRACK

                        if (
                            now - last_next_press
                            > DOUBLE_PRESS_TIME
                        ):

                            send("PLAY")

                        else:

                            send("NEXT")

                        last_next_press = now

                    # -----------------------------------------
                    # PREV
                    # -----------------------------------------

                    elif stable_state == "PREV":

                        flash()

                        # First press:
                        # PAUSE
                        #
                        # Second press within
                        # DOUBLE_PRESS_TIME:
                        # PREVIOUS TRACK

                        if (
                            now - last_prev_press
                            > DOUBLE_PRESS_TIME
                        ):

                            send("PAUSE")

                        else:

                            send("PREV")

                        last_prev_press = now

            time.sleep(0.007)

        # -------------------------------------------------
        # Rozłączenie
        # -------------------------------------------------

        print("BLE disconnected")

        ble.start_advertising(advertisement)


except Exception as e:

    print(
        type(e).__name__,
        e
    )

    try:
        set_led(255, 0, 0)
    except Exception:
        pass

    time.sleep(5)

    microcontroller.reset()
