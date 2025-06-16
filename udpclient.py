# udp_client.py
import socket


def udp_client(server_host='127.0.0.1', server_port=8009, message="bj200301,,192.168.0.11,,8000,,admin,,12345,,1"):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        # 发送消息到服务器
        s.sendto(message.encode(), (server_host, server_port))

        # # 接收来自服务器的响应
        # data, server = s.recvfrom(1024)
        # print(f"Received from server {server}: {data.decode()}")


if __name__ == "__main__":
    udp_client()