import socket
from time import sleep

def send_udp_message(message, host, port):
    """
    通过UDP发送消息到指定的主机和端口

    参数:
        message (str): 要发送的字符串消息
        host (str): 目标主机的IP地址
        port (int): 目标端口号
    """
    try:
        # 创建UDP套接字
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # 发送消息（注意：UDP不需要建立连接）
        # encode()将字符串转换为字节流
        sock.sendto(message.encode('utf-8'), (host, port))

        print(f"消息已发送到 {host}:{port} - {message}")

    except Exception as e:
        print(f"发送消息时出错: {e}")
    finally:
        # 关闭套接字
        sock.close()


# 使用示例
if __name__ == "__main__":
    target_ip = "192.168.20.31"  # 替换为目标IP地址
    target_port = 8088  # 替换为目标端口号
    # message_to_send = "bj200322,,192.168.20.30,,8000,,admin,,12345,,33,,bj200330_33_11_37_46_297.gif"
    # 定义一个包含多条消息的消息集合
    message_to_send_list = [
        "bj200322,,192.168.0.11,,8000,,admin,,12345,,33,,bj200322_1_10_39_32_202.gif",
    ]

    for message_to_send in message_to_send_list:
        print(f"准备发送消息给udpserver: {message_to_send}...")
        send_udp_message(message_to_send, target_ip, target_port)
        print("消息发送完成。\n")

        sleep(3)  # 等待3秒钟再发送下一条消息
