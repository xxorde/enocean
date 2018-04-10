# -*- encoding: utf-8 -*-
from __future__ import print_function, unicode_literals, division, absolute_import
import logging
import serial
import time

from enocean.communicators.ESP2communicator import ESP2Communicator


class ESP2SerialCommunicator(ESP2Communicator):
    ''' Serial port communicator class for EnOcean radio '''
    logger = logging.getLogger('enocean.communicators.ESP2SerialCommunicator')

    def __init__(self, port='/dev/ttyS0', callback=None):
        super(ESP2SerialCommunicator, self).__init__(callback)
        # Initialize serial port
        self.__ser = serial.Serial(port, 57600, timeout=0.1)

    def run(self):
        self.logger.info('SerialCommunicator started')
        while not self._stop_flag.is_set():
            # If there's messages in transmit queue
            # send them
            while True:
                packet = self._get_from_send_queue()
                if not packet:
                    break
                try:
                    self.__ser.write(bytearray(packet.build_ESP2()))
                except serial.SerialException:
                    self.stop()

            # Read chars from serial port as hex numbers
            try:
                self._buffer.extend(bytearray(self.__ser.read(16)))
            except serial.SerialException:
                self.logger.error('Serial port exception! (device disconnected or multiple access on port?)')
                self.stop()
            self.parse()
            time.sleep(0)

        self.__ser.close()
        self.logger.info('SerialCommunicator stopped')
