# 来源与许可范围

本项目采用 MIT 的范围是维护者有权授权的独立录音代码及文档；不对外部软件、固件、协议、商标或专利作出授权承诺。MIT 正文见根目录 LICENSE。

## 提取与新实现

连续采音、文件分段、原生后台拥有者和 Lua 状态读取部分来自 VoiceSpace 项目中维护的 `watch-native/continuous-native` 与 `meeting-source.lua`。本次拆分加入独立的文件目录、控制流程、录音清单和主机导出工具，去掉录音结束等待手机/转写的依赖。具体提取前后哈希和修改记录见 `SOURCE_PROVENANCE.json`。

此独立项目不使用旧的 `native-recorder-v017/recorder.c`、`native-launcher-v017/launcher.c`、GUI attach 或旧 SDK 导入脚本。旧 VoiceSpace 的源码许可证和外部来源审查不因本项目 MIT 选择而自动改变。

## 没有随源码分发的材料

| 材料 | 处理方式 |
|---|---|
| 小米商用 AP/audio 固件、资源分区、反汇编转储 | 构建者自行合法取得，不随源码包分发 |
| 厂商 SDK/JAR/AAR、签名私钥、设备身份/配对数据 | 不收入本项目公开包 |
| `Mi8WfBinTool.java` / Android_Source / WfWriter 来源链尚待核实的表盘打包器 | 作为外部构建输入，不收入 MIT 源码包；不得仅靠改名改成 MIT |
| 编译器、Python 库、Lua、Unicorn、LVGL、NuttX 等外部环境 | 各自许可继续适用；本项目不重新授予其许可 |

原生适配中的函数地址、结构参数和指纹用于精确兼容性校验；没有捆绑商用固件实现本体。仅有地址/指纹并不能独立证明全部来源、使用与发布权限已经获得。

open-vela 的公开媒体接口可作为研究资料，其文件中的许可声明应逐项遵守；公开接口资料的许可不等于商用固件镜像、厂商 SDK 或特定装载方式的授权。[open-vela 媒体接口](https://github.com/open-vela/frameworks_multimedia_media/blob/dev/include/media_recorder.h)

如后续加入外部源码，提交者需保留真实版权声明和许可，将来源、版本、修改及再分发条件加入记录。不要用根目录 MIT 声明覆盖许可未知或不兼容的代码。

## 预编译安装包

GitHub Release 另提供表盘 BIN、Android APK 和通信身份 RPK。APK 含已集成的小米穿戴通信 SDK 运行代码；这部分第三方代码不因本项目采用 MIT 而改为 MIT，相关权利和使用条件仍归其提供方。安装合集不包含可单独使用的厂商 SDK JAR/AAR、表盘打包器、固件镜像、签名私钥或个人录音。

发布包中的公开签名证书用于校验 APK 与 RPK 的配套关系，不是签名私钥。自建时应使用自己的匹配签名；请保留本文件和项目 LICENSE。
