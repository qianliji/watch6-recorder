# 开源与发布步骤

## 当前准备方式

独立录音项目自己的代码采用用户选定的 MIT 许可。源代码候选与可运行候选分开；固件、SDK、外部打包器、个人配置、签名和录音不进入公开源码。

**源码准备完成不等于所有外部权利问题或真实设备验收已经完成。** 录音功能是正常功能；源码来源、模块装载是否涉及受保护技术措施、具体设备协议和第三方再分发条件仍需分别核对。有关实现与权利的审查记录应与本项目一同保留。

## 公开仓库基础内容

- README：三分钟能看懂用途、精确兼容范围、功能状态和已知限制。
- LICENSE、NOTICE、SOURCE_PROVENANCE：MIT 仅覆盖有权授权的代码；外部材料各自处理。
- BUILDING：完整依赖、合法外部输入、构建命令、输出与失败诊断。
- FEATURES、COMPATIBILITY：首版功能、实机验收与支持矩阵，不用“全版本解锁”营销。
- 自动测试、CI、issue 模板、贡献和安全说明；故障反馈不要求用户上传真实录音。

## 建议分两次发布

1. **开发者预览。** 先发布经过来源与隐私核对的源码；说明没有捆绑固件/打包器，表盘录音、完整回听与运动健康导出已有候选实现，但没有把模拟结果写成真机通过。当前组合为表盘 0.5.3、手机 0.5.1、连接组件 0.5.0，采用表盘＋连接身份方案：离线使用只需表盘 BIN；无线导出另需手机 APK、匹配签名的连接身份 RPK 和运动健康授权。连接身份一次安装，日常不必打开。代码和安装包已具备不代表真实硬件验收已经完成。失败的单 RPK 录音验证与独立 BLE 实验不进入本版源码及安装包。
2. **普通用户版本。** 补齐录音完整取出、校验与回放，完成兼容设备的完整实机清单，并核实模块装载方式和适用协议的公开分发边界后，再提供面向普通用户的安装包。

建立仓库时只从经过检查的独立源码 ZIP 开始，不要对原工作目录直接 `git add .`。保留发布清单与 SHA-256；标签对应已测试的源码，附件对应同一源码构建。不要上传私人构建文件、原始固件、ELF 调试转储、第三方未授权工具或个人设备证据。

当前没有自动创建或推送公开仓库，也没有代表项目取得小米授权。面向大规模公开分发或商业化前，建议让熟悉中国软件著作权与反规避规则的律师，结合具体固件、适用条款和发布物复核；通用免责声明不能替代这一步。


## 上传当前源码包

1. 使用 `Watch6-Recorder-OpenSource-0.5.3.zip`，解压后进入含 README、LICENSE、src 与 phone-app 的项目目录。
2. 在 GitHub 或 Gitee 新建空仓库，例如 `watch6-recorder`。上传解压后的文件，保留 `.github`、`.gitignore`、LICENSE、NOTICE 与来源清单；不要只把 ZIP 本身当成仓库内容上传。
3. 仓库简介可写：`REDMI Watch 6 离线录音、完整回听与手机无线导出。` 仓库标签可使用 `watch6`、`recorder`、`android`、`lua`、`open-vela`。
4. 首次提交后查看 CI 结果。工作流提供 ARM/主机检查；手机构建需要自行配置外部 SDK 与签名，不能把这些私密或外部材料直接提交。
5. 发布标签可用 `v0.5.3`，说明对应手机 App 0.5.1、通信组件 0.5.0。说明实际测试范围；安装附件与源码分开管理，核对每个附件的来源和分发条件。

提交前的本机命令示例：

```sh
git init
git add README.md LICENSE NOTICE.md .gitignore BUILDING.md CONTRIBUTING.md SECURITY.md SOURCE_PROVENANCE.json build.py build_settings.py build-config.example.json requirements*.txt .github src native adapters assets docs tests tools phone-app
git status --short
git commit -m "Initial source release v0.5.3"
git branch -M main
```

确认 `git status` 中没有本机配置、密钥、录音或外部固件后，再添加自己的仓库地址并推送。不要从原来的混合工作目录创建首个公开提交。此说明不会自动创建仓库或上传文件。

CI 使用第一方 [actions/checkout](https://github.com/actions/checkout) 与 [actions/setup-python](https://github.com/actions/setup-python)，固定到本次核对的提交；后续升级应重新核对上游来源。
