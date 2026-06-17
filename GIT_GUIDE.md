# Git 上传到 main/master 指南（给不熟 Git 的同学）

本仓库当前使用的主分支名是 **`main`**（不是 `master`）。如果你口头说“上传到 master”，在这个仓库里等价于“上传到 `origin/main`”。

---

## 你现在这个仓库的最短上传步骤（照抄即可）

在仓库目录下执行（你现在在 `MySensorTools/`）：

```bash
# 1) 看看当前有哪些改动
git status

# 2) 选择要纳入版本管理（track）的文件/目录
#    你目前是 3 个未跟踪项（untracked）：
git add imu/imu_reg_tools infrared/ir_qr_bench infrared/raw_tools/README.md

# 3) 再确认一次：哪些将要提交
git status

# 4) 生成一次提交（commit）。-m 后面写这次改动的目的（不是流水账）
git commit -m "Add IMU register tools and IR QR bench docs"

# 5) 推到远端主分支（origin/main）
git push origin main
```

如果第 5 步报错提示需要设置 upstream，也可以用：

```bash
git push -u origin main
```

---

## Git 你需要掌握的 4 个核心概念

- **工作区（Working tree）**：你本地文件夹里“你正在改的内容”。
- **暂存区（Staging area / index）**：你“挑选出来准备提交”的那一批变更（`git add` 放进去）。
- **提交（Commit）**：一次“快照”，带说明文字，形成历史记录（`git commit` 产生）。
- **远端（Remote）**：GitHub 上的仓库副本（这里叫 `origin`），`git push` 把本地提交上传过去。

一句话：**改文件（工作区）→ `git add`（暂存）→ `git commit`（形成记录）→ `git push`（上传远端）**。

---

## 常用查看命令（安全，无副作用）

```bash
git status          # 当前状态（最常用）
git log --oneline   # 提交历史（简洁）
git diff            # 看“未暂存”的差异
git diff --staged   # 看“已暂存”的差异
git remote -v       # 远端地址
git branch -vv      # 分支 + 跟踪关系
```

---

## “我不小心 add 了不该提交的东西”怎么办？

### 1) 只是想撤回暂存（文件还要保留在本地）

```bash
git restore --staged path/to/file
```

如果你想一次撤回所有暂存：

```bash
git restore --staged .
```

### 2) 误把大文件/数据加进来了（以后也不想再被 git 跟踪）

做两件事：

1) 把它加入 `.gitignore`
2) 如果已经被跟踪了，再执行（只取消跟踪，不删本地文件）：

```bash
git rm -r --cached path/to/file_or_dir
```

然后再正常 `git commit` + `git push`。

> 备注：本仓库已有 `.gitignore`，并且刻意忽略了很多传感器原始数据与产物（如 `*.mcap`, `*.pcd`, `logs/`, `output/` 等）。

---

## “我提交信息写错了 / 漏加文件了”怎么办？

### 1) 你还没 push 到远端（推荐做法）

```bash
# 先把漏掉的文件 add 进去（如果有）
git add <files>

# 然后用 amend 把它合并进上一次 commit，并重写提交信息
git commit --amend
```

### 2) 你已经 push 了（谨慎）

如果已经 push，改历史需要强推（force push），容易影响同事协作。
这类情况更安全的做法通常是：**再补一个新的 commit**：

```bash
git add <files>
git commit -m "Fix: <what & why>"
git push
```

---

## 分支与 PR（可选，但更安全）

当你不确定这次改动会不会影响别人，或者想让改动先审一下，再合入 `main`：

```bash
git checkout -b feat/imu-tools
git add ...
git commit -m "..."
git push -u origin feat/imu-tools
```

然后去 GitHub 上创建 Pull Request，把 `feat/imu-tools` 合并进 `main`。

---

## 常见报错速查

### 1) “nothing to commit”

说明你没有把改动放进暂存区，或者文件根本没变。
先 `git status` 看看是否需要 `git add`。

### 2) “rejected… non-fast-forward”

说明远端 `main` 比你本地更新（别人先 push 了）。

```bash
git pull --rebase
git push
```

如果出现冲突（conflict），按提示逐个解决文件冲突后：

```bash
git add <resolved_files>
git rebase --continue
git push
```

---

## 推荐习惯（让你少踩坑）

- **每次操作先 `git status`**：它基本会告诉你下一步该做什么。
- **commit 信息写“为什么”**：例如 “Add imu_diag tools for field debug”，不要只写 “update files”。
- **大文件/原始数据不要提交**：这个仓库的 `.gitignore` 已经帮你做了很多防护，但你也要留意 `git status` 里有没有意外的大文件。

