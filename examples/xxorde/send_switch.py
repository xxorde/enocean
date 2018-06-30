#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
import argparse
from enocean.consolelogger import init_logging
import enocean.utils
from enocean.communicators.ESP2serialcommunicator import ESP2SerialCommunicator
from enocean.protocol.constants import PACKET, RORG
from enocean.manufacturer.eltako import *
import sys
import traceback
from time import sleep
import threading, logging

def print_packet_type(packet_type):
    types = {
      PACKET.RESERVED: 'RESERVED',
      PACKET.RADIO: 'RADIO',
      PACKET.RESPONSE: 'RESPONSE',
      PACKET.RADIO_SUB_TEL: 'RADIO_SUB_TEL',
      PACKET.EVENT: 'EVENT',
      PACKET.COMMON_COMMAND: 'COMMON_COMMAND',
      PACKET.SMART_ACK_COMMAND: 'SMART_ACK_COMMAND',
      PACKET.REMOTE_MAN_COMMAND: 'REMOTE_MAN_COMMAND',
      PACKET.RADIO_MESSAGE: 'RADIO_MESSAGE',
      PACKET.RADIO_ADVANCED: 'RADIO_ADVANCED'}
    return types[packet_type]

def str_to_hex(hex_str):
  return int(hex_str, 16)


init_logging()
mainlogger = logging.getLogger('eno_backend')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
mainlogger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
stream_handler.setFormatter(formatter)
mainlogger.addHandler(stream_handler)

# parse arguments
parser = argparse.ArgumentParser(description='Send switch event')
parser.add_argument('swhigh', metavar='SH', type=str,
                   help='High part of the switch address')
parser.add_argument('swlow', metavar='SL', type=str,
                   help='Low part of the switch address')
args = parser.parse_args()

esp2com = ESP2SerialCommunicator(port='/dev/ttyUSB0')
esp2com.start()

msg = RadioPacket.create_ESP2(rorg=0x00, rorg_func=0x00, rorg_type=0x00,
                        sender = [0x00, 0x00, 0x10, 0x01],
                        destination = [0x00, 0x00, 0x00, 0x01],
                        command=[RockerButton.RightTop, 0x00, 0x00, 0x00],
                        status = MSGSTATUS.T2NMsg,
                        packet_type = 0x00
                        )
msg.packet_type = PACKET.RESERVED
msg.rorg = RORG.UNDEFINED
switchHigh = str_to_hex(args.swhigh)
switchLow = str_to_hex(args.swlow)
switchHigh = 0x10
switchLow = 0x05
msg.data = [0xf6, 0x70, 0x0, 0x0, 0x0, 0x0, 0x0, switchHigh, switchLow, 0x30]

mainlogger.debug("packet type:%s, rorg:%s, packet:%s", print_packet_type(msg.packet_type), msg.rorg, msg)
esp2com.send(msg)
sleep(0.5)

if esp2com.is_alive():
    esp2com.stop()