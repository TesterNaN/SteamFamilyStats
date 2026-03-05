# Steam Family Library Contribution Analyzer

Steam家庭库贡献统计工具  
一个自动登录 Steam、获取家庭共享库并统计成员贡献度的 Python 脚本。

## 简介

本项目通过模拟浏览器登录 Steam，获取用户的家庭组信息及家庭共享库游戏列表，统计每位家庭成员贡献的游戏数量，并生成排名和可视化图表。支持使用已保存的登录信息自动登录，避免重复输入凭证。

## 功能特性

- 🔐 **账密登录**：使用账号密码登录以获取数据（不需要 Steam API key）
- 🍪 **登录持久化**：登录成功后保存登录信息，下次运行时自动登录
- 👨‍👩‍👧‍👦 **家庭组识别**：自动获取当前用户所在的家庭组详细数据
- 📊 **游戏贡献统计**：统计家庭共享库中每个成员拥有的游戏数量（排除被排除的游戏）
- 📈 **可视化输出**：
  - 贡献值柱状图（显示数量及百分比）
  - 贡献占比饼图（仅显示有贡献的成员）
- 📝 **排名导出**：将贡献排名保存为 JSON 文件

## 技术亮点

- **基于 Steam 新版 protobuf API 完整实现登录流程**  
  目前公开的 Steam 数据获取方案大多基于 Steam 官方 API，本项目完整实现了 Steam 最新的 protobuf 认证协议，包括：
  - RSA 公钥获取与本地加密
  - 发送设备确认请求
  - 验证码（邮件/令牌）提交
  - 会话轮询与最终登录分发
- **模拟浏览器 TLS 指纹**  
  使用 `curl_cffi` 库模拟 Chrome 浏览器的 TLS 握手特征，有效降低被 Steam 识别为自动化脚本的风险。
- **可能是全网首个开源的、完整支持新版 Steam 登录的 Python 实现**。
- **protobuf 定义来源**：感谢 [SteamDatabase/Protobufs](https://github.com/SteamDatabase/Protobufs) 提供的 protobuf 定义文件，大大提高了登录流程的逆向效率，让本项目能够直接使用现成的 proto 文件。
- **Cookie 自动刷新功能正在开发中**  
  当前版本仅在登录时保存 Cookie，暂不支持在运行过程中自动刷新过期的 access_token。此功能已在规划中，敬请期待。

## 环境要求

- Python 3.8 或更高版本
- 依赖库（见 `requirements.txt`）

## 安装步骤

1. **克隆或下载本项目**  
   确保以下文件均在同一个目录中：
   - `steam_family_contrib.py` （主脚本）
   - `authentication_pb2.py` （Steam 认证 API 的 protobuf 定义编译文件）
   - `familygroups_pb2.py` （Steam 家庭组 API 的 protobuf 定义编译文件）
   - `requirements.txt` （依赖列表）

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

## 使用方法

1. **运行脚本**
   ```bash
   python steam_family_contrib.py
   ```

2. **登录流程**
   - 如果存在有效的登录信息，脚本会自动加载并跳过登录。
   - 否则，输入 Steam 账号和密码。
   - 根据提示输入验证码类型（2=邮件验证码，3=令牌验证码）和验证码内容。
   - 如果触发设备确认，脚本会自动发送确认请求。

3. **结果输出**
   - 终端打印家庭成员昵称和贡献排名。
   - 生成 `contribution_rank.json` 文件。
   - 显示并保存柱状图 `contribution_bar.png` 和饼图 `contribution_pie.png`。

## 注意事项

- 🧪 **依赖库**：确保已安装 `curl_cffi`、`cryptography`、`beautifulsoup4`、`matplotlib`、`pwinput`。
- 🔑 **登录信息存储**：`store_cookie.txt` 文件包含你的登录凭证，请勿分享给他人。
- 🚫 **限流处理**：脚本遇到 HTTP 429 或 `X-eresult: 84` 时会自动等待并重试。
- 📋 **协议同意**：如果登录过程中需要同意新的 Steam 协议，脚本会输出链接并等待用户手动完成后继续。
- 🌐 **网络连接**：如果因为网络环境连接不上 Steam 服务器，请使用 Watt Toolkit 或 Steamcommunity 302 加速 Steam。

## 许可证

本项目仅供学习交流使用，请遵守 Steam 用户协议。  
MIT License

---

**Steam Family Library Contribution Analyzer**  
帮助家庭组管理员轻松了解每位成员的贡献度！