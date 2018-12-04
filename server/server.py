import socket
import random
import time
import logging
import os
import threading
import math

class Interface:
    def __init__(self, address, seq, func):
        self.file_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client_port = random.randint(5600, 10000)
        self.file_socket.bind(("127.0.0.1", self.client_port))
        self.client_ACK = seq + 1
        (self.server_name, self.server_port) = address
        self.MSS = 10
        self.send_base = self.next_seq_num = random.randint(0, 100)
        self.winSize = 5
        self.congestion_winSize = 50
        self.threshold = 30
        self.file_length = 0
        self.lockForBase = threading.Lock()
        if self.hand_shake(func):
            if func == 0:
                with open(self.file_name, "wb") as file:
                    self.receive_file(file)
            else:
                with open(self.file_name, "rb") as file:
                    self.send_file(file)

    def __del__(self):
        self.file_socket.close()

    def send_segment(self, SYN, ACK, Func, data=b""):
        seg = self.encode_data(SYN, ACK, Func, data)
        data = decode_segment(seg)
        print("发送:", data)
        address = (self.server_name, self.server_port)
        # if random.randint(0, 10) > 2:
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
        delay_time = 2
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
        print("接收: ", data)
        return data, address

    def send_file(self, file):
        self.next_seq_num = self.send_base = 0
        self.file_length = os.path.getsize(self.file_name)
        SYN = 0
        ACK = 0
        Func = 1
        while True:
            try:
                self.reliable_send_segment(SYN, ACK, Func, b'%d' % self.file_length)
                mydata, addr = self.receive_segment()
                if len(mydata['data']) != 0:
                    break
            except socket.timeout as reason:
                print(reason)
        Func = 0

        data_buffer = []
        buffer_begin = 0
        buffer_begin += len(data_buffer) * self.MSS
        data_buffer, data_ack = self.get_buffer(file, self.winSize)
        can_send = True
        while True:
            try:
                if can_send:
                    # and min congestion window
                    while self.next_seq_num < buffer_begin + min(min(self.winSize, len(data_buffer)), self.congestion_winSize) * self.MSS:
                        self.reliable_send_segment(SYN, ACK, Func,
                                                   data_buffer[(self.next_seq_num - buffer_begin) // self.MSS])
                        self.next_seq_num = self.next_seq_num + self.MSS
                    can_send = False
                else:
                    mydata, addr = self.receive_segment()
                    self.winSize = mydata['winsize']
                    if mydata['valid']:
                        if mydata['ack'] > self.send_base:
                            #拥塞控制
                            if (self.congestion_winSize < self.threshold):
                                self.congestion_winSize = self.congestion_winSize * 2
                            else:
                                self.congestion_winSize = self.congestion_winSize + 1
                            self.send_base = mydata['ack']
                            if self.send_base < self.next_seq_num:
                                self.file_socket.settimeout(2)
                            else:
                                buffer_begin += len(data_buffer) * self.MSS
                                data_buffer, data_ack = self.get_buffer(file, self.winSize)
                                can_send = True
                            if mydata['ack'] >= self.file_length:
                                print('file transmission over')
                                break
                
            except socket.timeout as reason:
                #拥塞控制
                self.threshold = math.ceil(self.threshold / 2)
                self.congestion_winSize = 1
                print(reason)
                if self.send_base >= self.file_length:
                    print(self.send_base, self.file_length)
                    break
                elif self.send_base < self.next_seq_num:
                    temp = self.next_seq_num
                    self.next_seq_num = self.send_base
                    self.reliable_send_segment(SYN, ACK, Func,
                                               data_buffer[(self.send_base - buffer_begin) // self.MSS])
                    self.next_seq_num = temp

    def get_buffer(self, file, size):
        buf = []
        ack = []
        for i in range(size):
            temp = file.read(self.MSS)
            if temp == b'':
                break
            buf.append(temp)
            ack.append(False)
        return buf, ack

    def get_last_ack(self, data):
        for i in range(len(data)):
            if data[i] == b'':
                return i
        return -1

    def get_free_buff(self, data):
        count = 0
        for i in range(len(data)):
            if data[i] == b'':
                count += 1
        return count

    def write_buffer_to_file(self, file, data):
        print(data)
        for temp in data:
            file.write(temp)

    def receive_file(self, file):
        SYN = 0
        ACK = 0
        Func = 0
        data_buffer = [b'']*self.winSize

        buffer_begin = 0
        print('begin to receive file:', self.file_length)
        self.send_base = self.next_seq_num = self.client_ACK = rtACK = 0
        can_send = True
        while True:
            try:
                if can_send:
                    self.reliable_send_segment(SYN, ACK, Func)
                    can_send = False
                else:
                    mydata, addr = self.receive_segment()
                    can_send = True
                    if mydata['valid'] and not mydata['ACK'] == 1:
                        print(mydata['seq'], buffer_begin, len(data_buffer))
                        if mydata['seq'] < buffer_begin or mydata['seq'] > buffer_begin + len(data_buffer) * self.MSS:
                            print("continue")
                            continue
                        if data_buffer[(mydata['seq'] - buffer_begin) // self.MSS] == b'':
                            data_buffer[(mydata['seq'] - buffer_begin) // self.MSS] = mydata['data']
                            self.winSize = self.get_free_buff(data_buffer)
                            print(rtACK, mydata['seq'], mydata['seq'] + len(mydata['data']))
                            if rtACK >= mydata['seq'] and rtACK < mydata['seq'] + len(mydata['data']):
                                next_ack = self.get_last_ack(data_buffer)
                                print('next ack', next_ack)
                                if next_ack == -1:
                                    self.client_ACK = rtACK = buffer_begin + len(data_buffer) * self.MSS
                                    self.write_buffer_to_file(file, data_buffer)
                                    self.winSize = 50
                                    data_buffer = [b'']*self.winSize
                                    buffer_begin = self.client_ACK
                                else:
                                    if buffer_begin + next_ack * self.MSS - rtACK <= self.MSS:
                                        socket.timeout(1)
                                        can_send = False
                                    self.client_ACK = rtACK = buffer_begin + next_ack * self.MSS
                                    if self.client_ACK >= self.file_length:
                                        can_send = True
                                    print(self.client_ACK, self.file_length)
                #加入拥塞控制
                self.congestion_winSize = self.congestion_winSize * 2
            except socket.timeout as reason:
                self.congestion_winSize = 5
                print(reason)
                can_send = True
                if self.client_ACK >= self.file_length:
                    self.write_buffer_to_file(file, data_buffer)
                    print("RECEIVE FILE OVER")
                    break


    def hand_shake(self, func):
        SYN = 1
        ACK = 1
        while True:
            try:
                print("START HANDSHAKE")
                self.reliable_send_segment(SYN, ACK, func)
                data, addr = self.receive_segment()
                print('hand shake:', data)
                if data['valid']:
                    if data['ACK'] == 1:
                        f = data['data'].split(b" ")
                        self.file_name = './data/' + f[0].decode('utf-8')
                        self.file_length = int(f[1])
                        break
            except socket.timeout as reason:
                print(reason)
        print("HANDSHAKE SUCCESS")
        return True


class Server:
    def __init__(self):
        self.file_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.file_socket.bind(('127.0.0.1', 5555))
        addr_info = {}

    def receive_segment(self):
        seg, address = self.file_socket.recvfrom(4096)
        try:
            data = decode_segment(seg)
            data['valid'] = is_correct(seg)
        except TypeError as error:
            print(error)
            data['valid'] = False
        return data, address



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


def handler(addr, seq, func):
    Interface(addr, seq, func)
    # del addr in addr_info
    addr_info.remove(addr)


addr_info = []

if __name__ == "__main__":
    server = Server()
    addr = ()
    seq = 0
    func = 0
    while True:
        data, addr = server.receive_segment()
        if (data['SYN'] == 1 and addr not in addr_info):
            # addr -> addr_info
            addr_info.append(addr)
            seq = data['seq']
            func = data['FUNC']
            t = threading.Thread(target=handler, args=(addr, seq, func))
            t.start()

