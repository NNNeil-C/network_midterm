import socket
import os
import sys
import struct

'''
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

for data in [b'Michael', b'Tracy', b'sarah']:
    # 发送数据
    s.sendto(data, ('127.0.0.1', 9999))
    # 接收数据
    print(s.recv(1024).decode('utf-8'))

s.close()
'''

def socket_client():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(('127.0.0.1', 9999))
    except socket.error as msg:
        print(msg)
        sys.exit(1)
    
    print(s.recv(1024))

    while True:
        filepath = input('Please enter the file to send: ')
        if os.path.isfile(filepath):
            #定义文件大小，将其分割成一个个小块， 128sl表示文件名长128bytes，l表示一个int文件类型，表示文件大小
            fileinfo_size = struct.calcsize('128sl')
            #定义文件头
            filehead = struct.pack(b'128sl', os.path.basename(filepath).encode('utf-8'), os.stat(filepath).st_size)

            s.send(filehead)
            print('client filepath: {0}'.format(filepath))

            fp = open(filepath, 'rb')
            while True:
                data = fp.read(1024)
                if not data:
                    print('file sending over')
                    break
                s.send(data)
        
        s.close()
        break

if __name__ == '__main__':
    socket_client()