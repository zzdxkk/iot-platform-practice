"""演示：报文编解码、主题匹配、broker 路由、retained、QoS1 去重、影子 delta。"""
from broker import Broker
from codec import decode_packet, encode_connect, encode_publish, encode_subscribe
from topic import matches

TOPICS = [
    ("dev/1001/telemetry", "dev/+/telemetry"),
    ("dev/1001/telemetry/temp", "dev/+/telemetry"),
    ("dev/1001/telemetry/temp", "dev/#"),
    ("$SYS/broker/uptime", "dev/#"),
    ("$SYS/broker/uptime", "#"),
]


def main():
    print("== 报文编解码 ==")
    conn = encode_connect("dev-1001", keepalive=30, username="u", password="p")
    print("  CONNECT 字节：", conn.hex())
    print("  解码 CONNECT：", decode_packet(conn))
    pub = encode_publish("dev/1001/telemetry", '{"t":22.5}', qos=1, packet_id=7, retain=True)
    d = decode_packet(pub)
    print("  PUBLISH 字节：", pub.hex())
    print("  PUBLISH 解码：", {**d, "payload": d["payload"].decode()})

    print("\n== 主题通配符 ==")
    for topic, filter_ in TOPICS:
        print(f"  {filter_:22} 匹配 {topic:28} -> {matches(filter_, topic)}")

    print("\n== broker 路由 ==")
    b = Broker()
    b.connect("dev-1001", clean_session=False)   # 持久会话：离线也能收 QoS1
    print("  订阅返回码：", b.subscribe("dev-1001", [("dev/+/telemetry", 1), ("bad/#/x", 0)]))
    b.publish("dev/1001/telemetry", "22.5", qos=1, retain=True)
    print("  发给订阅者：", b.poll("dev-1001"))
    print("  报文（wire）：", b.to_wire({"topic": "dev/1001/telemetry", "payload": b"22.5",
                                        "qos": 1, "retain": True, "packet_id": 1}).hex())

    print("\n== 重复 QoS1 与离线队列 ==")
    print("  第一次：", b.accept_publish("dev-1001", "dev/1001/telemetry", "22.5", 1, 1))
    print("  重发同 packet_id：", b.accept_publish("dev-1001", "dev/1001/telemetry", "22.5", 1, 1))
    b.disconnect("dev-1001")
    b.publish("dev/1001/telemetry", "23.0", qos=1)
    print("  离线期间队列长度：", len(b.sessions["dev-1001"].queue) if "dev-1001" in b.sessions else 0)

    print("\n== 新订阅者的 retained ==")
    b.connect("dev-2002")
    b.subscribe("dev-2002", [("dev/+/telemetry", 0)])
    print("  收到 retained：", b.poll("dev-2002"))

    print("\n== 设备影子 ==")
    b.set_reported({"power": "on", "mode": "auto"})
    b.set_desired({"power": "on", "mode": "manual", "interval": 30})
    print("  delta：", b.delta())
    print("  统计：", b.stats)


if __name__ == "__main__":
    main()
