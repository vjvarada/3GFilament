# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.events import eventManager, Events
from flask import jsonify, make_response
import RPi.GPIO as GPIO

class Julia3GFilament(octoprint.plugin.StartupPlugin,
                             octoprint.plugin.EventHandlerPlugin,
                             octoprint.plugin.TemplatePlugin,
                             octoprint.plugin.SettingsPlugin):

    def initialize(self):
        self._logger.info("Running RPi.GPIO version '{0}'".format(GPIO.VERSION))
        if GPIO.VERSION < "0.6":       # Need at least 0.6 for edge detection
            raise Exception("RPi.GPIO must be greater than 0.6")
        GPIO.setmode(GPIO.BCM)       # Use the board numbering scheme
        GPIO.setwarnings(False)        # Disable GPIO warnings

    def on_after_startup(self):
		self.sensorCount = int(self._settings.get(["sensorCount"]))
		self.sensor0MotorStepPin = int(self._settings.get(["sensor0MotorStepPin"]))
		self.sensor0DirPin = int(self._settings.get(["sensor0MotorStepPin"]))
		self.sensor0EncoderPin = int(self._settings.get(["sensor0EncoderPin"]))
		if self.sensorCount == 2:
			self.sensor1MotorStepPin = int(self._settings.get(["sensor1MotorStepPin"]))
			self.sensor1DirPin = int(self._settings.get(["sensor1MotorStepPin"]))
			self.sensor1EncoderPin = int(self._settings.get(["sensor1EncoderPin"]))
		self.bounce = int(self._settings.get(["bounce"]))
		if self.sensorCount != -1:   # If a pin is defined
			self._logger.info("Number of Filament Sensors active : "%self.sensorCount)
			GPIO.setup(self.sensor0MotorStepPin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)    # Initialize GPIO as INPUT
			GPIO.setup(self.sensor0DirPin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
			GPIO.setup(self.sensor0EncoderPin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
			GPIO.setup(self.sensor1MotorStepPin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)    # Initialize GPIO as INPUT
			GPIO.setup(self.sensor1DirPin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
			GPIO.setup(self.sensor1EncoderPin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)


    def get_settings_defaults(self):
        return dict(
			sensorCount  = 2,   # Default is no pin
			sensor0MotorStepPin = 13,
			sensor0DirPin = 16,
			sensor0EncoderPin = 5,
			sensor1MotorStepPin = 19,
			sensor1DirPin = 26,
			sensor1EncoderPin = 6,
            bounce  = 300  # Debounce 250ms
        )

    # def get_template_configs(self):
    #     return [dict(type="settings", custom_bindings=False)]

	# @octoprint.plugin.BlueprintPlugin.route("/status", methods=["GET"])
	# def check_status(self):
	# 	status = "-1"
	# 	if self.sensorCount != -1:
	# 		status = "1" if GPIO.input(self.PIN_FILAMENT) else "0"
	# 	return jsonify( status = status )

    def on_event(self, event, payload):
        if event == Events.PRINT_STARTED:  # If a new print is beginning
            self._logger.info("Printing started: Filament sensor enabled")
            if self.sensorCount != -1:
                GPIO.add_event_detect(self.sensor0MotorStepPin, GPIO.RISING, callback=self.check_gpio, bouncetime=self.bounce)
				GPIO.add_event_detect(self.sensor0DirPin, GPIO.RISING, callback=self.check_gpio,bouncetime=self.bounce)
				GPIO.add_event_detect(self.sensor0EncoderPin, GPIO.RISING, callback=self.check_gpio,bouncetime=self.bounce)
				if self.sensorCount == 2:
					GPIO.add_event_detect(self.sensor1MotorStepPin, GPIO.RISING, callback=self.check_gpio,bouncetime=self.bounce)
					GPIO.add_event_detect(self.sensor1DirPin, GPIO.RISING, callback=self.check_gpio,bouncetime=self.bounce)
					GPIO.add_event_detect(self.sensor1EncoderPin, GPIO.RISING, callback=self.check_gpio,bouncetime=self.bounce)


        elif event in (Events.PRINT_DONE, Events.PRINT_FAILED, Events.PRINT_CANCELLED):
            self._logger.info("Printing stopped: Filament sensor disabled")
            try:
                GPIO.remove_event_detect(self.pin)
            except Exception:
                pass

    def check_gpio(self, channel):
        state = GPIO.input(self.pin)
        self._logger.debug("Detected sensor [%s] state [%s]"%(channel, state))
        if state != self.switch:    # If the sensor is tripped
            self._logger.debug("Sensor [%s]"%state)
            if self._printer.is_printing():
                self._printer.toggle_pause_print()

    def get_update_information(self):
        return dict(
            octoprint_filament=dict(
                displayName="Filament Sensor Reloaded",
                displayVersion=self._plugin_version,

                # version check: github repository
                type="github_release",
                user="kontakt",
                repo="Octoprint-Filament-Reloaded",
                current=self._plugin_version,

                # update method: pip
                pip="https://github.com/kontakt/Octoprint-Filament-Reloaded/archive/{target_version}.zip"
            )
        )

__plugin_name__ = "Filament Sensor Reloaded"
__plugin_version__ = "1.0.1"

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = Julia3GFilament()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
}
