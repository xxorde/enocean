#!/usr/bin/env python
# -*- encoding: utf-8 -*-
from enocean.consolelogger import init_logging
import enocean.utils
from enocean.communicators.ESP2serialcommunicator import ESP2SerialCommunicator
from enocean.protocol.constants import PACKET, RORG
from enocean.manufacturer.eltako import *
import sys
import traceback
from time import sleep
import paho.mqtt.client as paho
from devicelist_example import *
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

try:
    import queue
except ImportError:
    import Queue as queue

class BreakIt(Exception): pass

def eno_worker(wstop):
    # endless loop receiving radio packets
    mainlogger.info("Worker started...")
    while 1:
        try:
            if wstop.isSet():
                mainlogger.debug("wstop.isSet()")
                break

            # Loop to empty the queue...
            packet = esp2com.receive.get(block=True, timeout=0.1)
            #mainlogger.debug("packet type:%s, rorg:%s, packet:%s", print_packet_type(packet.packet_type), packet.rorg, packet)

            # toggle all switches
            # type:RESERVED, rorg:RORG.UNDEFINED, packet:0x00 ['0xf6', '0x70', '0x0', '0x0', '0x0', '0x0', '0x0', '0x10', '0x1', '0x30'] [] OrderedDict()
            for item in switches:
                msg = RadioPacket.create_ESP2(rorg=0x00, rorg_func=0x00, rorg_type=0x00,
                                        sender = [0x00, 0x00, 0x10, 0x01],
                                        destination = [0x00, 0x00, 0x00, 0x01],
                                        command=[RockerButton.RightTop, 0x00, 0x00, 0x00],
                                        status = MSGSTATUS.T2NMsg,
                                        packet_type = 0x00
                                        )
                msg.packet_type = PACKET.RESERVED
                msg.rorg = RORG.UNDEFINED
                #msg.sender = []
                #msg.destination = []
                #msg.destination = [0x00, 0x00, 0x00, 0x01]
                msg.data = [0xf6, 0x70, 0x0, 0x0, 0x0, 0x0, 0x0, 0x10, 0x1, 0x30]

                mainlogger.debug("packet type:%s, rorg:%s, packet:%s", print_packet_type(msg.packet_type), msg.rorg, msg)
                esp2com.send(msg)
                sleep(1.2)


            # parse FTS14EM events
            if(packet.packet_type in[PACKET.RESERVED]) and(packet.rorg in[RORG.UNDEFINED]):
                id = packet.data[5], packet.data[6], packet.data[7], packet.data[8]
                if packet.data[1] in [0x70, 0x50, 0x30, 0x10] :
                    mainlogger.debug("Eltako FTS14EM rocker switch, %s, PRESS %s", [hex(o) for o in id], hex(packet.data[1]))
                elif packet.data[1] == 0x00 :
                    mainlogger.debug("Eltako FTS14EM rocker switch, %s, RELEASED", [hex(o) for o in id])

            elif (packet.packet_type in [PACKET.RADIO, PACKET.EVENT]) and (packet.rorg in [RORG.RPS, RORG.BS4, RORG.BS1]):

                button = rockers.new_event(packet)
                if button is not None:
                    mainlogger.debug("button is not None")
                    if button[1] is RockerEvent.Press:
                        cmqtt.publish("my/home/automation/topic/button/press", payload=button[0], qos=2, retain=False)
                        mainlogger.debug("RockerEvent.Press")
                    if button[1] is RockerEvent.Longpress_2s:
                        cmqtt.publish("my/home/automation/topic/button/longpress2", payload=button[0], qos=2, retain=False)
                        mainlogger.debug("RockerEvent.Longpress_2s")
                    if button[1] is RockerEvent.Longpress_5s:
                        cmqtt.publish("my/home/automation/topic/button/longpress5", payload=button[0], qos=2, retain=False)
                        mainlogger.debug("RockerEvent.Longpress_5s")

                for item in hygrometer:
                    if packet.sender_hex == item.ID:
                        EnoValList = item.decode_humidity(packet)
                        cmqtt.publish(item.Name, payload=EnoValList, qos=2, retain=True)
                        raise BreakIt

                for item in roomsensors:
                    if packet.sender_hex == item.ID:
                        EnoValList = item.decode(packet)
                        cmqtt.publish(item.Name + "/temperature", payload=EnoValList[0], qos=2, retain=True)
                        cmqtt.publish(item.Name + "/setpoint", payload=EnoValList[1], qos=2, retain=True)
                        cmqtt.publish(item.Name + "/state", payload=EnoValList[2], qos=2, retain=True)
                        raise BreakIt

                if packet.sender_hex == weatherstation.ID:
                    item = weatherstation
                    EnoValList = item.decode(packet)
                    if EnoValList[0] == 0:
                        cmqtt.publish(item.Name + "/lightsensor", payload=EnoValList[1], qos=2, retain=True)
                        cmqtt.publish(item.Name + "/temperature", payload=EnoValList[2], qos=2, retain=True)
                        cmqtt.publish(item.Name + "/windspeed", payload=EnoValList[3], qos=2, retain=True)
                        cmqtt.publish(item.Name + "/rain", payload=EnoValList[4], qos=2, retain=True)
                    else:
                        cmqtt.publish(item.Name + "/sun/west", payload=EnoValList[1], qos=2, retain=True)
                        cmqtt.publish(item.Name + "/sun/south", payload=EnoValList[2], qos=2, retain=True)
                        cmqtt.publish(item.Name + "/sun/east", payload=EnoValList[3], qos=2, retain=True)

                    raise BreakIt

                for item in thermostate:
                    if packet.sender_hex == item.ID:
                        EnoValList = item.decode(packet)
                        if len(EnoValList) == 3:
                            cmqtt.publish(item.Name + "/temperature", payload=EnoValList[0], qos=2, retain=True)
                            cmqtt.publish(item.Name + "/setpoint", payload=EnoValList[1], qos=2, retain=True)
                            cmqtt.publish(item.Name + "/state", payload=EnoValList[2], qos=2, retain=True)
                        else:
                            cmqtt.publish(item.Name + "/state", payload=EnoValList[0], qos=2, retain=True)

                        raise BreakIt

                for item in shutters:
                    if packet.sender_hex == item.ID:
                        EnoValList = item.decode(packet)
                        cmqtt.publish(item.Name + "/position", payload=EnoValList[0], qos=2, retain=True)
                        cmqtt.publish(item.Name + "/state", payload=EnoValList[1], qos=2, retain=True)
                        raise BreakIt

                for item in dimmer:
                    if packet.sender_hex == item.ID:
                        EnoValList = item.decode(packet)
                        cmqtt.publish(item.Name + "/dimmvalue", payload=EnoValList[0], qos=2, retain=True)
                        cmqtt.publish(item.Name + "/state", payload=EnoValList[1], qos=2, retain=True)
                        raise BreakIt

                for item in switches:
                    if packet.sender_hex == item.ID:
                        EnoValList = item.decode(packet)
                        cmqtt.publish(item.Name + "/state", payload=EnoValList, qos=2, retain=True)
                        raise BreakIt

        except queue.Empty:
            continue
        except BreakIt:
            continue
        except KeyboardInterrupt:
            break
        except Exception:
            traceback.print_exc(file=sys.stdout)
            break


