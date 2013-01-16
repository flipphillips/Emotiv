#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Emotiv - Emotive support in Python
#
# Originally by John DiMatteo <jdimatteo@gmail.com>
# 
#   4July12 flip    woot
#   15Aug12 flip    merged in changes from blink experiment
#   winter 12 flip  added more coverage for MIT stuff
#

# needs to run in 32 bit
# export VERSIONER_PYTHON_PREFER_32_BIT=yes
# export DYLD_LIBRARY_PATH=/usr/local/lib/EmotivSDKLib-PREMIUM:$DYLD_LIBRARY_PATH

import ctypes
import logging
from sys import platform
import os #handy system and path functions
import EmoConstants
import csv ## should probably make a seperate IO... but for now...
import numpy as np

class EmoException(Exception):
    def __init__(self, constants, description, code, enum_type = None):
        self.description = description 
        self._constants = constants 
        self.code = code
        self.enum_type = enum_type
    def __str__(self):
        code_description = self._constants.describe(self.code, self.enum_type)
        return(self.description + ': code ' + hex(self.code) + ' (' 
            + code_description + ')')

class Emotiv(object):
    """Emotiv - Class for dealing with the Emotiv headset """
    def __init__(self, use_emo_composer_instead_of_headset, 
                 profilePath = None, dataFileName = None):
        logging.basicConfig(level=logging.INFO) #logging.INFO
        logging.info('initializing Emotiv')
        logging.info(os.getcwd())
        
        if platform == "win32":
            self.edk = ctypes.CDLL('edk')
        elif platform == "darwin":
            os.putenv('DYLD_LIBRARY_PATH',os.getcwd())
            for i in os.environ:
                logging.info(i)
                
            # wouldn't have to do this if their stuff was properly built... alas.
            ctypes.cdll.LoadLibrary(os.getcwd()+"/libiomp5.dylib")
            ctypes.cdll.LoadLibrary(os.getcwd()+"/libedk_ultils_mac.dylib")
            ctypes.cdll.LoadLibrary(os.getcwd()+"/libedk.dylib")
            self.edk = ctypes.CDLL(os.getcwd()+"/libedk.dylib")
        else:
            self.edk = ctypes.CDLL('libedk.so.1')

        self.edk.ES_CognitivGetCurrentActionPower.restype = ctypes.c_float

        self.constants = EmoConstants.EmoConstants() 
        self.OK = self.constants['EDK_OK']

        if use_emo_composer_instead_of_headset: 
            if platform == "win32": 
                status = self.edk.EE_EngineRemoteConnect(
                    ctypes.c_char_p(b'127.0.0.1'), ctypes.c_ushort(1726))
            else:
                status = self.edk.EE_EngineRemoteConnect(
                    ctypes.c_char_p(b'127.0.0.1'), ctypes.c_ushort(1726),
                    ctypes.c_char_p(b'Emotiv Systems-5'))
            if status != self.OK:
                raise EmoException(self.constants, 
                    'EE_EngineRemoteConnect was not successful', status)
                exit()

            logging.info('Connected to EmoComposer')
        else:
            status = self.edk.EE_EngineConnect(
                ctypes.c_char_p(b'Emotiv Systems-5')) 
            if status != self.OK:
                raise EmoException(self.constants, 
                    'EE_EngineConnect was not successful', status)
                exit()

            logging.info('Connected to Emotiv headset')

        # for profile-based ops
        self.profilePath = profilePath

        # Emo Engine
        # these C structures with allocated memory may be reused
        self.event = self.edk.EE_EmoEngineEventCreate()
        self.state = self.edk.EE_EmoStateCreate()
        self.profile = self.edk.EE_ProfileEventCreate()
        self.userID = ctypes.c_uint(0)
        self.newState = False

        # Raw data
        self.rawData = self.edk.EE_DataCreate()
        self.ready = False
        self.capturing = False
        self.latest = np.array('d')

        self.filename = dataFileName
        if self.filename:
            self.writer = csv.writer(open(self.filename, "wb"))

    def __del__(self):
        self.edk.EE_EmoStateFree(self.state)
        self.edk.EE_EmoEngineEventFree(self.event)
        ### crashes the dang program       self.edk.EE_EngineDisconnect()

    
    # -- maybe make a generic get_state func, and then a get_cog_state and get_user that call it
    def get_state(self):
        state = self.edk.EE_EngineGetNextEvent(self.event)

        if state == self.OK:
            event_type = self.edk.EE_EmoEngineEventGetType(self.event) 
            logging.debug('Got Event: ' + self.constants.describe(event_type, 'EE_Event_enum'))
            
            if event_type == self.constants["EE_EmoStateUpdated"]:
                status = self.edk.EE_EmoEngineEventGetEmoState(self.event, self.state)

                if status != self.OK:
                    raise EmoException(self.constants, 'EE_EmoEngineEventGetEmoState was not successful', status)

                self.newState = True
                return None # OK?!
                
            elif event_type == self.constants['EE_UserAdded']:
                user = ctypes.c_uint(55)
                status = self.edk.EE_EmoEngineEventGetUserId(self.event, ctypes.byref(user))
                if status != self.OK:
                    raise EmoException(self.constants, 'EE_EmoEngineEventGetUserId was not successful', status)
                self.userID = user
                self.ready = True

                if self.profilePath is not None:
                    status = self.edk.EE_LoadUserProfile(self.userID, ctypes.c_char_p(bytes(self.profilePath)))

                    if status != self.OK:
                        raise EmoException(self.constants, 'EE_LoadUserProfile was not successful', status)
               
                    logging.info('Successfully loaded profile for user ' + str(self.userID))

                return None
            else:
                raise EmoException(self.constants, 'Unrecognized state', event_type, 'EE_Event_enum')
                return None

        elif state == self.constants['EDK_NO_EVENT']:
            return None
        else:
            raise EmoException(self.constants, 'EE_EngineGetNextEvent was not successful', state)

    def get_cog_action(self):
        if self.ready:
            return (self.edk.ES_CognitivGetCurrentAction(self.state), 
                self.edk.ES_CognitivGetCurrentActionPower(self.state))
        else:
            logging.critical('No User')
            return self.constants['EDK_INVALID_USER_ID']
        return None

    def get_exp_action(self):
        return None

    def get_blink_or_wink(self):
        ## hmm... need to think about this
        if not self.newState:
            return False
        else:
            self.newState = False

        if self.edk.ES_ExpressivIsBlink(self.state) or self.edk.ES_ExpressivIsLeftWink(self.state) or self.edk.ES_ExpressivIsRightWink(self.state):
            return True
        else:
            return False

    def start_capture(self, buffer_size = 1.0):
        if not self.ready:
            logging.critical('No User')
            return self.constants['EDK_INVALID_USER_ID']

        if self.capturing:
            logging.info('Already Logging')
            return 

        logging.info('Raw capture start')
        self.edk.EE_DataSetBufferSizeInSec(ctypes.c_float(buffer_size))
        self.edk.EE_DataAcquisitionEnable(self.userID,ctypes.c_bool(True))
        self.capturing = True
        return None
        
    def stop_capture(self):
        if not self.ready or not self.capturing:
            logging.critical('Ugh')
            return

        logging.info('Raw capture stop')
        self.edk.EE_DataAcquisitionEnable(self.userID,ctypes.c_bool(False))
        self.edk.EE_DataUpdateHandle(0, self.rawData)
        self.capturing = False;

        nSamplesTaken = ctypes.c_uint(0)
        self.edk.EE_DataGetNumberOfSample(self.rawData,ctypes.byref(nSamplesTaken))
        
        samplingRate = ctypes.c_uint(0)
        self.edk.EE_DataGetSamplingRate(self.userID, ctypes.byref(samplingRate))
        logging.info("%d samples grabbed at %d/sec", nSamplesTaken.value,samplingRate.value)



        if nSamplesTaken.value > 0:
            # allocate enough doubles
            ddata = ctypes.c_double * nSamplesTaken.value

            # pointer to first thing
            dd = ddata(0)

            self.latest = np.empty( (nSamplesTaken.value, 25) )

            for trode in xrange(0,25): #should use the constants...
                self.edk.EE_DataGet(self.rawData, trode, dd, nSamplesTaken)
                for s in xrange(1,nSamplesTaken.value):
                    self.latest[s,trode] = dd[s]

        return None

    def set_marker(self, marker):
        status = self.edk.EE_DataSetMarker(self.userID, marker)
        return None

    def dump_capture(self):
        """output csv"""
        # print self.latest
        self.writer.writerows(self.latest)
        return None

    def get_push_power(self):
        state = self.get_state()
        if (state is None):
            return None

        (action, power) = state 
        if action == self.constants['COG_PUSH']:
            return power
        else:
            return None

