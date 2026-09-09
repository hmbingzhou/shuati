# 接入 GitHub · 完整实现流程

> 目标：把「刷题软件 + 题库 + 题目图片」发布到 GitHub 仓库，让每一位使用者都能
> **远程下载题库**，并能在软件里一键**更新题库**（网页版设置页 / 终端版菜单 7 / `python sync_bank.py`）。
>
> 原理一句话：题库文件（`data/*.json` + `pictures/*`）连同清单 `data_manifest.json`
> 一起提交到 GitHub；使用者运行同步器 → 读取远程清单 → 与本地逐文件比对 sha256 →
> 只下载变化文件 → 先备份再覆盖。**全程不需要使用者懂 git。**

---

## 一、仓库里会有什么 / 不会有什么

| 会上传到 GitHub（public）                    | 不会上传（.gitignore 已排除）                    |
| ------------------------------------------- | ------------------------------------------------ |
| 程序代码（*.py、webui/、convert_tools/…）    | `data/records.json` 正确率记录                   |
| `data/*.json` **题库**（每科一个文件）       | `data/wrong_book.json` 错题本                    |
| `pictures/*` 题目图片                        | `data/recycle_bin.json` 回收站                   |
| `data_manifest.json` 题库同步清单            | `data/exams.json`、`data/brush_progress.json`    |
| README.md、同步器代码                        | `reports/` 刷题报告、`backups/` 存档与同步备份    |

⚠️ 公开仓库意味着**任何人在网上都能看到全部题库**。如果题库含个人隐私或不便公开的内容，
请先删除/脱敏，或改用 **private 仓库 + token**（见「五、可选配置」）。

---

## 二、维护者 · 第一次接入（约 10 分钟）

### 第 1 步：在 GitHub 网页上建仓库

1. 登录 https://github.com ，点右上角 **+** → **New repository**。
2. Repository name 填仓库名（例如 `shuati`）。
3. **不要勾选** “Add a README / .gitignore / license”（保持空仓库，避免冲突）。
4. 可见性：Public（免费、无需配置、jsDelivr 加速可用）。点 **Create repository**。
5. 建好后页面会显示仓库地址，两种形式都行：
   - HTTPS：`https://github.com/<你的GitHub用户名>/shuati.git`
   - SSH：`git@github.com:<你的GitHub用户名>/shuati.git`

### 第 2 步：本机初始化 git 并首次提交

在**项目根目录**打开终端（本目录），依次执行：

```bash
git init -b main                # 以 main 为默认分支初始化
git add .
git status                      # ← 先看一眼！确认 records.json/wrong_book.json 等个人文件“没”出现在列表里
git commit -m "初次提交：刷题软件 + 题库"
```

> 若 `git commit` 报 “Please tell me who you are”，先执行：
> ```bash
> git config --global user.name "你的名字"
> git config --global user.email "你的邮箱"
> ```

### 第 3 步：关联远程仓库并推送

```bash
git remote add origin https://github.com/<你的GitHub用户名>/shuati.git
git push -u origin main
```

推送时 GitHub 会要求身份验证（2021 年起**不能用账号密码**，三选一）：