def SendSwToggle(communicator, messages):
    mainlogger.debug("SendSwToggle")
    communicator.send(messages[0])
    sleep(0.1)
    communicator.send(messages[1])


def on_message_set_dimmerstate(client, userdata, message):
    for item in dimmer:
        if item.Name in message.topic and message.payload != None:
            try:
                newvalue = int(message.payload)
            except ValueError:
                mainlogger.info("Value Error happened with " + str(message.topic))
                return

            esp2com.send(item.send_DimMsg(newState=newvalue)[0])


def on_message_light_toggle(client, userdata, message):
    mainlogger.debug("on_message_light_toggle(client, userdata, message):")
    for item in switches:
        if item.Name in message.topic:
            eno_msg = item.send_toggle()
            SendSwToggle(esp2com, eno_msg)


def on_message_set_brightness(client, userdata, message):
    for item in dimmer:
        if item.Name in message.topic and message.payload != None:
            try:
                newvalue = float(message.payload)
            except ValueError:
                mainlogger.info("Value Error happened with " + str(message.topic))
                return

            esp2com.send(item.send_DimMsg(newVal=newvalue)[0])


def on_message_shutter_set_state(client, userdata, message):
    for item in shutters:
        if item.Name in message.topic and message.payload != None:
            try:
                newvalue = int(message.payload)
            except ValueError:
                mainlogger.info("Value Error happened with " + str(message.topic))
                return

            esp2com.send(item.send_Move(newState=newvalue)[0])


