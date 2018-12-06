# -*- coding: utf-8 -*-
import socket
import os
import math
import random
import sys



class Client:
    def __init__(self, _file_name, _server_name, port):
        self.file_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client_port = random.randint(10000, 12000)
        self.file_socket.bind(("127.0.0.1", self.client_port))
        self.next_seq_num = random.randint(0, 100)
        self.client_ACK = 0
        self.file_name = _file_name
        self.server_name = _server_name
        self.server_port = port
        self.MSS = 1024
        self.send_base = self.next_seq_num
        self.initWinSize = 50
        self.winSize = self.initWinSize
        self.congestion_winSize = 50
        self.file_length = 0
        self.threshold = 30

    def __del__(self):
        self.file_socket.close()

    def send_segment(self, SYN, ACK, Func, data=b""):
        seg = self.encode_data(SYN, ACK, Func, data)
        data = decode_segment(seg)
        
        #进度条
        global func
        global start
        if (start == True and func == 'lget'):
            sys.stdout.write('\r')
            done = (data['ack'] * 100 // self.file_length)
            done = min(100, done)
            sys.stdout.write("[%s>%s] %s" % ('-'*done, ' '*(100 - done),str(done)+'%'))
            sys.stdout.flush()
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
            #进度条
            global func
            global start
            if (start == True and func == 'lsend'):
                sys.stdout.write('\r')
                done = (data['ack'] * 100 // self.file_length)
                done = min(done, 100)
                sys.stdout.write("[%s>%s] %s" % ('-'*done, ' '*(100 - done),str(done)+'%'))
                sys.stdout.flush()

        except TypeError as error:
            print(error)
            data['valid'] = False
        return data, address

    def get_buffer(self, file, size,  buf):
        buf = buf[size:]
        for i in range(size):
            temp = file.read(self.MSS)
            if temp == b'':
                break
            buf.append(temp)
        return buf, size

    def send_file(self, file):
        self.next_seq_num = self.send_base = 0
        print("Beging to send file: %s, size: %d" % (self.file_name, self.file_length))
        SYN = 0
        ACK = 0
        Func = 0

        buffer_begin = 0
        data_buffer = []
        data_buffer, _ = self.get_buffer(file, self.initWinSize, data_buffer)
        can_send = True
        duplication = 0
        while True:
            try:
                if can_send:
                    # and min congestion window
                    while self.next_seq_num < self.send_base + min(self.winSize, self.congestion_winSize) * self.MSS \
                            and self.next_seq_num < buffer_begin + len(data_buffer) * self.MSS:
                        self.reliable_send_segment(SYN, ACK, Func,
                                                   data_buffer[(self.next_seq_num - buffer_begin) // self.MSS])
                        self.next_seq_num = self.next_seq_num + self.MSS
                    can_send = False
                else:
                    mydata, addr = self.receive_segment()
                    # flow control
                    self.winSize = mydata['winsize']
                    if mydata['valid']:
                        if mydata['ack'] > self.send_base:
                            self.file_socket.settimeout(0.5)
                            # 拥塞控制
                            if self.congestion_winSize < self.threshold:
                                self.congestion_winSize = \
                                    self.congestion_winSize * math.pow(2, (mydata['ack']-self.send_base) // self.MSS)
                                if (self.congestion_winSize > self.threshold):
                                    self.congestion_winSize = self.threshold
                            else:
                                self.congestion_winSize = \
                                    self.congestion_winSize + (mydata['ack']-self.send_base) // self.MSS
                            if self.send_base > self.next_seq_num:
                                self.next_seq_num = self.send_base
                            self.send_base = mydata['ack']
                            data_buffer, had_write = \
                                self.get_buffer(file, (self.send_base - buffer_begin) // self.MSS, data_buffer)
                            buffer_begin = buffer_begin + had_write * self.MSS
                            self.next_seq_num = self.send_base
                            can_send = True
                            if mydata['ack'] >= self.file_length:
                                print('\nSend file over')
                                break
                        else:
                            duplication += 1
                            if duplication >= 3:
                                duplication = 0
                                self.congestion_winSize = (self.congestion_winSize+1) // 2
                                self.next_seq_num = self.send_base
                                self.reliable_send_segment(SYN, ACK, Func,
                                                           data_buffer[(self.next_seq_num - buffer_begin) // self.MSS])
                                can_send = False
                                continue
            except socket.timeout as reason:
                # 拥塞控制
                self.threshold = (self.threshold + 1) // 2
                self.congestion_winSize = 1
                if self.send_base >= self.file_length:
                    print("Send file over")
                    break
                elif self.send_base <= self.next_seq_num:
                    self.next_seq_num = self.send_base
                    can_send = True
            except Exception as reason:
                sys.stdout.write('\r')
                done = 100
                sys.stdout.write("[%s>%s] %s" % ('-' * done, ' ' * (100 - done), str(done) + '%'))
                sys.stdout.flush()
                print("\nSend file over")
                break


    def get_last_ack(self, data):
        for i in range(len(data)):
            if data[i] == b'':
                return i
        return len(data)

    def get_free_buff(self, data):
        count = 0
        for i in range(len(data)):
            if data[i] == b'':
                count += 1
        return count

    def write_buffer_to_file(self, file, data):
        i = 0
        for i in range(len(data)):
            if data[i] == b'':
                break
            file.write(data[i])
        if i == len(data)-1 and data[i] != b'':
            i += 1
        buffer = data[i:] + [b''] * i
        return buffer

    def slide_windows(self, file, data_buffer, buffer_begin, ):
        self.file_socket.settimeout(2)
        next_ack = self.get_last_ack(data_buffer)
        data_buffer = self.write_buffer_to_file(file, data_buffer)
        self.client_ACK = buffer_begin + next_ack * self.MSS
        buffer_begin = self.client_ACK
        return data_buffer, buffer_begin, self.get_free_buff(data_buffer)

    def receive_file(self, file):
        SYN = 0
        ACK = 0
        Func = 1
        data = b"***"
        data_buffer = [b''] * self.winSize
        buffer_begin = 0
        print('Begin to receive file:', self.file_length)
        self.send_base = self.next_seq_num = self.client_ACK = 0
        can_send = True
        while True:
            try:
                if can_send:
                    # send ack and start timeout
                    self.reliable_send_segment(SYN, ACK, Func, data)
                    can_send = False
                else:
                    mydata, addr = self.receive_segment()
                    can_send = True
                    if mydata['valid'] and mydata['FUNC'] == 0:
                        # func == 0 mean both server an client get the file information
                        if mydata['FUNC'] == 0:
                            data = b''
                            # out of buffer
                            if mydata['seq'] < buffer_begin or buffer_begin + len(
                                    data_buffer) * self.MSS <= mydata['seq']:
                                can_send = False
                                continue
                            # data no in buffer
                            if data_buffer[(mydata['seq'] - buffer_begin) // self.MSS] == b'':
                                data_buffer[(mydata['seq'] - buffer_begin) // self.MSS] = mydata['data']
                                self.winSize = self.get_free_buff(data_buffer)
                                if self.client_ACK == mydata['seq']:
                                    next_ack = self.get_last_ack(data_buffer)
                                    # buffer full of data
                                    if next_ack == len(data_buffer):
                                        data_buffer, buffer_begin, self.winSize = \
                                            self.slide_windows(file, data_buffer, buffer_begin)
                                    else:
                                        if buffer_begin + next_ack * self.MSS - self.client_ACK == self.MSS:
                                            self.file_socket.settimeout(0.5)
                                            can_send = False
                                            self.client_ACK = buffer_begin + next_ack * self.MSS
                                        else:
                                            data_buffer, buffer_begin, self.winSize = \
                                                self.slide_windows(file, data_buffer, buffer_begin)
                                        if self.client_ACK >= self.file_length:
                                            self.write_buffer_to_file(file, data_buffer)
                                            data_buffer = []
                                            can_send = True
                            else:
                                data_buffer, buffer_begin, self.winSize = \
                                    self.slide_windows(file, data_buffer, buffer_begin)
                                continue
            except socket.timeout as reason:
                can_send = True
                if self.client_ACK >= self.file_length:
                    self.write_buffer_to_file(file, data_buffer)
                    print("\nRECEIVE FILE OVER")
                    break
                data_buffer, buffer_begin, self.winSize = \
                    self.slide_windows(file, data_buffer, buffer_begin)
            except Exception as reason:
                print("\nRECEIVE FILE OVER")
                break

    def hand_shake(self, func):
        if func == 0:
            self.file_length = os.path.getsize(self.file_name)
        fileinfo = b"%b %d" % (self.file_name.encode('utf-8'), self.file_length)
        mydata = b''
        SYN = 1
        ACK = 0
        while True:
            try:
                self.reliable_send_segment(SYN, ACK, func, mydata)
                data, addr = self.receive_segment()
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
                            self.file_length = int(data['data'])
                        print('HAND SHAKE OVER:', self.file_length)
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
    command = input('Enter your command: ')
    command_list = command.split()
    func = command_list[1]
    server_name = command_list[2]
    file_name = command_list[3]
    client = Client(file_name, server_name, default_port)
    start = False
    if func == "lsend":
        with open(file_name, "rb") as file:
            # TCP construction
            print('正在尝试拜访服务器...')
            if client.hand_shake(0):
                start = True
                print("TCP(using UDP) construct successfully")
                print('正在向 {server} 上传数据({filepath})...'.format(server = server_name, filepath = file_name))
                client.send_file(file)
    elif func == "lget":
        with open(file_name, "wb") as file:
            # TCP construction
            print('正在尝试拜访服务器...')
            if client.hand_shake(1):
                start = True
                print("TCP（using UDP） construct successfully")
                print('正在从 {server} 下载数据({filepath})...'.format(server = server_name, filepath = file_name))
                client.receive_file(file)