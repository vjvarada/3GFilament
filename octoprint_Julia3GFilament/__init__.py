# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.events import eventManager, Events
from flask import jsonify, make_response, request
import RPi.GPIO as GPIO
import time
import threading

# TODO:
'''
API to change settings, and pins
API to Caliberate
API to enable/Dissable sensor, and save this information
'''


class Julia3GFilament(octoprint.plugin.StartupPlugin,
                      octoprint.plugin.EventHandlerPlugin,
                      octoprint.plugin.SettingsPlugin,
					  octoprint.plugin.TemplatePlugin,
                      octoprint.plugin.BlueprintPlugin):
    def initialize(self):
        '''
        Checks RPI.GPIO version
        Initialises board
        :return: None
        '''
        self._logger.info("Running RPi.GPIO version '{0}'".format(GPIO.VERSION))
        if GPIO.VERSION < "0.6":  # Need at least 0.6 for edge detection
            raise Exception("RPi.GPIO must be greater than 0.6")
        GPIO.setmode(GPIO.BCM)  # Use the board numbering scheme
        GPIO.setwarnings(False)  # Disable GPIO warnings

    def on_after_startup(self):
        '''
        Runs after server startup.
        initialises filaemnt sensor objects, depending on the settings from the config.yaml file
        logs the number of filament sensors active
        :return: None
        '''
        self.filamentSensorEnabled = False
        self.sensorCount = int(self._settings.get(["sensorCount"]))
        if self.sensorCount != -1:  # If a pin is defined
            bounce = int(self._settings.get(["bounce"]))
            extrudePin = int(self._settings.get(["extrudePin"]))
            minExtrudeTime = int(self._settings.get(["minExtrudeTime"]))
            filamentRunoutTime = int(self._settings.get(["filamentRunoutTime"]))
            sensor0EncoderPin = int(self._settings.get(["sensor0EncoderPin"]))

            self.sensor0 = filamentSensor(sensorNumber=0, encoderPin=sensor0EncoderPin,
                                          filamentRunoutTime=filamentRunoutTime, bounce=bounce)
            self.motorExtrusion = motorExtrusion(extrudePin=extrudePin, minExtrudeTime=minExtrudeTime,
                                                 bounce=bounce)
            sensor1EncoderPin = int(self._settings.get(["sensor1EncoderPin"]))
            self.sensor1 = filamentSensor(sensorNumber=1,
                                          encoderPin=sensor1EncoderPin, filamentRunoutTime=filamentRunoutTime,
                                          bounce=bounce)
            self._logger.info("Number of Filament Sensors active : [%s]" % self.sensorCount)
        else:
            self._logger.info("No Filament sensors active")

        thread = threading.Thread(target=self.worker)
        thread.daemon = True
        thread.start()


    def get_settings_defaults(self):
        '''
        initialises default parameters
        :return:
        '''
        return dict(
            sensorCount=2,  # Default is no pin
            sensor0EncoderPin=5,
            sensor1EncoderPin=6,
            extrudePin=13,
            minExtrudeTime=5,
            filamentRunoutTime=15,
            bounce=50  # Debounce 250ms
        )

    def get_template_configs(self):
        return [dict(type="settings", custom_bindings=False)]

    @octoprint.plugin.BlueprintPlugin.route("/status", methods=["GET"])
    def check_pin_config(self):
        '''
        Checks and sends the pin configuration of the filament sensor(s)
        :return: response  dict of the pin configuration
        '''
        if self._printer.is_printing() or self._printer.is_paused():
            if self.sensorCount == 2:
                sensor0 = self.sensor0.getStatus()
                sensor1 = self.sensor1.getStatus()
                extruder = self.motorExtrusion.getStatus()
                return jsonify(sensor0=sensor0, sensor1=sensor1, motorExtrusion = extruder)
            else:
                return jsonify(sensor='No Sensors Connected')
        else:
            return jsonify(status='Printer is not priting')


    @octoprint.plugin.BlueprintPlugin.route("/message", methods=["GET"])
    def message_test(self):
        '''
        Checks and sends the pin configuration of the filament sensor(s)
        :return: response  dict of the pin configuration
        '''
        self.sendMessage('Filament_Sensor_Triggered', {'sensor': 'ActiveSensor'})
        return jsonify(status='Message Sent')

    @octoprint.plugin.BlueprintPlugin.route("/enable", methods=["POST"])
    def sensorEnable(self, *args, **kwargs):
        '''
        enables sensors based on sensorCount
        '''
        data = request.json
        if 'sensorCount' in data.keys():
            self.sensorCount = data['sensorCount']
        if self._printer.is_printing() or self._printer.is_paused():
            if self.sensorCount == -1:
                self.dissableFilamentSensing()
                return jsonify(STATUS='ALL SENSORS DISSABLED')
            elif self.sensorCount == 2:
                self.enableFilamentSensing()
                return jsonify(STATUS='ALL SENSORS ENABLED')
        return jsonify(STATUS=str(data['sensorCount']) + '  SENSORS ENABLED')

    def on_event(self, event, payload):
        '''
        Enables the filament sensor(s) if a print/resume command is triggered
        Dissables the filament sensor when pause ic called.
        :param event: event to respond to
        :param payload:
        :return:
        '''
        if event in (Events.PRINT_STARTED, Events.PRINT_RESUMED):  # If a new print is beginning
            self.dissableFilamentSensing()
            self.enableFilamentSensing()
        elif event in (
                Events.PRINT_DONE, Events.PRINT_FAILED, Events.PRINT_CANCELLED, Events.PRINT_PAUSED, Events.ERROR):
            self.dissableFilamentSensing()
            self._logger.info("Printing paused: Filament sensor Dissabled")

    def triggered(self):
        '''
        Callback function called when filament sensor is triggered while printing
        :param sensorNumber: the sensor number that triggered the function
        :return:
        '''
        # self._logger.info("Detected sensor [%s]" % sensorNumber)
        # print ("Detected sensor [%s]" % sensorNumber)
        if self._printer.is_printing():
            self.sendMessage('Filament_Sensor_Triggered', {'sensor': 'ActiveSensor'})
            self.dissableFilamentSensing()
            self._printer.toggle_pause_print()
            self._printer.jog(z=2, relative=True, speed=1000)
            self._printer.jog(x=0, y=0, relative=False, speed=600)
            self._logger.info("Printing paused: Filament sensor Dissabled")


    def sendMessage(self, plugin, data):
        self._plugin_manager.send_plugin_message(plugin, data)

    def dissableFilamentSensing(self):

        try:
            self.motorExtrusion.dissable()
            self.sensor0.dissable()
            self.filamentSensorEnabled = False
            self.sensor1.dissable()
        except Exception:
            pass

    def enableFilamentSensing(self):
        try:
            if self.sensorCount != -1:
                self.motorExtrusion.enable()
                self.sensor0.enable()
                self.filamentSensorEnabled = True
                self.sensor1.enable()
                self._logger.info("Filament sensor enabled")
            else:
                self._logger.info("No filament sensor to enable")
        except RuntimeError:
            self._logger.info("filament sensors could not be enabled")

    def get_update_information(self):
		return dict(
			octoprint_filament=dict(
				displayName="Filament Sensor Reloaded",
				displayVersion=self._plugin_version,

				# version check: github repository
				type="github_release",
				user="vjvarada",
				repo="3GFilament",
				current=self._plugin_version,

				# update method: pip
				pip="https://github.com/vjvarada/3GFilament/archive/{target_version}.zip"
			)
		)



	def worker(self):
		self._logger.info("Filament sensor thread started")
		while (True):
			try:
				if self.filamentSensorEnabled and self.sensorCount == 2:
					if (self.motorExtrusion.isExtruding() and not (
								self.sensor0.isRotating() or self.sensor1.isRotating())):
						self.triggered()
						self._logger.info("Filament sensor triggered")
			except:
				self._logger.info("Error in filament checkingThread")
			time.sleep(5)


