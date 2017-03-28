# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.events import eventManager, Events
from flask import jsonify, make_response, request
import RPi.GPIO as GPIO

# TODO:
'''
API to change settings, and pins
API to Caliberate
API to enable/Dissable sensor, and save this information
'''

class Julia3GFilament(octoprint.plugin.StartupPlugin,
					  octoprint.plugin.EventHandlerPlugin,
					  octoprint.plugin.SettingsPlugin,
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
		self.sensorCount = int(self._settings.get(["sensorCount"]))
		if self.sensorCount != -1:  # If a pin is defined
			bounce = int(self._settings.get(["bounce"]))
			motorStepsRequired = int(self._settings.get(["motorStepsRequired"]))
			encoderStepsRequired = int(self._settings.get(["encoderStepsRequired"]))
			sensor0MotorStepPin = int(self._settings.get(["sensor0MotorStepPin"]))
			sensor0DirPin = int(self._settings.get(["sensor0MotorStepPin"]))
			sensor0EncoderPin = int(self._settings.get(["sensor0EncoderPin"]))
			sensor0MotorDir = bool(self._settings.get(["sensor0MotorDir"]))
			self.sensor0 = filamentSensor(sensorNumber = 0, motorStepPin=sensor0MotorStepPin, dirPin=sensor0DirPin,
										  encoderPin=sensor0EncoderPin, bounce=bounce,callback= self.triggered,
										  motorStepsRequired=motorStepsRequired,
										  encoderStepsRequired=encoderStepsRequired, motorDir = sensor0MotorDir)
			if self.sensorCount == 2:
				sensor1MotorStepPin = int(self._settings.get(["sensor1MotorStepPin"]))
				sensor1DirPin = int(self._settings.get(["sensor1MotorStepPin"]))
				sensor1EncoderPin = int(self._settings.get(["sensor1EncoderPin"]))
				sensor1MotorDir = bool(self._settings.get(["sensor1MotorDir"]))
				self.sensor1 = filamentSensor(sensorNumber = 1, motorStepPin=sensor1MotorStepPin, dirPin=sensor1DirPin,
											  encoderPin=sensor1EncoderPin, bounce=bounce,callback= self.triggered,
											  motorStepsRequired=motorStepsRequired,
											  encoderStepsRequired=encoderStepsRequired,motorDir = sensor1MotorDir)
			self._logger.info("Number of Filament Sensors active : [%s]" %self.sensorCount)
		else:
			self._logger.info("No Filament sensors active")

	def get_settings_defaults(self):
		'''
		initialises default parameters
		:return:
		'''
		return dict(
			sensorCount=2,  # Default is no pin
			sensor0MotorStepPin=13,
			sensor0DirPin=16,
			sensor0MotorDir = True,
			sensor0EncoderPin=5,
			sensor1MotorStepPin=19,
			sensor1DirPin=26,
			sensor1MotorDir = False,
			sensor1EncoderPin=6,
			motorStepsRequired=1000,
			encoderStepsRequired=500,
			bounce=300  # Debounce 250ms
		)

	# def get_template_configs(self):
	#     return [dict(type="settings", custom_bindings=False)]s

	@octoprint.plugin.BlueprintPlugin.route("/status/config", methods=["GET"])
	def check_pin_config(self):
		'''
		Checks and sends the pin configuration of the filament sensor(s)
		:return: response  dict of the pin configuration
		'''
		if self.sensorCount == 2:
			sensor0 = self.sensor0.getConfigs()
			sensor1 = self.sensor1.getConfigs()
			return jsonify(sensor0=sensor0, sensor1=sensor1)
		if self.sensorCount != -1:
			sensor0 = self.sensor0.getConfigs()
			return jsonify(sensor0=sensor0)
		else:
			return jsonify(sensor= 'No Sensors Connected')

	@octoprint.plugin.BlueprintPlugin.route("/status/steps", methods=["GET"])
	def check_status(self):
		'''
		cheks the number of steps incremented since enabled
		:return: response dict of the steps for each sensor
		'''
		if self.sensorCount == 2:
			sensor0 = self.sensor0.getSteps()
			sensor1 = self.sensor1.getSteps()
			return jsonify(sensor0=sensor0, sensor1=sensor1)
		if self.sensorCount != -1:
			sensor0 = self.sensor0.getSteps()
			return jsonify(sensor0=sensor0)
		else:
			return jsonify(sensor= 'No Sensors Connected')

	@octoprint.plugin.BlueprintPlugin.route("/status/test", methods=["POST"])
	def sensorTest(self, *args, **kwargs):
		'''
		Tests the filament sensor, for settings putposes
		if {"TEST": "START"} s POSTed, the filaemnt sensors will be enabled, and start counting,
		but will not trigger a pause command and would be the case when printing.
		any extrusion then on would be ounted, and can be checked with the /status/pin GET method.
		{"TEST": "STOP"} stops the testing
		'''
		data = request.json
		if data['TEST'] == 'START':
			try:
				if self.sensorCount != -1:
					self.sensor0.enableEventsTEST()
					self.sensor0.resetSteps()
					if self.sensorCount == 2:
						self.sensor1.resetSteps()
						self.sensor1.enableEventsTEST()
					self._logger.info("TESTING started: Filament sensor enabled")
					return jsonify(TEST='STARTED')
				else:
					self._logger.info("No filament sensors to test")
					return jsonify(TEST='NO FILAMENT SENSOR TO TEST')
			except RuntimeError:
				self._logger.info("TESTING not started: Filament sensor already enabled")
				return jsonify(TEST='ALREADY RUNNING')
		elif data['TEST'] == 'STOP':
			try:
				if self.sensorCount != -1:
					self.sensor0.dissableEvents()
					if self.sensorCount == 2:
						self.sensor1.dissableEvents()
				else:
					self._logger.info("No filament sensors to test")
					return jsonify(TEST='NO FILAMENT SENSOR TO TEST')
			except Exception:
				pass
			self._logger.info("TESTING stopped: Filament sensor disabled")
			return jsonify(TEST='STOPED')

	@octoprint.plugin.BlueprintPlugin.route("/status/enable", methods=["POST"])
	def sensorEnable(self, *args, **kwargs):
		'''
		enables sensors based on sensorCount
		'''
		data = request.json
		if 'sensorCount' in data.keys():
			self.sensorCount = data['sensorCount']
		if self._printer.is_printing() or self._printer.is_paused():
			if self.sensorCount == -1:
				try:
					self.sensor0.dissableEvents()
					self.sensor1.dissableEvents()
				except Exception:
					pass
				return jsonify(STATUS='ALL SENSORS DISSABLED')
			elif self.sensorCount == 1:
				try:
					self.sensor1.dissableEvents()
				except Exception:
					pass
				try:
					self.sensor0.enableEvents()
					self.sensor0.resetSteps()
				except Exception:
					pass
				return jsonify(STATUS='SENSOR 1 DISSABLED, SENSOR 0 ENABLED')
			elif self.sensorCount == 2:
				try:
					self.sensor0.enableEvents()
					self.sensor0.resetSteps()
				except Exception:
					pass
				try:
					self.sensor1.enableEvents()
					self.sensor1.resetSteps()
				except Exception:
					pass
				return jsonify(STATUS='ALL SENSORS ENABLED')
		return jsonify(STATUS= str(data['sensorCount']) + '  SENSORS ENABLED')

	@octoprint.plugin.BlueprintPlugin.route("/status/motorDir", methods=["POST"])
	def changeMotorDir(self, *args, **kwargs):
		'''
		changes motor direction (For testing purposes), only when the extruder is moving in positive direction
		should the motor steps increment
		'''
		data = request.json
		if 'sensor0' in data.keys():
			self.sensor0.motorDir = bool(data['sensor0'])
		if 'sensor1' in data.keys():
			self.sensor1.motorDir = bool(data['sensor1'])
		return jsonify(STATUS = 'Settings Changed')



	def on_event(self, event, payload):
		'''
		Enables the filament sensor(s) if a print/resume command is triggered
		Dissables the filament sensor when pause ic called.
		:param event: event to respond to
		:param payload:
		:return:
		'''
		if event in (Events.PRINT_STARTED,Events.PRINT_RESUMED):  # If a new print is beginning
			try:
				if self.sensorCount != -1:
					self.sensor0.dissableEvents()
					if self.sensorCount == 2:
						self.sensor1.dissableEvents()
			except Exception:
				pass
			try:
				if self.sensorCount != -1:
					self.sensor0.enableEvents()
					self.sensor0.resetSteps()
					if self.sensorCount == 2:
						self.sensor1.resetSteps()
						self.sensor1.enableEvents()
					self._logger.info("Printing started: Filament sensor enabled")
				else:
					self._logger.info("No filament sensor to enable")
			except RuntimeError:
				self._logger.info("filament sensors could not be enabled")
		elif event in (Events.PRINT_DONE, Events.PRINT_FAILED, Events.PRINT_CANCELLED,Events.PRINT_PAUSED,Events.ERROR):
			try:
				if self.sensorCount != -1:
					self.sensor0.dissableEvents()
					if self.sensorCount == 2:
						self.sensor1.dissableEvents()
					self._logger.info("Printing stopped: Filament sensor disabled")
				else:
					self._logger.info("No filament sensor to dissable")
			except Exception:
				pass


	def triggered(self, sensorNumber):
		'''
		Callback function called when filament sensor is triggered while printing
		:param sensorNumber: the sensor number that triggered the function
		:return:
		'''
		self._logger.info("Detected sensor [%s]" %sensorNumber)
		print ("Detected sensor [%s]" %sensorNumber)
		if self._printer.is_printing():
			self._printer.toggle_pause_print()
			self._printer.jog(z=2, relative=True, speed=1000)
			self._printer.jog(x=0,y=0,relative=False,speed=600)
			self._plugin_manager.send_plugin_message('Filament_Sensor_Triggered', {'sensor': sensorNumber})
			self._logger.info("Printing paused: Filament sensor Dissabled")
			# if self.sensorCount != -1:
			# 	self.sensor0.dissableEvents()
			# 	if self.sensorCount == 2:
			# 		self.sensor0.dissableEvents()


class filamentSensor(object):
	def __init__(self, sensorNumber, motorStepPin, dirPin, encoderPin, motorStepsRequired, encoderStepsRequired,
				 callback,motorDir, bounce=300):
		self.sensorNumber = sensorNumber
		self.motorStepPin = motorStepPin
		self.dirPin = dirPin
		self.motorDir = motorDir
		self.encoderPin = encoderPin
		self.bounce = bounce
		self.callback = callback
		self.motorStepsRequired = motorStepsRequired
		self.encoderStepsRequired = encoderStepsRequired
		GPIO.setup(self.motorStepPin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)  # Initialize GPIO as INPUT
		GPIO.setup(self.dirPin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
		GPIO.setup(self.encoderPin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
		self.encoderSteps = 0
		self.motorSteps = 0

	def enableEvents(self):
		GPIO.add_event_detect(self.motorStepPin, GPIO.RISING, callback=self.incMotorStep, bouncetime=self.bounce)
		GPIO.add_event_detect(self.encoderPin, GPIO.RISING, callback=self.incEncoder, bouncetime=self.bounce)

	def enableEventsTEST(self):
		GPIO.add_event_detect(self.motorStepPin, GPIO.RISING, callback=self.incMotorStepTEST, bouncetime=self.bounce)
		GPIO.add_event_detect(self.encoderPin, GPIO.RISING, callback=self.incEncoderTEST, bouncetime=self.bounce)

	def dissableEvents(self):
		GPIO.remove_event_detect(self.motorStepPin)
		GPIO.remove_event_detect(self.encoderPin)

	def incMotorStep(self,channel):
		if GPIO.input(self.dirPin) == self.motorDir:
			self.motorSteps += 1
		if self.motorSteps >= self.motorStepsRequired:
			if self.encoderSteps < self.encoderStepsRequired:
				self.callback(self.sensorNumber)

	def incEncoder(self,channel):
		self.encoderSteps += 1

	def incMotorStepTEST(self,channel):
		if GPIO.input(self.dirPin) == self.motorDir:
			self.motorSteps += 1

	def incEncoderTEST(self,channel):
		self.encoderSteps += 1

	def resetSteps(self):
		self.encoderSteps = 0
		self.motorSteps = 0

	def getConfigs(self):
		return {'sensorNumber' : self.sensorNumber, 'motorStepPin' : self.motorStepPin, 'dirPin' : self.dirPin,
				'encoderPin' : self.encoderPin,'motorDir' : self.motorDir}
	def getSteps(self):
		return {'motorSteps' : self.motorSteps, 'encoderSteps' : self.encoderSteps}


__plugin_name__ = "Julia3GFilament"
__plugin_version__ = "0.0.1"
__plugin_description__ = "Julia 3G FIlament Sensor Plugin for Octoprint"
__plugin_implementation__ = Julia3GFilament()
