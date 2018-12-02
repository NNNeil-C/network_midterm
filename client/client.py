# -*- coding: utf-8 -*-
import socket
import os
import sys
import logging
import threading
import random
import math
import struct
import time


class Client:
    def __init__(self, _file_name, _server_name, port):
        self.file_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.file_socket.bind(("127.0.0.1", 9999))
        self.next_seq_num = random.randint(0, 100)
        self.client_ACK = 0
        self.file_name = _file_name
        self.server_name = _server_name
        self.server_port = port
        self.client_port = 9999
        self.MSS = 2
        self.send_base = self.next_seq_num
        self.winSize = 10 * self.MSS
        self.file_length = 0

    def __del__(self):
        self.file_socket.close()

    def send_segment(self, SYN, ACK, Func, data=b""):
        # * is the character used to split
        seg = self.encode_data(SYN, ACK, Func, data)
        data = decode_segment(seg)
        print("发送:", data)
        address = (self.server_name, self.server_port)
        self.file_socket.sendto(seg, address)

    def encode_data(self, syn, ack, func, data):
        port = self.client_port.to_bytes(2, 'little')
        address = self.server_port.to_bytes(2, 'little')
        seq_number = self.next_seq_num.to_bytes(4, 'little')
        ack_number = self.client_ACK.to_bytes(4, 'little')
        flag = ((syn << 2) + (ack << 1) + func) & 0x00ff
        flag = flag.to_bytes(1, 'little')
        windows_size = self.winSize.to_bytes(2, 'little')
        checksum = get_checksum(port+address+seq_number+ack_number+flag+windows_size+data)
        return port+address+seq_number+ack_number+checksum+flag+windows_size+data

    def reliable_send_segment(self, SYN, ACK, Func, _data=b''):
        delay_time = 10
        self.send_segment(SYN, ACK, Func, _data)
        self.file_socket.settimeout(delay_time)

    def receive_segment(self):
        seg, address = self.file_socket.recvfrom(4096)
        try:
            data = decode_segment(seg)
            data['valid'] = is_correct(seg)
        except TypeError as error:
            print(error)
            data['valid'] = False
        return data, address

    def send_file(self, file):
        self.next_seq_num = self.send_base = 0
        print(self.file_length)
        SYN = 0
        ACK = 0
        Func = 0
        data = []
        data_size = 0
        print("begin to split file into MSS")
        while True:
            temp = file.read(self.MSS)
            data_size += len(temp)
            if temp == b'':
                break
            data.append(temp)
        print("finish")
        print('data: ', len(data))
        can_send = True
        while True:
            try:
                if can_send:
                    self.reliable_send_segment(SYN, ACK, Func, data[self.next_seq_num])
                    self.next_seq_num = self.next_seq_num + 1
                    can_send = False
                else:
                    mydata, addr = self.receive_segment()
                    if mydata['valid']:
                        if mydata['ack'] > self.send_base:
                            self.send_base = mydata['ack']
                            can_send = True
                            if mydata['ack'] == self.file_length:
                                print('file transmission over')
                                break
            except socket.timeout as reason:
                print(reason)
                can_send = True
                if self.send_base == self.file_length-1:
                    print(self.send_base, self.file_length)
                    time.sleep(10)
                    break

    def receive_file(self, file):
        SYN = 0
        ACK = 0
        Func = 1
        self.send_base = self.next_seq_num = self.client_ACK = 0
        can_send = False
        while True:
            try:
                if can_send:
                    self.reliable_send_segment(SYN, ACK, Func)
                    self.next_seq_num = self.next_seq_num + 1
                    self.file_socket.settimeout(2)
                    can_send = False
                else:
                    mydata = self.receive_segment()
                    if mydata['valid']:
                        if mydata['seq'] + 1 > self.client_ACK:
                            file.write(mydata['data'])
                            self.client_ACK = mydata['seq']
                        can_send = True
            except socket.timeout as reason:
                print(reason)
                can_send = True
                if self.send_base == self.file_length:
                    break

    def hand_shake(self, func):
        if func == 0:
            self.file_length = math.ceil(os.path.getsize(self.file_name) / self.MSS)
        fileinfo = b"%b %d" % (self.file_name.encode('utf-8'), self.file_length)
        mydata = b''
        SYN = 1
        ACK = 0
        while True:
            try:
                self.reliable_send_segment(SYN, ACK, func, mydata)
                data, addr = self.receive_segment()
                print('valid: ', data['valid'])
                if data['valid']:
                    if data['SYN'] == 1 and data['ACK'] == 1 and data['ack'] == self.next_seq_num + 1:
                        self.client_ACK = data['seq'] + 1
                        self.next_seq_num = data['ack']
                        self.server_port = data['port']
                        SYN = 0
                        ACK = 1
                        mydata = fileinfo
                    elif not data['SYN']:
                        if data['FUNC'] == 1:
                            self.file_length = int.from_bytes(data['data'], 'little')
                        break
            except socket.timeout as reason:
                print(reason)
        return True


def get_checksum(data):
    checksum = 0
    for i in range(0, len(data), 2):
        checksum += int.from_bytes(data[i:i + 2], 'little')
        carry = checksum & ~0x1ff
        checksum &= 0xff
        checksum += carry
    checksum = (~checksum) & 0xff
    return checksum.to_bytes(2, 'little')


def is_correct(segment):
    return get_checksum(segment) == b'\x00\x00'


def decode_segment(segment):
    if len(segment) < 17:
        print("segment error")
        return {}
    data = b''
    port = segment[0:2]
    address = segment[2:4]
    seq_number = segment[4:8]
    ack_number = segment[8:12]
    checksum = segment[12:14]
    flag = segment[14:15]
    flag = int.from_bytes(flag, 'little')
    syn = ((flag & (1 << 2)) >> 2)
    ack = ((flag & (1 << 1)) >> 1)
    func = (flag & 1)
    windows_size = segment[15:17]
    if len(segment) > 17:
        data = segment[17:]
    return {'port': int.from_bytes(port, 'little'), 'address': int.from_bytes(address, 'little'),
            'seq': int.from_bytes(seq_number, 'little'), 'ack': int.from_bytes(ack_number, 'little'),
            'SYN': syn, 'ACK': ack, 'FUNC': func,
            'winsize': int.from_bytes(windows_size, 'little'), 'checksum': checksum, 'data': data}


if __name__ == "__main__":
    default_port = 5555
    server_name = "127.0.0.1"
    file_name = "././test.txt"
    client = Client(file_name, server_name, default_port)
    func = "lsend"
    if func == "lsend":
        with open(file_name, "rb") as file:
            # TCP construction
            if client.hand_shake(0):
                print("TCP construct successfully")
                client.send_file(file)
    elif func == "lget":
        with open(file_name, "wb") as file:
            # TCP construction
            if client.hand_shake(1):
                print("TCP construct successfully")
                client.receive_file(file)