if __name__ == '__main__':
    import time

    emotiv = Emotiv(False, None, "flip.csv") ###'./flip.emu')

    while not emotiv.ready:
        emotiv.get_state()

    print("go!")

    emotiv.start_capture(buffer_size=600.0)
    start = time.time()
    while time.time()-start <= 5.0:
        emotiv.set_marker(1)
        time.sleep(.1)
        emotiv.get_state() ##blinks get queued up?


    emotiv.stop_capture()

    print("stop stop quit it!")

    emotiv.dump_capture()

    # get rid of queued up blinks?
    emotiv.start_capture(buffer_size=8.0)
    start = time.time()
    while time.time()-start <= 5.0:
        emotiv.get_state()
        if emotiv.get_blink_or_wink():
            print("blink at "+str(time.time()-start))

    emotiv.stop_capture()

    print("stop stop quit it!")

    emotiv.dump_capture()

#    import time
# 
#     emotiv = Emotiv(False, None, "flip.csv") ###'./flip.emu')
# 
#     while not emotiv.ready:
#         emotiv.get_state()
# 
#     print("go!")
# 
#     emotiv.start_capture(buffer_size=600.0)
#     start = time.time()
#     while time.time()-start <= 5.0:
#         emotiv.set_marker(1)
#         time.sleep(.5)
# 
#     emotiv.stop_capture()
# 
#     print("stop stop quit it!")
# 
#     emotiv.dump_capture()
# 
#     emotiv.start_capture(buffer_size=8.0)
#     start = time.time()
#     while time.time()-start <= 5.0:
#         emotiv.set_marker(1)
#         time.sleep(.5)
# 
#     emotiv.stop_capture()
# 
#     print("stop stop quit it!")
# 
#     emotiv.dump_capture()
# 
