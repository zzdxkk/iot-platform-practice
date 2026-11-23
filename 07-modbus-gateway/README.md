# 07 · Modbus 网关（RTU/TCP 编解码 + 寄存器服务端 + 多从站轮询)

## 解决什么问题
现场设备 90% 是 Modbus。真正的坑都在字节层和错误处理上：CRC 高低字节顺序、MBAP 里的长度字段到底算不算 unit id、从站返回 `0x83/0x02` 时该重试还是该报错、一个从站掉线会不会把整轮轮询拖死。

## 怎么实现
- `src/codec.py`：`crc16`（多项式 0xA001、初值 0xFFFF、低字节先发）；`encode_rtu/decode_rtu`（CRC 不符抛错）；`encode_tcp/decode_tcp`（MBAP：transaction id + protocol id + length + unit，length 含 unit）；`build_read_holding`（数量 1–125 校验）、`build_write_single`、`build_write_multiple`（数量 1–123）；异常帧解码为 `function | 0x80` + 异常码 + 中文说明
- `src/registers.py`：`RegisterMap` 持有/输入双表；地址不连续、未定义地址、越界数量都转成对应异常码（0x02 / 0x03）；写入更新内存并计数
- `src/server.py`：`ThreadingTCPServer` 的多从站服务端，按 unit id 分派，未知 unit 也回 `0x83/0x02` 异常帧；异常帧与正常帧分开构造
- `src/client.py`：`ModbusTcpClient` 读/写/多从站轮询；只有网络错误才重试（从站异常直接抛 `ModbusExceptionResponse`，不浪费重试）；`poll()` 把坏从站隔离成 `ERR:` 字符串，其它从站继续
- `src/demo.py`：RTU hex + CRC、篡改一字节被拒、MBAP 解码、起服务端跑读/写/批量轮询、三类异常码

## 跑起来
```bash
python3 src/demo.py                        # 起本地从站，跑读/写/异常/批量轮询
python3 -m unittest discover -s tests -v   # 24 项
```

## 验证
24 项测试覆盖：CRC 已知向量（`01 03 00 00 00 0A` → `CDC5`）与低字节序、RTU 往返、篡改 CRC 被拒、异常帧解析、短帧与从站地址越界；MBAP 各字段位置、读数量上限 125、写数量上限 123、协议标识非 0 报错；寄存器读/写/地址空洞异常/值越界/数量 0；端到端读与写、非法地址 0x02、未知从站 0x02、数量越界客户端拦截、多从站轮询（坏从站不影响好从站）、连接被拒。

## 边界
- 客户端每条请求新建一次 TCP 连接，没有长连接复用；高频轮询要改成连接池
- RTU 只在编解码层实现，没有串口设备路径与 3.5 字符静默间隔处理；也没有广播地址 0 的特殊语义
- 功能码只做了 0x03/0x04/0x06/0x10，没做线圈（0x01/0x05/0x0F）与 0x17 读写复合
- 服务端是内存寄存器表，没有持久化、没有写保护与权限，也没有并发写入的顺序保证
