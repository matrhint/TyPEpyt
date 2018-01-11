#!/usr/bin/env python
# License: Public Domain 

# Code to create a typing robot using a keyboard mapping
# This uses the Adafruit I2C and Servo libraries for controlling the PCA9685. 
# It also uses the Adafruit I2C and Adafruit_ADS1x15 libraries for reading current.
# Note that current is read in all servos, no single servo is monitored individually in this code.

# To use this code, start python and run these commands
# > execfile('ty.py')
# > ty.pressKey("h")
# > ty.pressString("hello")

import MeArm_Cal_Jetson_Configuration as cal
import math
import meArm
import TyAdc
import random
import time
import keyboardCalibration as KeyCal
import TyKey as key
import cv2
import numpy as np


class TyContoller():

    def __init__(self, cam):
        self.adc = TyAdc.TyAdc()
        self.arm = meArm.meArm(
	        cal.BASE_MIN_PWM,     cal.BASE_MAX_PWM,      cal.BASE_MIN_ANGLE_RAD,     cal.BASE_MAX_ANGLE_RAD,
	        cal.SHOULDER_MIN_PWM, cal.SHOULDER_MAX_PWM,  cal.SHOULDER_MIN_ANGLE_RAD, cal.SHOULDER_MAX_ANGLE_RAD,
	        cal.ELBOW_MIN_PWM,    cal.ELBOW_MAX_PWM,     cal.ELBOW_MIN_ANGLE_RAD,    cal.ELBOW_MAX_ANGLE_RAD,
	        cal.CLAW_MIN_PWM,     cal.CLAW_MAX_PWM,      cal.CLAW_MIN_ANGLE_RAD,     cal.CLAW_MAX_ANGLE_RAD)
        self.arm.begin(pwmFrequency = cal.PWM_FREQUENCY) 
        time.sleep(0.5)
        self.open(92)
        self.cam = cam
        self.keymap = key.KeyMap(cam)

    def __del__(self):
        self.adc.stop()
        del self.arm

    def start(self):
        self.checkBaselineCurrrent()
        self.adc.stop() # adc fights with display
        self.gotoServoPos(KeyCal.KEYBOARD_NEUTRAL)
        self.open(92)
        frame, self.keyboardOutline = self.keymap.kvm(debugDraw = True)
#        self.adc.start()

    def open(self, percent=75):
        self.arm.gripperClosePercent(percent)

    def checkBaselineCurrrent(self):
        self.currentCheckTime = time.time()
        self.baselineCurrent = self.adc.magnitude()

    def isMotionComplete(self):
        okMultiplier = 3 # can go over 10% and still considered done
        adc = self.adc.magnitude();
        if (adc < self.baselineCurrent):
            self.baselineCurrent = adc; # use the lowest
        print "%s: base %s mag %s" % (time.time(), self.baselineCurrent, adc)
        if (adc < self.baselineCurrent * okMultiplier):
            return True
        if (adc < 150):
            return True
        return False

    def waitUntilDone(self, minTime = 0.1, timeout=0.5):
        time.sleep(minTime)
        timeStarted = time.time()
        dt = time.time() - timeStarted
        while (not self.isMotionComplete() and dt < timeout): 
            dt = time.time() - timeStarted
            time.sleep(0.05)
        if self.isMotionComplete():
            self.checkBaselineCurrrent()
            print "done, motion finished"
        else:
            print "done, timed out"

    def waitForPushback(self, timeout):
        pushbackCurrent = 25
        timeStarted = time.time()
        dt = time.time() - timeStarted 
        adc = self.adc.magnitude()
        print "%s: pushback %s mag %s (%s)" % (time.time(), self.baselineCurrent, adc, (adc - self.baselineCurrent))  
        while ((abs(adc - self.baselineCurrent) < pushbackCurrent) and dt < timeout):
            adc = self.adc.magnitude()
            dt = time.time() - timeStarted
            time.sleep(0.05)
            print "%s: pushback %s mag %s (%s)" % (time.time(), self.baselineCurrent, adc, (adc - self.baselineCurrent))  
        if abs(adc - self.baselineCurrent) >= pushbackCurrent:
            print "done, pushed"
            return True
        else:
            print "done, timed out"
            return False

    def pressString(self, string):
        for c in string:
            self.pressKey(c)
            time.sleep(0.2)

    # 1. Translate goal keypos from perfect to real-world units.
    # 1. Translate goal keypos into servo units ?
    # 1. Get current position in servo units. Translate into real-world units
    # 1. Set servo to go in small steps
    # 1. Take picture, check servo position. Adjust goal.

    # 2. Press key until current feedback says done
    # 3. Raise key
    # 4. Return key to neutral 
    def pressKey(self, char, delayDiv=300.0):
        debugPrint = 1
        goalPos = list(KeyCal.KEYPIX[char]) #make a copy of the location because we'll edit Z

        ret, frame = self.cam.read()
        curPos = self.keymap.locateClaw(frame, self.keyboardOutline)

        print "Goal pos ", goalPos, " cur pos ", curPos
        return 

        self.checkBaselineCurrrent() 

        [keyX, keyY, keyZ] = keypos