class motorExtrusion(object):
    def __init__(self, extrudePin, minExtrudeTime, bounce):
        self.extrudePin = extrudePin
        self.bounce = bounce
        self.minExtrudeTime = minExtrudeTime
        try:
            GPIO.setup(self.extrudePin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        except:
            self._logger.info("Error while initialising Motor Pins")

    def enable(self):
        GPIO.add_event_detect(self.extrudePin, GPIO.RISING, callback=self.callback, bouncetime=self.bounce)
        self.callback(self.extrudePin)

    def callback(self, channel):
        self.latestPulse = time.time()

    def dissable(self):
        GPIO.remove_event_detect(self.extrudePin)

    def isExtruding(self):
        '''
        If the motor has been extruding for some time, as well as is currently HIGH, means the extruder is extruding
        :return:
        '''
        if (time.time() - self.latestPulse > self.minExtrudeTime) and bool(GPIO.input(self.extrudePin)):
            return True
        else:
            return False
    def getStatus(self):
        return {'isExtruding': self.isExtruding(),
                'extrudePinStatus': bool(GPIO.input(self.extrudePin)),
                'lastExtrude': time.time() - self.latestPulse}


class filamentSensor(object):
    def __init__(self, encoderPin, sensorNumber, filamentRunoutTime, bounce):
        self.sensorNumber = sensorNumber
        self.encoderPin = encoderPin
        self.bounce = bounce
        self.filamentRunoutTime = filamentRunoutTime
        try:
            GPIO.setup(self.encoderPin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        except:
            self._logger.info("Error while initialising Filament Pins")

    def enable(self):
        GPIO.add_event_detect(self.encoderPin, GPIO.RISING, callback=self.callback, bouncetime=self.bounce)
        self.latestPulse = time.time()

    def dissable(self):
        GPIO.remove_event_detect(self.encoderPin)

    def callback(self, channel):
        self.latestPulse = time.time()

    def isRotating(self):
        'If the encoder hasnt moved for some time, means the fiament sensor isnt rotating'
        if (time.time() - self.latestPulse > self.filamentRunoutTime):
            return False
        else:
            return True
    def getStatus(self):
        return {'lastEncoderStep': time.time() - self.latestPulse,
                'isRotating': self.isRotating()}



__plugin_name__ = "Julia3GFilament"
__plugin_version__ = "0.0.1"




def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = Julia3GFilament()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
}
