"""
Boot configuration for Feather S2 board with SCD-30 sensor
This file runs before code.py and configures the board's behavior
"""
import supervisor
import board
import digitalio
import time

# Disable auto-reload to prevent interruptions
supervisor.runtime.autoreload = False

# Disable REPL completely
supervisor.set_next_stack_limit(0)  # Disable REPL
supervisor.disable_autoreload()     # Disable auto-reload

# Set up the built-in LED to indicate boot status
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT

# Flash LED to indicate boot.py is running
for _ in range(3):
    led.value = True
    time.sleep(0.1)
    led.value = False
    time.sleep(0.1)

print("Boot configuration complete - REPL and auto-reload disabled")