#        [origX, origY, origZ] = self.arm.getPos()       # ideally this is the neutral position

        # 1. Goto to the XY location
        dist = self.arm.getDistance(keyX, keyY, origZ)
        self.arm.gotoPoint(x=keyX, y=keyY, z=origZ, debugPrint=debugPrint)		
        print "goto XY %s %s (%s, %s)" % (keypos, self.arm.getPos(), self.arm.isReachable(x=keyX, y=keyY, z=origZ), dist)
        self.waitUntilDone(minTime = dist/delayDiv, timeout = dist/delayDiv)

        # 2. Press key until feedback indicates it is done
        print "key"
        self.checkBaselineCurrrent() 
        self.arm.goDirectlyTo(x=keyX, y=keyY, z=keyZ, debugPrint=debugPrint)		
        done = self.waitForPushback(0.25)

        # 3. Raise key
        print "raise key"
        self.arm.gotoPoint(x=keyX, y=keyY, z=origZ-10, debugPrint=debugPrint)		

        # 4. Return key to neutral
        print "back to neutral"
        self.gotoNice(KeyCal.KEYBOARD_NEUTRAL)


    def gotoServoPos(self, pos):
        [x, y, z] = pos
        self.arm.gotoPoint(x=x, y=y, z=z, debugPrint=1)		
        print(self.arm.getPos())

    def findCamPos(self, c):
        pos = ty.keymap.transformKeyboardToCameraPos(c)
        pos = pos.flatten()
        [goalCamX, goalCamY] = pos
        goalServoZ = KeyCal.KEYBOARD_NEUTRAL[2]
        [curServoX, curServoY, curServoZ] = self.arm.getPos()
        [curCamX, curCamY] = self.keymap.locateClaw()
        goalServo = cv2.perspectiveTransform(np.array([[pos]], dtype='float32'),self.camToServoM)
        goalServo = goalServo.flatten()
        print "Goal Cam ", [goalCamX, goalCamY] 
        print "Goal Servo ", [goalServo] 
        print "Cur Cam ", [curCamX, curCamY]
        print "Cur servo ", [curServoX, curServoY, curServoZ]


        self.arm.gotoPoint(x=goalServo[0], y=goalServo[1], z=goalServoZ, debugPrint=1)		
        print(self.arm.getPos())

#    def calibrateCamServo(self):
    def cal(self):
        servoPos = [[-110, 140],    # q
                    [ 120, 155],    # DEL
                    [- 95, 100],    # z
                    [- 40, 105]]    # space
        neutralZ = 50
        camPos = []
        clawPos = []
        self.adc.stop() # adc fights with display
        for p in servoPos:            
            self.gotoServoPos([p[0], p[1], neutralZ]) 
            self.keymap.waitForClick()
            camPos.append([self.keymap.click_x, self.keymap.click_y])
            clawPos.append(self.keymap.locateClaw())
        self.camToServoM = cv2.getPerspectiveTransform(np.array(camPos, dtype="float32"),
                                                        np.array(servoPos, dtype="float32"), )
#        self.adc.start()
        self.gotoServoPos(KeyCal.KEYBOARD_NEUTRAL)
        print camPos
        print clawPos
        return self.camToServoM


    def gotoNice(self, pos):
        [keyX, keyY, keyZ] = pos
        [curX, curY, curZ] = self.arm.getPos()
        if (curZ < keyZ): # go up and then down into position
            dist = self.arm.getDistance(keyX, keyY, z=keyZ+10)
            self.arm.gotoPoint(x=keyX, y=keyY, z=keyZ+10, debugPrint=0)

        self.arm.gotoPoint(x=keyX, y=keyY, z=keyZ, step=10, debugPrint=0)
        self.waitUntilDone(0.25)
        print(self.arm.getPos())		
   

if __name__ == '__main__':
    try: cam
    except NameError: 
        videoChannel = 1
        cam = cv2.VideoCapture(videoChannel)
    ty = TyContoller(cam)




