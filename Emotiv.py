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
# export DYLD_LIBRARY_PATH=
#      /usr/local/lib/EmotivSDKLib-PREMIUM:$DYLD_LIBRARY_PATH

import ctypes
import logging
from sys import platform
import os  # handy system and path functions
import EmoConstants
import csv  # should probably make a seperate IO... but for now...
import numpy as np


class EmoException(Exception):
    def __init__(self, constants, description, code, enum_type=None):
        '''get this party started'''
        self.description = description
        self._constants = constants
        self.code = code
        self.enum_type = enum_type

    def __str__(self):
        code_description = self._constants.describe(self.code, self.enum_type)
        return(self.description + ': code ' + hex(self.code) + ' (' +
               code_description + ')')


class Emotiv(object):
    """Emotiv - Class for dealing with the Emotiv headset """
    def __init__(self, use_composer=False,
                 profilePath=None, dataFileName=None):
        '''Find and open the SDK'''
        logging.basicConfig(level=logging.INFO)  # logging.INFO
        logging.info('initializing Emotiv')
        logging.info(os.getcwd())

        # ctypes cdll slightly different depending on platform
        # open these libraries
        if platform == "win32":
            self.edk = ctypes.CDLL('edk')
        elif platform == "darwin":
            # os.putenv('DYLD_LIBRARY_PATH', os.getcwd())
            # for i in os.environ:
            #     logging.info(i)

            # wouldn't have to do this if their stuff was properly built...
            # alas.
            ctypes.cdll.LoadLibrary(os.getcwd()+"/SDK/libiomp5.dylib")
            ctypes.cdll.LoadLibrary(os.getcwd()+"/SDK/libedk_ultils_mac.dylib")
            ctypes.cdll.LoadLibrary(os.getcwd()+"/SDK/libedk.dylib")
            self.edk = ctypes.CDLL(os.getcwd()+"/SDK/libedk.dylib")
        else:
            self.edk = ctypes.CDLL('libedk.so.1')

        # set up come constants that are useful further down the line
        self.edk.ES_CognitivGetCurrentActionPower.restype = ctypes.c_float
        self.constants = EmoConstants.EmoConstants()
        self.OK = self.constants['EDK_OK']

        # use the the socket version instead of the direct access.
        # I haven't tested this on the Mac but I can't see why it wouldn't
        # work properly
        if use_composer:
            if platform == "win32":
                status = self.edk.EE_EngineRemoteConnect(
                    ctypes.c_char_p(b'127.0.0.1'), ctypes.c_ushort(1726))
            else:
                status = self.edk.EE_EngineRemoteConnect(
                    ctypes.c_char_p(b'127.0.0.1'), ctypes.c_ushort(1726),
                    ctypes.c_char_p(b'Emotiv Systems-5'))
            if status != self.OK:
                raise EmoException(
                    self.constants,
                    'EE_EngineRemoteConnect was not successful', status)
                exit()

            logging.info('Connected to EmoComposer')
        else:
            status = self.edk.EE_EngineConnect(
                ctypes.c_char_p(b'Emotiv Systems-5'))
            if status != self.OK:
                raise EmoException(
                    self.constants,
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

        # if we use a file set it here
        self.filename = dataFileName
        if self.filename:
            self.writer = csv.writer(open(self.filename, "wb"))
        else:
            self.writer = None

    def __del__(self):
        self.edk.EE_EmoStateFree(self.state)
        self.edk.EE_EmoEngineEventFree(self.event)
        ### crashes the dang program
        #self.edk.EE_EngineDisconnect()

    def get_state(self):
        '''Read the emotiv state.
           A of a basic routine needed for everything.'''

        state = self.edk.EE_EngineGetNextEvent(self.event)

        if state == self.OK:
            event_type = self.edk.EE_EmoEngineEventGetType(self.event)
            logging.debug(
                'Got Event: ' +
                self.constants.describe(
                    event_type,
                    'EE_Event_enum'))

            if event_type == self.constants["EE_EmoStateUpdated"]:
                status = self.edk.EE_EmoEngineEventGetEmoState(
                    self.event, self.state)

                if status != self.OK:
                    raise EmoException(
                        self.constants,
                        'EE_EmoEngineEventGetEmoState was not successful',
                        status)

                self.newState = True
                return None  # OK?!

            elif event_type == self.constants['EE_UserAdded']:
                user = ctypes.c_uint(55)
                status = self.edk.EE_EmoEngineEventGetUserId(
                    self.event, ctypes.byref(user))
                if status != self.OK:
                    raise EmoException(
                        self.constants,
                        'EE_EmoEngineEventGetUserId was not successful',
                        status)

                self.userID = user
                self.ready = True

                if self.profilePath is not None:
                    status = self.edk.EE_LoadUserProfile(
                        self.userID,
                        ctypes.c_char_p(bytes(self.profilePath)))

                    if status != self.OK:
                        raise EmoException(
                            self.constants,
                            'EE_LoadUserProfile was not successful',
                            status)

                    logging.info(
                        'Successfully loaded profile for user ' +
                        str(self.userID))

                return None
            else:
                raise EmoException(
                    self.constants,
                    'Unrecognized state', event_type, 'EE_Event_enum')
                return None

        elif state == self.constants['EDK_NO_EVENT']:
            return None
        else:
            raise EmoException(
                self.constants,
                'EE_EngineGetNextEvent was not successful',
                state)

    def get_cog_action(self):
        if self.ready:
            return (
                self.edk.ES_CognitivGetCurrentAction(self.state),
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

        if self.edk.ES_ExpressivIsBlink(self.state) or \
           self.edk.ES_ExpressivIsLeftWink(self.state) or \
           self.edk.ES_ExpressivIsRightWink(self.state):
            return True
        else:
            return False

    def start_capture(self, buffer_size=1.0):
        if not self.ready:
            logging.critical('No User')
            return self.constants['EDK_INVALID_USER_ID']

        if self.capturing:
            logging.info('Already Logging')
            return

        logging.info('Raw capture start')
        self.edk.EE_DataSetBufferSizeInSec(ctypes.c_float(buffer_size))
        self.edk.EE_DataAcquisitionEnable(self.userID, ctypes.c_bool(True))
        self.capturing = True
        return None

    def stop_capture(self):
        if not self.ready or not self.capturing:
            logging.critical('Ugh')
            return

        logging.info('Raw capture stop')
        self.edk.EE_DataAcquisitionEnable(self.userID, ctypes.c_bool(False))
        self.edk.EE_DataUpdateHandle(0, self.rawData)
        self.capturing = False

        nSamplesTaken = ctypes.c_uint(0)
        self.edk.EE_DataGetNumberOfSample(
            self.rawData, ctypes.byref(nSamplesTaken))

        samplingRate = ctypes.c_uint(0)
        self.edk.EE_DataGetSamplingRate(
            self.userID, ctypes.byref(samplingRate))

        logging.info(
            "%d samples grabbed at %d/sec",
            nSamplesTaken.value, samplingRate.value)

        if nSamplesTaken.value > 0:
            # allocate enough doubles
            ddata = ctypes.c_double * nSamplesTaken.value

            # pointer to first thing
            dd = ddata(0)

            self.latest = np.empty((nSamplesTaken.value, 25))

            for trode in xrange(0, 25):  # should use the constants...
                self.edk.EE_DataGet(self.rawData, trode, dd, nSamplesTaken)
                for s in xrange(1, nSamplesTaken.value):
                    self.latest[s, trode] = dd[s]

        return None

    def get_data(self):
        '''simple getter for the latest data.'''
        return self.latest

    def set_marker(self, marker):
        status = self.edk.EE_DataSetMarker(self.userID, marker)
        return None

    def dump_capture(self):
        """output csv"""
        # print self.latest
        if self.writer:
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

    emotiv = Emotiv()

    # idle until the headset is ready
    while not emotiv.ready:
        emotiv.get_state()

    print("go!")

    # make a buffer that can hold our samples
    emotiv.start_capture(buffer_size=6.0)
    start = time.time()

    # for 5 seconds, gather data
    while time.time()-start <= 5.0:
        emotiv.get_state()
        if emotiv.get_blink_or_wink():
            print("blink at "+str(time.time()-start))

    emotiv.stop_capture()

    print("stop!")

    # emotiv.dump_capture()

    theData = emotiv.get_data()

    # data is in sample-major order
    # there are n samples x 25 channels of data.
    # ED_COUNTER = 0, ED_INTERPOLATED, ED_RAW_CQ,
    #     ED_AF3, ED_F7, ED_F3, ED_FC5, ED_T7,
    #     ED_P7, ED_O1, ED_O2, ED_P8, ED_T8,
    #     ED_FC6, ED_F4, ED_F8, ED_AF4, ED_GYROX,
    #     ED_GYROY, ED_TIMESTAMP, ED_ES_TIMESTAMP, ED_FUNC_ID,
    #     ED_FUNC_VALUE, ED_MARKER,
    #     ED_SYNC_SIGNAL
    #
    print theData.shape

    # print electrode O1
    o1 = theData[:, emotiv.constants['ED_O1']]
    o2 = theData[:, emotiv.constants['ED_O2']]

    print("mean value %f" % np.mean(o1))

    # print the values relative to the DC offset you see above
    print(o1 - np.mean(o1))
