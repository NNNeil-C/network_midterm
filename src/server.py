import socket
import threading
import time
import sys
import struct
import os

'''
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#绑定端口
s.bind(('127.0.0.1', 9999))

print('Bind UDP on 9999')
while True:
    data, addr = s.recvfrom(1024)
    print('Received from %s:%s' % addr)
    s.sendto(b'hello, %s!' % data, addr)

'''

def socket_service():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1', 9999))
        s.listen(10)
    except socket.error as msg:
        print(msg)
        sys.exit(1)

    print('Waiting connection...')

    while True:
        conn, addr = s.accept()
        t = threading.Thread(target=deal_data, args=(conn, addr))
        t.start()


def deal_data(conn, addr):
    print('Accept new connection from {0}'.format(addr))

    conn.send(b'Hi, Welcom to the server!')

    while True:
        fileinfo_size = struct.calcsize('128sl')
        buffer = conn.recv(fileinfo_size)
        if buffer:
            filename, filesize = struct.unpack(b'128sl', buffer)
            fn = filename.strip(b'\00')
            modified_filename = os.path.join(b'd:\\networkdata', b'new_' + fn)
            print('file new name is {0}, file size is {1}'.format(modified_filename, filesize))

            #接收文件的大小
            recv_size = 0
            fp = open(modified_filename, 'wb')
            print('start receiving...')

            while not recv_size == filesize:
                if filesize - recv_size > 1024:
                    data = conn.recv(1024)
                    recv_size += len(data)
                else:
                    data = conn.recv(filesize - recv_size)
                    recv_size = filesize
                fp.write(data)
            
            fp.close()

            print('end receiving...')
            
        conn.close()
        break


if __name__ == '__main__':
    socket_service()  