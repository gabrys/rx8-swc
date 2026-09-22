# rx8-swc

Bluetooth media controls for Mazda RX-8 steering wheel.

## Hardware

- Adafruit ItsyBitsy nRF52840 Express
- 22 kΩ potentiometer or two 11 kΩ resistors

## Controls

- VOL_UP → Play
- VOL_DOWN → Pause
- PREV → Previous track
- NEXT → Next track

## Wiring

The factory radio uses a resistive steering-wheel control ladder.

Use a 22 kΩ potentiometer as the divider:

- SWC signal → potentiometer
- Potentiometer wiper → `A4`
- Potentiometer GND → `GND`

Set the potentiometer to the center position:

- R = R = 11 kΩ

This divides the SWC voltage by 2 (as the radio powers this ladder with 5V).

## How it works

The steering wheel buttons generate different analog voltages through the original resistor ladder.
The ItsyBitsy reads this voltage on `A4` and identifies which button is pressed based on voltage ranges.
The selected button is then sent to the connected device over Bluetooth Low Energy as a HID Consumer Control command.
The onboard DotStar LED indicates the device state and button events.