def on_message_shutter_set_pos(client, userdata, message):
    for item in schutters:
        if item.Name in message.topic and message.payload != None:
            if item.isMoving:
                #if shutter is moving, stop it first and wait for a position update...
                #tested ok, works perfectly
                runpos = item.pos
                esp2com.send(item.send_Move(newState="Stop")[0])
                timesslept = 0
                while runpos == item.pos:
                    sleep(0.05)
                    timesslept+=1
                    if timesslept*0.05 >= item.tFull_s:
                        #seems like we already were in an endstop, eltako behaviour...
                        break
            #print("Sleep loop delay " + str(timesslept*50.0) + "ms, ran " + str(timesslept) + " times...")
            try:
                newvalue = float(message.payload)
            except ValueError:
                mainlogger.info("Value Error happened with " + str(message.topic))
                return

            esp2com.send(item.send_Move(newpos=float(message.payload))[0])


def on_message_thermo_set_temp(client, userdata, message):
    for item in thermostate:
        if item.Name in message.topic and message.payload != None:
            try:
                newvalue = float(message.payload)
            except ValueError:
                mainlogger.info("Value Error happened with " + str(message.topic))
                return

            esp2com.send(item.send_SetPoint(SetPoint=newvalue, block=1)[0])


def on_message_thermo_set_release(client, userdata, message):
    for item in thermostate:
        if item.Name in message.topic and message.payload != None:
            esp2com.send(item.send_Release()[0])


def on_connect(client, userdata, flags, rc):
    cmqtt.subscribe("my/home/automation/topic/#", qos=2)
    mainlogger.info("Connected to MQTT-Broker with result code "+str(rc))


def on_disconnect(cmqtt, obj, rc):
    mainlogger.info("Disconnected from MQTT-Broker with result code "+str(rc))


def on_message(mosq, obj, msg):
    mainlogger.info("From mqtt-broker: " + msg.topic + " " + str(msg.qos) + " " + str(msg.payload))


init_logging()

mainlogger = logging.getLogger('eno_backend')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
mainlogger.setLevel(logging.DEBUG)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
stream_handler.setFormatter(formatter)
mainlogger.addHandler(stream_handler)

esp2com = ESP2SerialCommunicator(port='/dev/ttyUSB0')
cmqtt = paho.Client(client_id="", clean_session=True)
cmqtt.username_pw_set(username="", password="")
cmqtt.message_callback_add("my/home/automation/topic", on_message_set_brightness)
cmqtt.message_callback_add("my/home/automation/topic", on_message_set_dimmerstate)
cmqtt.message_callback_add("my/home/automation/topic", on_message_light_toggle)
cmqtt.message_callback_add("my/home/automation/topic", on_message_shutter_set_state)
cmqtt.message_callback_add("my/home/automation/topic", on_message_shutter_set_pos)
cmqtt.message_callback_add("my/home/automation/topic", on_message_thermo_set_temp)
cmqtt.message_callback_add("my/home/automation/topic", on_message_thermo_set_release)
cmqtt.on_message = on_message
cmqtt.on_connect = on_connect
cmqtt.on_disconnect = on_disconnect

cmqtt.connect("127.0.0.1", port=1883)
esp2com.start()

wstop = threading.Event()
t = threading.Thread(name='eno-worker', target=eno_worker, args=(wstop,))
t.start()

mainlogger.info("Starting MQTT...")

cmqtt.loop_forever()

mainlogger.info('MQTT Exited, stopping other workers...')

if t.is_alive():
    wstop.set()
    t.join(timeout=10)

if esp2com.is_alive():
    esp2com.stop()
