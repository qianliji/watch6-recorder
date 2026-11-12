# Watch6 录音手机接收端 0.5.1

通过小米运动健康接收手表录音，保留完整 WAV、回听、跳转进度、保存到下载和手动分享。没有手机录音、语音识别、云端请求或自动对外分享功能。

## 首次设置

1. 用小米运动健康正常配对 Watch 6。
2. 在手表安装录音表盘及同包名、同签名的「录音连接组件」0.5.0。组件只提供本方案所需的运动健康通信身份，不录音、不加载原生录音库；日常录音和回听只有表盘一个入口。该 RPK 的 versionCode 为 6，可替换 versionCode 4 的旧录音验证包。
3. 手机打开「Watch6 录音」，点「开启接收」，允许附近设备、通知与运动健康通信授权。
4. 需要手机息屏接收时，允许两个手机应用自启动及后台运行。

「接收已待命」表示监听已装好；只有收到有效录音协议后才显示「已连接手表」。

开启状态会保存在本机。手机应用恢复、系统重启或应用更新后，会尝试在后台恢复；自动恢复不弹出新的 SDK 授权界面。首次未授权或缺组件时会明确提示。系统强制停止、撤销权限或禁止后台运行仍需用户恢复设置。

手机不提供独立 BLE 模式、配对码、全局扫描或蓝牙开关操作。已保存的 0.3.1 直连实验版源码与安装包保留在 artifacts/releases/0.3.1-preview 和历史整包中。

## 传输与省电

SDK API 检查有 10 秒边界；监听安装有 12 秒观察边界。重连间隔为 1、3、10、30、60 秒，上限后保持 60 秒。首次授权或组件缺失直接使用 60 秒间隔，避免反复打扰。就绪时只有至多每 60 秒一次节点健康检查；最近持续接收数据时跳过检查，没有高频空转、扫描或空闲 WakeLock。

SDK 消息回调最多排队 16 条，每条不超过 4096 字节；确认消息最多排队 8 条，另有一条在途。旧连接的回调或存储完成不会给新连接发送确认。SDK 发送成功仅代表传输提交；录音的 durable 确认由 ArchiveStore 的落盘与目录同步完成后生成。中断后可从已持久化偏移续传。

WakeLock 仅接收文件时限时持有。播放期间按需申请音频焦点；没有手机麦克风权限。手表原音不会自动删除。

## 构建

按 build-config.example.json 配置本地 JDK、Android SDK 和获授权的 Xiaomi xms-wearable-1.4.jar。外部 SDK JAR、签名密钥及私有构建路径不进入源码包。APK 会包含编译后的 SDK；发布前需自行核对其分发条款。

```powershell
python -X utf8 build.py
python -X utf8 tests/run_fitness_host.py
python -X utf8 tests/run_receiver_host.py
python -X utf8 tests/run_restore_host.py
python -X utf8 tests/run_storage.py
python -X utf8 tests/run_protocol.py
python -X utf8 tests/verify_package.py
```

使用本项目签名更新既有 com.watch6.recorder，原有录音与 storage_id 保留。不要用旧 VoiceSpace 的签名或私有服务配置。

`verify_package.py` 必须核对本次构建报告、实际 APK 的 apksigner 签名，以及身份 RPK 中的公开证书、内容和源码摘要；干净源码构建不依赖历史安装包或报告。本地存在 0.2/0.3.1 签名报告时，会额外比较历史证书，并在 `historical_upgrade.versions_checked` 列出已比对版本；不存在时明确输出 `not_checked_no_historical_reports`，表示未检查历史升级兼容性。证书比对不等于已完成真机升级测试。

身份 RPK 先在 `watch-identity` 运行构建，再构建手机 APK。设置 `W6R_AIOT_TOOLKIT` 为获授权的 aiot-toolkit 目录，运行 `node build.cjs`；签名默认使用本项目 `watch-identity/sign/release`，可通过 `W6R_RPK_SIGNER` 指定本项目签名目录。每次使用独立构建目录并验证新产物、公开证书和输入摘要。手机构建会核对并复制同证书的身份 RPK 到 `artifacts/Watch6-Recorder-Identity-0.5.0.rpk`。0.2 身份包仅为历史记录，不能覆盖已安装的 versionCode 4 验证包。

## 诊断

「连接帮助 → 保存连接诊断」写入 Download/Watch6Recorder。只包含连接阶段、错误码、队列和计时，不含设备标识、录音、识别内容或密钥。SDK 回调模拟、存储故障注入和 APK 检查不能替代真实手机/手表的后台连接和回听验收。

本版修复 Android 拒绝硬链接导致的最终保存失败。最终 WAV 通过发布锁和原子重命名提交；已收齐的文件可在手机直接「完成保存」。通信身份继续使用 0.5.0，版本独立于手机补丁版本。
