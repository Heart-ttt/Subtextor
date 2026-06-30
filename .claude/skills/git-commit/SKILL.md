---
name: git-commit
description: 按《Git 提交信息规范》撰写或校正 Git commit message。当用户说「写 commit」「帮我写提交信息」「生成 commit message」「检查这条提交信息是否规范」时使用。可基于已暂存(staged)的改动归纳提交信息。除了<type>一定使用英文，其他默认使用中文写。
---

# Git 提交信息规范 Skill

按本规范撰写或校正 Git commit message。

## 第 0 步：先看改动（建议）

若用户未说明本次改动内容，先运行 `git status` 与 `git diff --staged`（没有暂存内容则看 `git diff`）了解变更，再据此归纳提交信息。**不要替用户执行 `git commit`，除非用户明确要求。**

## 格式

commit message 分 `<header>` 与 `<body>` 两部分，中间空一行隔开；每行建议不超过 72 个字符。

### header（必写）

格式为 `<type>: <subject>`，建议不超过 50 个字符，不换行。
- `<type>` 只能取下列之一：
  - `init`：初始化
  - `feat`：新功能或新内容
  - `fix`：修复错误
  - `docs`：纯文档修改（非研究报告）
  - `update`：优化细节
  - `refactor`：重构、优化格式
  - `test`：增加测试例
  - `draft`：草稿
  - `misc`：辅助工具或其他无法归类的变动
- `<subject>` 以小写动词开头，使用第一人称现在时（祈使语气），结尾不加句号。

### body（可选）

- 与 `<header>` 之间空一行。
- 可用正式语言描述，可分段，支持 Markdown 语法。
- 重点解释「为什么这么改」，而非逐行复述「改了什么」。

## 输出方式

默认直接输出 commit message 文本本身，便于用户复制或粘进编辑器。若用户需要可一并给出命令：
```
git commit -m "<header>" -m "<body>"
```

## 完成后自查

1. `<type>` 属于上述 9 种之一，冒号后恰好一个空格。
2. `<subject>` 小写动词开头、现在时、句尾无句号、不超过 50 个字符。
3. 含 body 时与 header 间恰好空一行，每行不超过 72 个字符。
4. 一次提交只表达一件事；若改动横跨多个不相关主题，提示用户拆分提交。
