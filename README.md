# 百变小樱每日自动签到

纯 Python HTTP 脚本 + GitHub Actions。每天北京时间 **09:00** 自动执行，也可点击 **Run workflow** 手动签到。无需 Codex、浏览器、服务器或本地电脑开机，Python 3.10+ 标准库即可运行，无第三方依赖。

## 1. 上传到 GitHub

建议创建一个空的私有仓库，例如 `bbxy-checkin`。解压交付的 ZIP 后，在本文件所在目录打开 PowerShell：

```powershell
git init -b main
git add .
git commit -m "Add BBXY daily check-in workflow"
git remote add origin https://github.com/你的用户名/bbxy-checkin.git
git push -u origin main
```

如果文件夹已经初始化了 Git，跳过 `git init`。首次推送按 Git 提示完成 GitHub 认证。

也可用 GitHub Desktop 的 Add local repository / Publish repository 上传。必须保留 `.github/workflows/checkin.yml`，并让 `checkin.py` 和本 README 直接位于仓库根目录；不要上传 ZIP 本身，也不要多套一层 `bbxy-checkin/`。ZIP 包含隐藏的 `.github` 文件夹，命令行上传能避免遗漏。

## 2. 配置两个 Secrets

仓库 **Settings → Secrets and variables → Actions → New repository secret**：

| Secret 名称 | 值 |
| --- | --- |
| `BBXY_EMAIL` | 你在百变小樱注册的邮箱 |
| `BBXY_PASSWORD` | 对应的网站登录密码 |

名称必须完全一致。使用 **Secrets** 标签，不是 Variables。不需要添加 GitHub PAT、Cookie、OpenAI Key 或邮箱授权码。凭据只通过运行环境传给脚本，不写进源码或结果文件。

## 3. 手动验收

1. 打开仓库 **Actions**，如有启用提示先启用工作流。
2. 选择 **BBXY Daily Check-in → Run workflow → main → Run workflow**。
3. 运行完成后打开该次运行的 **Summary**：会显示北京时间、签到结果和可识别的本次奖励流量。
4. 当天已签到会显示“今日已签到”，属于成功，不会再次提交。失败显示红色，具体原因见运行日志。
5. 可下载该次运行的 `bbxy-result-...` artifact，其中 `result.json` 只包含状态、固定结果说明、奖励和北京时间，保留 14 天。

手动执行会真的签到，无需额外开关。首次云端运行成功后，再停用原来 Codex 的每日签到任务，避免两个系统同时执行；本地交付不会替你删除原任务。

## 4. GitHub 自带邮件反馈

打开 GitHub 头像 **Settings → Notifications → System → Actions**，开启 **Email**。如果希望成功和失败都收到邮件，关闭 **Only notify for failed workflows**（界面名称可能随 GitHub 更新）。确认通知邮箱已验证并正确配置。

- 手动运行：GitHub 向触发该次运行的用户发送结果通知。
- 定时运行：GitHub 向最初创建工作流或最后修改 cron 表达式的用户发送通知。用你自己的账号创建和上传即可。
- 邮件由 GitHub 发送，不需要脚本连接 SMTP；正文由 GitHub 决定，详细奖励看运行 Summary。本项目不能保证 GitHub 邮件投递时效。
- 默认设置若只通知失败，成功签到不会发邮件，务必检查上述选项。
- 如果 GitHub 根本没触发工作流，该次也没有运行结果邮件。

官方说明：[Notifications for workflow runs](https://docs.github.com/en/actions/monitoring-and-troubleshooting-workflows/notifications-for-workflow-runs)。

## 5. 定时规则与运行限制

`.github/workflows/checkin.yml` 中 `0 1 * * *` 是 **UTC 01:00 = 北京时间 09:00**。修改时间后提交到默认分支即可。

GitHub 定时运行是尽力调度，可能延迟，尤其在整点；不保证精确到分钟。需要降低整点拥堵可改成 `7 1 * * *`，即北京时间 09:07。计划任务只在默认分支运行，工作流需要先存在于默认分支。公开仓库长期无活动可能被停用定时执行；私有仓库受账号 Actions 分钟额度等限制。工作流无需仓库写权限。

## 6. 本地运行（可选）

安装 Python 3.10+ 后，在项目目录执行：

```powershell
$env:BBXY_EMAIL = Read-Host '网站邮箱'
$credential = Get-Credential -UserName $env:BBXY_EMAIL -Message '请输入百变小樱密码'
$env:BBXY_PASSWORD = $credential.GetNetworkCredential().Password
python checkin.py
Remove-Item Env:BBXY_EMAIL, Env:BBXY_PASSWORD
```

脚本不自动加载 `.env` 文件。离线测试无需账号：

```powershell
python -m unittest discover -s tests -v
```

## 实现与验证范围

1. GET `/v2/login` 获取页面、隐藏字段与 Cookie。
2. POST `/v2/login` 提交 `email`、`passwd` 和空二步验证字段，使用 CookieJar 保持会话。
3. GET `/user` 验证登录状态；根据 `studio-checkin` 按钮判断当天是否已签到。网站已签到时可能没有 `id="checkin"`。
4. 尚未签到则 POST `/user/checkin`，随后重新 GET `/user` 确认“今日已签到”。接口返回成功但页面未确认仍视为失败。
5. 网络超时、429 和临时服务器错误最多尝试 3 次。登录失败、验证码、非 JSON、页面变化均返回非零退出码，使 GitHub Actions 报红。账号启用二步验证或网站开启验证码时需人工处理，不绕过验证。

已参考用户提供的 `csu-checkin` Actions 示例，沿用定时/手动触发、最小权限、并发控制、离线测试等结构。该范本使用 QQ SMTP；本项目按要求使用 GitHub 原生通知。

2026-10-30 已用真实账号在全新 Python CookieJar 中验证账号密码登录和“今日已签到”识别，也直接验证了 POST 签到端点返回当天已签到（`ret: 0`），随后页面再次确认已签到。签到端点及字段来自实际网站请求与前端脚本。此前浏览器实际签到成功；本次开发时当天已签到，因此 Python 新增流量的路径由离线测试覆盖，尚未在 GitHub runner 上执行。上传后按第 3 节手动验收，验证 GitHub 出口网络的实际连通性。不会把本地成功等同于云端已验证。