- **方式 A（推荐、最简单）**：安装 [GitHub CLI](https://cli.github.com/) 后执行一次
  `gh auth login`，之后 git push 自动免密；
- 方式 B：网页 → Settings → Developer settings → Personal access tokens → 生成一个
  勾选 `repo` 权限的 token，推送时用户名填你的用户名、密码粘贴 token；
- 方式 C：改用 SSH——[生成 SSH 密钥](https://docs.github.com/zh/authentication/connecting-to-github-with-ssh) 并添加到 GitHub，remote 换成 `git@github.com:<用户名>/shuati.git`。

### 第 4 步：验证

1. 浏览器打开 `https://github.com/<你的GitHub用户名>/shuati`，确认代码、`data/C语言.json`、
   `pictures/1.png`、`data_manifest.json` 都在。
2. 本机运行 `python sync_bank.py info`，应显示你的仓库地址（来源 git-origin）。
3. 运行 `python sync_bank.py check`，应提示“未变 N / 无需更新”（因为本地就是最新）。

✅ 接入完成。现在把仓库地址发给同学即可。

---

## 三、维护者 · 以后每次更新题库

只要按“改了题库/图片 → 重新生成清单 → 提交推送”三步走：

```bash
python sync_bank.py build-manifest    # ① 重新生成 data_manifest.json（含每个文件 sha256）
git add data data_manifest.json pictures
git commit -m "更新题库：新增XX题、修正XX"
git push
```

> 只改了程序代码、没动题库时，可以省略 `build-manifest`（清单没变就不用重新生成）。
> 不放心就每次都生成，幂等、无害。

推送后，使用者在软件里点「检查更新」就能看到新版本并一键下载。
（jsDelivr CDN 有缓存，推送后一般几分钟内生效；想立刻生效可访问
`https://purge.jsdelivr.net/gh/<用户名>/<仓库>@main/data_manifest.json` 手动刷新一次。）

---

## 四、使用者 · 下载与更新题库

### 方式 A：git clone（推荐，之后更新全自动）

1. 下载安装 [Git](https://git-scm.com/download/win)（装好后右键“Git Bash Here”）。
2. 下载项目（自动包含当前最新题库与图片）：
   ```bash
   git clone https://github.com/<你的GitHub用户名>/shuati.git
   ```
3. 进入目录运行 `start.bat` 或 `python launcher.py`，选择网页版或终端版。
4. **以后题库更新**，不用碰 git，直接在软件里：
   - 网页版：设置页 → “题库更新（远程 GitHub）” → **🔍 检查更新** → **⬇️ 立即更新**；
   - 终端版：主菜单 → **7. 更新题库**；
   - 命令行：`python sync_bank.py update`。

   同步器会读取 clone 时写入的 git origin 自动识别仓库地址（配置来源 git-origin），
   无需任何手工配置。

### 方式 B：zip 下载（给不想装 git 的人）

1. GitHub 仓库页面 → **Code → Download ZIP**，解压即用。
2. zip 用户无法自动识别仓库，需先手动配置一次远程仓库，任选其一：
   - 命令行：`python sync_bank.py setup <你的GitHub用户名> shuati`
   - 或：在项目根目录新建 `bank_remote.json`：
     ```json
     { "owner": "<你的GitHub用户名>", "repo": "shuati", "branch": "main" }
     ```
3. 之后照常在软件里“检查更新 / 立即更新”。

> 维护者若想让 zip 用户“零配置”，可以把写好的 `bank_remote.json` 也放进仓库一起发布
> （该文件会被每个 clone 下来的用户直接使用，自动匹配远程，无需再 setup）。

### 更新安全机制（内置，无需操作）

- 先**下载并校验 sha256**，全部成功后才写盘；中途失败不会破坏本地题库；
- 覆盖前自动把旧文件备份到 `backups/sync_backup_时间戳/`（自动保留最近 5 份）；
- 只更新清单里列出的题库/图片文件，**绝不碰**你的错题本、记录、回收站、考试记录；
- 远程“下架”的科目文件：本地没改过会自动删除；本地改过则保留并提示；
- 你自己的本地自建题库（不在远程清单里）永远不会被删除。

---

## 五、可选配置（遇到问题再看）

### 1. 下载源顺序
默认先走 **jsDelivr CDN**（大陆一般可直连），失败自动切 **raw.githubusercontent.com**。
在 `bank_remote.json` 里可调：

```json
{ "owner": "xx", "repo": "shuati", "branch": "main",
  "sources": ["github", "jsdelivr"] }
```

### 2. private 仓库（需要 token）
private 仓库的 raw/CDN 下载需要鉴权。两种做法：
- 简单做法：软件不改，仓库改回 public；
- 需要 private：把仓库地址所在代码改为带 token 的 URL，或在 `sync_bank.py` 顶部给
  `_http_get()` 加 `Authorization: Bearer <token>` 请求头（自行扩展，注意别把 token 提交到仓库）。

### 3. 默认分支不是 main（比如 master）
在 `bank_remote.json` 里把 `branch` 改成实际分支名即可。

### 4. 完全离线/没有 GitHub 时
题库更新会提示“下载失败”，此时可让对方拿「网页版设置 → 数据存档」生成的 zip 手动导入，
或直接拷贝 `data/*.json` 与 `pictures/*`。

---

## 六、常见问题（FAQ）

**Q1：check 提示“还没有配置题库的远程仓库”**
本目录没有 git（zip 安装）也没填 `bank_remote.json`。见“方式 B”第 2 步配置一次。

**Q2：check 提示“下载失败：…jsdelivr… HTTP 404”**
说明你的仓库里还没有 `data_manifest.json`。维护者请先运行 `python sync_bank.py build-manifest`
并把生成的 `data_manifest.json` 提交推送。

**Q3：一直“下载失败 / 超时”**
大陆网络访问 GitHub 不稳。默认会先试 jsDelivr CDN；若两个源都失败，稍后重试，或用代理后把
`sources` 调成 `["github"]`、或换网络再试。仓库必须是 **public**（private 无法走 jsDelivr）。

**Q4：更新后某科题目数量不对？**
题库文件是整体覆盖更新的：如果你之前用“导入题目/编辑题目”改过某个远程科目，
更新会用维护者版本覆盖（旧版本可在 `backups/sync_backup_时间戳/` 找回）。
本地自建科目（远程清单里没有）不受影响。

**Q5：推送时报错 / 身份验证失败**
见“二、第 3 步”的三种身份验证方式；国内访问 GitHub 慢可配置代理后重试。

**Q6：我改了题库，想把这版“发布”给同学们**
按“三、维护者更新流程”提交推送即可；同学们点“检查更新/立即更新”就能拉到。

---

## 七、实现原理速览（给想改代码的人）

| 文件 / 函数                          | 作用                                                        |
| ------------------------------------ | ----------------------------------------------------------- |
| `sync_bank.py`（核心，纯标准库）     | 远程识别 / 清单下载 / sha256 比对 / 断点式安全更新 / CLI    |
| `sync_bank.py build-manifest`        | 扫描 `data/` 与 `pictures/`，生成 `data_manifest.json`      |
| `sync_bank.py check`                 | 拉远程清单 → `build_plan()` 返回 新增/更新/下架/未变        |
| `sync_bank.py update`                | 先下载全部变更并校验 → 备份 → 原子写盘 → 删下架 → 记状态    |
| `_resolve_remote()`                  | 远程仓库识别：bank_remote.json → git origin → 顶部默认值    |
| `.bank_sync_state.json`              | 上次同步结果（本地，已 gitignore），用于“远程下架”检测      |
| `menu.py` 主菜单 7 / `webui_server.py /api/bank/*` / `webui/app.js` 设置页 | 三个入口接入同一套同步逻辑    |

远程清单格式（`data_manifest.json`，位于仓库根目录）：

```json
{
  "format": 1,
  "generated_at": "2026-09-07 20:00:00",
  "files": {
    "data/C语言.json": "sha256…",
    "pictures/1.png": "sha256…",
    "…": "…"
  }
}
```

文件下载地址规则（以 `data/C语言.json` 为例，文件名已做 URL 编码）：
- jsDelivr：`https://cdn.jsdelivr.net/gh/<owner>/<repo>@<branch>/data/C语言.json`
- GitHub：`https://raw.githubusercontent.com/<owner>/<repo>/<branch>/data/C语言.json`
