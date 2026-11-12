# 构建与测试

这是表盘 `0.5.3`、手机 `0.5.1` 表盘＋通信快应用／运动健康无线导出版本，代码及安装包先交付，设备验收待完成。源码、主机模拟或成功打包不等于已在真实手表完成验收。单 RPK 录音探针不再参与本项目构建。

## 构建依赖

- Python 3.11+，运行 `python -m pip install -r requirements-build.txt`。
- ARM GCC、JDK，以及自己合法取得的 P65 3.100.043 AP / audio 固件输入。全文件 SHA 与运行时校验窗口必须同时匹配。
- 外部兼容 `Mi8WfBinTool.java` 打包器。这个打包器的上游许可尚未完整核对，项目**不包含**它；请自行取得合法的兼容工具，并用 `W6R_PACKER_SOURCE` 指定源文件。构建会将其编译到被忽略的 `build/external-packer`，不会复制到公开源码。

配置路径仅使用环境变量，或复制 `build-config.example.json` 为被忽略的 `.local-build.json` 填写本机位置。不要提交个人配置、固件、工具链、SDK 或 ELF。

```powershell
$env:VOICESPACE_ARM_TOOLCHAIN='你的工具链目录'
$env:VOICESPACE_WATCH_FIRMWARE='你的固件目录'
$env:JAVA_HOME='你的JDK目录'
$env:W6R_PACKER_SOURCE='你合法取得的兼容打包器源文件'
python build.py
```

输出 `artifacts/Watch6-Recorder-0.5.3.bin` 和 `build/build-report.json`。分别编译采音、完整回听、运动健康传输和只读模块登记查询，合并精确固件校验窗口，完整解析打包结果并核对内嵌 Lua/模块。本版不嵌入独立 BLE 实验 ELF；若旧模块仍持有回调或文件，会保留缓存并提示录音结束后完整重启，不强制卸载。构建只读固件、编译和打包，不会连接或写入手表。

手机 APK 在 `phone-app` 中单独构建，输出 `phone-app/artifacts/Watch6-Recorder-Phone-0.5.1.apk`。需要 JDK、Android SDK、获授权的运动健康 SDK JAR 和自己的签名输入，不需要识别服务密钥。手表无线导出还需 `Watch6-Recorder-Identity-0.5.0.rpk`：同包名、同签名，只有 `system.interconnect` 身份，无录音接口。连接身份与手机应使用同一证书；不要发布私钥。构建步骤见 [手机构建说明](phone-app/README.md)。

## 测试

```sh
python tests/run_all.py --host-only
python tests/run_all.py --native
```

测试执行真实 Lua 录音/目录/回听/导出/界面/编排模块，以及 Python WAV 校验和源码隐私保护。可用工具齐备时，发现的播放与传输测试会运行实际 ARM C；`--native` 另外强制执行采音核心 ARM 套件。因此完整依赖包括 ARM 工具链、Lupa、Unicorn。`--host-only` 并不禁止其他测试使用 ARM 模拟，只是不额外运行采音核心套件。测试不会读取麦克风、连接蓝牙或请求云端。

手机前端另用 Node 运行 `node phone-app/tests/frontend.test.cjs`，执行实际生产 JS 的 DOM/原生桥回放。`python tools/render_ui_review.py` 可用自有中文字体生成实际 Lua 控件模型的布局预览；这是近似渲染，不是设备截图。

手机构建与实际 Java 存储/协议测试见 `phone-app/README.md`。`tests/test_phone_crosslayer.py` 覆盖实际 ARM 导出编码与 Java Protocol/ArchiveStore；手机 SDK 回调测试验证授权、重连、队列与旧回调隔离。跨语言测试依赖 JDK 和外置 JSON-java 测试 JAR；无线射频、操作系统安全策略和真实吞吐不由这些测试证明。默认回归和发布源码不包含已停用的独立 BLE 实验；完整历史工作区可用 `--include-experimental` 显式运行历史测试。

## 获取录音及导出

数据目录为 `/data/watch6recorder/`。表上完整回听与无线发送都先用小块流式校验封存分段，生成标准 WAV；缓存只有在播放器与导出器都证明已关闭源文件、不再持有该缓存时才允许替换。BLE 回调模块可以保持驻留，不把模块阶段或页面退出当作源文件关闭证明。它不自动删除源 PCM、metadata 或会议原音。

无线导出：表盘负责录音与完整回听；首次安装连接身份 RPK，并在手机 APK 允许运动健康通信后，选择已保存录音 → 发送到手机。此链路复用运动健康配对，不新建独立 BLE 广播／扫描。手机确认持久化保存后，可以回听、分享或保存 Download。后台重连逐步退避；关闭接收后不会自行开启，恢复时不会绕过首次授权。

下列主机工具是独立恢复入口，需先通过自己有权使用的方式取得该目录副本；它不负责连接手表：

保持 `.session`、`.meta`、`.pcm`、`.end` 文件完整，然后在电脑执行：

```sh
python tools/export_wav.py --source /path/to/copied-recordings --id 0123456789abcdef
python tools/export_wav.py --source /path/to/copied-recordings --id 0123456789abcdef --output /path/to/output.wav
```

只有身份、顺序、CRC、采样率和结束账本全部通过才输出完整 WAV；不覆盖已有文件，不修改或自动删除原始分段。不完整录音需要显式 `--allow-partial`。断电后没有结束账本时可显式 `--recover-sealed`，只恢复已封存并通过校验的部分，未封存尾音不算完整。输出目录需支持同卷硬链接（例如 NTFS、ext4），否则拒绝发布，避免留下半个 WAV。

## 实机验收

按自己的合法表盘导入方式安装预览包，只测试所列精确固件。先离线验证录音与回听，再验证连接身份、运动健康授权和手机接收端，最后测试真实无线导出。还需核对中文显示、显式开始、准备后计时、暂停继续、尾音、连续下一条、息屏录音、断电恢复、剩余空间保护、完整回听、手机息屏和重连。原生无法确认退出时保留所有文件并完整重启；不能通过强制卸载、改校验或写入固件来绕过保护。
