# 刷题软件（题库 + 错题本 + 模拟考试）

一个本地运行的刷题工具：终端版（CLI）与网页版共用同一份数据，题库以 JSON 文件存放，可直接编辑、批量导入、导出存档。

- 终端版：`python launcher.py`（或 `start.bat`）
- 网页版：`python launcher.py web`（或 `start_webui.bat`），默认 http://127.0.0.1:8000

## 题目存储格式（v2）

六种题型：**单选题、多选题、判断题、填空题、简答题、计算题**，每题一个 JSON 对象：

- 公共字段：`type / text / answer / images / subject / flag_star / flag_cross`
- 单选/多选另有 `options`（`[["A","文本"],…]`）；判断题固定 正确/错误，无选项；
- 图片以内嵌文件名显示（题干或选项文本里写 `1.png`），`images` 自动汇总；
- 填空题题干用 `【1】【2】…` 标记空位，答案结构：
  `answer.items[i].accept` = 第 i 空可接受答案列表（命中任一即对），
  `accept` 相同的 `group` 编号的空位**可任意互换顺序**；
  无法可靠拆分的旧题会标记 `whole: true`（整串比对，逐题录入编辑器可直接编辑）；
- 简答题不自动判分（作答后展示参考答案、用户自评）；计算题严格判分（双方为数字时按容差）。

迁移工具：`python migrate_questions.py --dry-run`（试运行）/ `python migrate_questions.py`（先备份再迁移）。
自检：`python question_v2_selftest.py`。

## 目录结构

```
data/              题库数据（每科一个 JSON：C语言.json、Python.json …）＋本地个人记录
pictures/          题目图片（按科目子目录 pictures/<科目>/；共用图在 _shared/）
webui/             网页版前端（含 manifest/图标，可“添加到主屏幕”）
android/           Android APK 工程 + 构建脚本（Chaquopy 17 + WebView，详见 android/README.md）
models/  utils/    题目模型与工具（utils/paths.py = 统一路径层，支持 SHUATI_HOME）
convert_tools/     批量导入用的文本转换脚本（judge 系列）
tools/             构建期工具（make_icons.py 生成 PWA/Android 图标）
backups/           存档 / 题库更新前自动备份（自动生成）
reports/           刷题报告（自动生成）
sync_bank.py       题库远程同步器（连接 GitHub，下载/更新题库）
reorganize_pictures.py  图片按科目归类整理 + 题目↔图片一一对应检查
data_manifest.json 题库同步清单（维护者推送题库时自动生成）
*_selftest.py      离线自检：模型/判分、convert_tools、题库同步、路径层、服务端、Android 工程、前端交互
```

## 手机版（Android APK）

把同一套 Python 后端（`webui_server.py`）与网页界面打进一个 APK：**安装即用、完全离线**，
个人数据保存在应用私有目录，联网时可在应用内一键更新题库。业务代码只有一份 —— Android 只是外壳，
构建时由脚本把运行时文件与题库种子生成到工程内（`android/README.md` 有完整说明）。

构建（一次性安装 JDK 17 + Android SDK + Python 3.14，下载清单见 android/README.md）：

```bat
android\build_apk.bat                      :: 双击即可（debug APK）
:: 或： android\build_apk.bat -Task assembleRelease   （需先配置签名）
```

产物在 `dist/shuati-<版本>-debug.apk`，用数据线 `adb install -r` 或把文件传到手机点击安装。

与桌面版的关系：

- **代码/题库同源**：APK 内代码与题库来自本仓库，不存在第二套逻辑；
- **数据各自独立**：桌面数据在项目目录，手机数据在应用私有目录（Python 侧 `SHUATI_HOME`），互不覆盖；
- **更新节奏**：题库内容更新走应用内「检查更新/立即更新」（不必重装 APK）；代码/前端更新需重新构建并覆盖安装；
- **首启种子只补缺失文件**：升级 APK 不会覆盖你的题目与错题本/记录/进度；
- 桌面端行为不变：不设置 `SHUATI_HOME` 时所有路径与历史完全一致（可跑 `python paths_selftest.py` 验证）。


图片整理与检查：
```bash
python reorganize_pictures.py --dry-run   # 预览分类/修复/搬移计划
python reorganize_pictures.py             # 备份→按科目搬移→重写引用→报告
python reorganize_pictures.py --check     # 校验每题引用图片都能找到
```
说明：题目里的图片引用是**相对 pictures/ 的相对路径**（如 `数据结构/3.png`，共用图 `_shared/x.png`）；逐题/批量导入的“插入图片”会按当前科目自动归入 `pictures/<科目>/`。

> `data/records.json、wrong_book.json、recycle_bin.json、exams.json、brush_progress.json`
> 是**你自己的使用数据**，已被 `.gitignore` 排除，不会上传 GitHub，也不会被远程更新覆盖。

## 题库远程更新（GitHub）

本项目把「程序 + 题库 + 图片」都发布在 GitHub 仓库。使用者拿到项目后可以随时**远程下载/更新题库**，无需懂 git：

- 网页版：设置 → **题库更新（远程 GitHub）** → 检查更新 / 立即更新
- 终端版：主菜单选 **7. 更新题库（从远程 GitHub 同步）**
- 命令行：`python sync_bank.py check` / `python sync_bank.py update`

详细流程（维护者发布、使用者下载更新、常见问题）见 **《接入GitHub完整流程.md》**。

### 国内网络：把题库镜像到 Gitee（不用代理也能更新）

GitHub 在国内经常连不上（`raw.githubusercontent.com` 基本不可达，jsDelivr 时通时断）。
推荐**再加一个 Gitee 镜像仓库**，让更新优先走国内直连：

```bash
# 1) 在 Gitee 新建一个仓库（public），例如 gitee.com/你的名字/shuati

# 2) 把数据推过去（data/ 题库 + pictures/ 图片 + 清单，代码是否镜像随你）
git remote add gitee https://gitee.com/你的名字/shuati.git
git push gitee main

# 3) 在项目根目录写 bank_remote.json，声明镜像地址
python sync_bank.py setup <GitHub用户名> shuati --gitee-owner <Gitee用户名>
```

生成的 `bank_remote.json`：

```json
{
  "owner": "GitHub用户名", "repo": "shuati", "branch": "main",
  "gitee": {"owner": "Gitee用户名", "repo": "shuati", "branch": "main"}
}
```

之后 `检查更新` 会按 **gitee → jsDelivr → raw.githubusercontent** 的顺序尝试，任意一个可用即可
（`python sync_bank.py info` 会显示当前源）。没配 `gitee` 时不会去请求它，不会白白多 404。
维护者把这个 `bank_remote.json` 提交到仓库，则桌面版 zip 用户和 Android 随包种子都会自动带上该镜像配置。

## 刷题数据说明（来自 README.txt，开发者备忘）

- 刷题与错题本功能可用；暂无“清空错题本”的独立按钮（终端菜单/设置页可清空记录）。
- “导入题目”只充分测试了判断/单选/多选；“编辑题目”待优化；查询删除会连带删除同文本题目；缺少题目查重（有 duplicate_finder.py 雏形）。
- text.txt / text_converted.txt 在 convert_tools/ 内，是给 convert 系列脚本改格式用的中间文件。
