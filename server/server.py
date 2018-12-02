import socket
import random
import logging
import threading


class Interface:
    def __init__(self, address, seq, func):
        self.file_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.file_socket.bind(("127.0.0.1", 7777))
        self.client_ACK = seq + 1
        (self.server_name, self.server_port) = address
        self.client_port = 7777
        self.MSS = 2
        self.send_base = self.next_seq_num = random.randint(0, 100)
        self.winSize = 10 * self.MSS
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
        self.next_seq_num = self.send_base = 0;
        SYN = 0
        ACK = 0
        Func = 1
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

        can_send = True
        while True:
            try:
                if can_send:
                    self.reliable_send_segment(SYN, ACK, Func, data[self.next_seq_num])
                    self.next_seq_num = self.next_seq_num + 1
                    self.file_socket.settimeout(2)
                    can_send = False
                else:
                    mydata = self.receive_segment
                    if mydata['valid']:
                        if mydata['ack'] > self.send_base:
                            self.send_base = mydata['ack']
                            can_send = True
            except socket.timeout as reason:
                print(reason)
                can_send = True
                if self.send_base == self.file_length:
                    break

    def receive_file(self, file):
        SYN = 0
        ACK = 0
        Func = 0
        print('begin to receive file')
        self.send_base = self.next_seq_num = self.client_ACK = 0
        can_send = True
        while True:
            try:
                if can_send:
                    self.reliable_send_segment(SYN, ACK, Func)
                    can_send = False
                else:
                    mydata, addr = self.receive_segment()
                    print(mydata['valid'])
                    if mydata['valid']:
                        print('seq', mydata['seq'])
                        if mydata['seq'] + 1 > self.client_ACK:
                            file.write(mydata['data'])
                            self.client_ACK = mydata['seq'] + 1
                        can_send = True
            except socket.timeout as reason:
                print(reason)
                can_send = True
                if self.client_ACK == self.file_length:
                    break

    def hand_shake(self, func):
        SYN = 1
        ACK = 1
        while True:
            try:
                self.reliable_send_segment(SYN, ACK, func)
                data, addr = self.receive_segment()
                print('hand shake:', data)
                if data['valid']:
                    if data['ACK'] == 1:
                        f = data['data'].split(b" ")
                        self.file_name = './data'+  f[0].decode('utf-8')
                        self.file_length = int(f[1])
                        break
            except socket.timeout as reason:
                print(reason)
        return True


class Server:
    def __init__(self):
        self.file_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.file_socket.bind(('127.0.0.1', 5555))
        self.addr_info = {}

    def newInterface(self, addr, ACK, SEQ):
        #  New a buffer for the address
        clientInterface = Interface(self.fileSocket, addr, ACK, SEQ)
        self.addr_info[addr] = clientInterface

    def deleteInterface(self, addr):
        self.addr_info.pop(addr)

    def getInterface(self, addr):
        return self.addr_info[addr]

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


if __name__ == "__main__":
    server = Server()
    while True:
        data, addr = server.receive_segment()
        if data['SYN'] == 1:
            i = Interface(addr, data['seq'], data['FUNC'])