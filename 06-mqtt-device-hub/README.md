# 06 · MQTT 设备接入 Hub（3.1.1 编解码 + 订阅路由 + 影子）

## 解决什么问题
设备接入平台最底层的工作是"把字节讲清楚"：一条报文哪些字节是类型、哪些是 QoS、剩余长度怎么变长编码；订阅一个 `dev/+/temp` 到底匹配哪些主题、`$SYS` 为什么不能被 `#` 匹配；断线重连后哪些消息该补发、retained 该不该重放。这些判断错一位就会导致丢消息或重复控制。

## 怎么实现
- `src/codec.py`：MQTT 3.1.1 报文的编码与解码，覆盖 CONNECT / CONNACK / PUBLISH（QoS0/1，含 DUP、RETAIN）/ PUBACK / SUBSCRIBE / SUBACK / PINGREQ / DISCONNECT；`remaining length` 的 7 位变长编解码（上限 268435455）；UTF-8 字段 2 字节长度前缀；解析时对截断报文抛 `CodecError`（带类型与声明长度）
- `src/topic.py`：`+` 单层、`#` 末层、非法过滤器校验（`a/#/b`、`a#`、`a/+b` 都拒绝）；发布主题禁止通配符；`$SYS` 主题不被 `#`/`+` 匹配（规范例外）
- `src/broker.py`：会话与 clean session 语义、订阅 QoS 协商（`min(pub, sub)`）、retained 存储与"空 payload 清除"、新订阅者补发 retained、持久会话离线队列、QoS1 按 `packet_id` 去重、设备影子 `desired/reported` 求 delta、收发统计
- `src/demo.py`：编解码 hex 往返、5 组通配符用例、路由/离线/retained/影子全流程

## 跑起来
```bash
python3 src/demo.py                        # 报文 hex、主题匹配、路由与影子
python3 -m unittest discover -s tests -v   # 30 项
```

## 验证
30 项测试覆盖：剩余长度的 0/127/128/16383/16384/2097151/268435455 往返与溢出/截断、CONNECT 全字段往返、CONNACK、QoS0/QoS1 PUBLISH（缺 packet_id 报错）、SUBSCRIBE flags=0x02、SUBACK 失败码、未知类型与过短报文；精确/单层/多层匹配、`$SYS` 例外、非法过滤器与通配符主题；路由只发订阅者、retained 补发与清除、持久会话离线队列、QoS1 重复丢弃、clean session 清状态、影子 delta、下发报文 wire 往返。

## 边界
- QoS2（PUBREC/PUBREL/PUBCOMP）只做类型识别与解码，没有实现完整四段握手
- 没有 TLS、没有鉴权、没有遗嘱消息（Will）、没有 keepalive 超时踢线、没有 `$SYS` 统计主题的自动发布
- broker 是单进程内存实现，会话不持久化、不支持集群与桥接
- 只做"内存 + 报文层"，不接真实 TCP 监听；实际部署要套 socket/select 或 asyncio
