# SmartBench v0.6

**通用 AI 代码诊断平台** — 任意语言、任意框架、任意项目，即开即用。**零幻觉保障。**

---

## 📺 演示视频

> 🎬 **SmartBench 实战演示 — 点击下方观看完整操作流程**

<div align="center">
  <a href="https://xianyu-sheng.github.io/SmartBench/demo.mp4" target="_blank">
    <img src="https://img.shields.io/badge/🎬-观看演示视频-ff6600?style=for-the-badge&logo=vimeo&logoColor=white&labelColor=333333" alt="观看演示视频">
  </a>
  <br>
  <em>点击上方按钮观看 SmartBench 完整操作演示</em>
</div>

<details>
<summary>📹 嵌入式播放（GitHub Pages 支持）</summary>

<video src="https://xianyu-sheng.github.io/SmartBench/demo.mp4" controls width="100%" poster="https://img.shields.io/badge/SmartBench-Demo-orange">
  您的浏览器不支持视频播放，请<a href="https://xianyu-sheng.github.io/SmartBench/demo.mp4">点击下载观看</a>
</video>

</details>

> 💡 如果视频无法播放，请直接访问：https://xianyu-sheng.github.io/SmartBench/demo.mp4

---

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Demo](https://img.shields.io/badge/demo-观看演示-ff6600.svg)](https://xianyu-sheng.github.io/SmartBench/demo.mp4)

---

## 项目简介

SmartBench 是一款**通用代码智能诊断平台**。它利用 LLM 驱动的多 Agent 辩论引擎，
对任意代码仓库进行深度分析。无论是 Python CLI 工具、Go 微服务、Rust 库还是 Java 单体应用 —
只需指向项目路径，SmartBench 自动识别语言和框架，构建代码图，产出可落地的诊断报告。

**核心原则**：SmartBench 只分析、只建议，**绝不修改**被测项目的任何代码。

### 五阶段诊断流水线（v0.6 增强版）

```
$ smartbench
  │
  ├─ 阶段 1 ─ 项目指纹采集（零 LLM 调用）
  │   确定性扫描文件系统，检测语言、框架、项目类型、构建系统、依赖关系。
  │
  ├─ 阶段 2 ─ LLM 项目理解（可选）
  │   LLM 阅读 README.md + 指纹信息，理解项目用途和领域。
  │
  ├─ 阶段 3 ─ 诊断策略选择
  │   LLM 从已验证的策略模板库中选择最优策略。
  │
  ├─ 阶段 4 ─ 代码图构建 + RAG 向量索引
  │   构建调用图 + 依赖图，同时建立代码语义向量索引。
  │   支持三级嵌入后端：sentence-transformers → s
  │
  ├─ 阶段 5 ─ 多 Agent 辩论 + 诊断报告生成
  │   多个 Agent 独立分析，辩论后产出诊断报告。
```

---

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/xianyu-sheng/SmartBench.git
cd SmartBench

# 安装依赖
pip install -r requirements.txt

# 运行诊断
python start.py /path/to/your/project
```

---

## 技术栈

- **Python 3.10+** — 核心语言
- **LLM 驱动** — 多 Agent 辩论引擎
- **ChromaDB** — 向量存储与语义检索
- **sentence-transformers** — 代码语义嵌入

---

## License

MIT © 2025 xianyu-sheng
