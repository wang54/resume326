# AI 智能简历分析系统

## 项目简介

这是一个在 24 小时极限挑战窗口内完成的 AI 赋能简历分析系统，目标是用尽可能短的交付周期，完成一个具备真实业务闭环的全栈作品：前端可直接上传 PDF 简历、输入岗位描述，后端完成文本提取、调用大模型进行结构化分析，并返回可视化匹配结果。

项目不仅追求“能跑通”，更强调工程表达力。最终交付覆盖了接口设计、前后端联调、缓存机制、阿里云 FC3 Serverless 部署配置，以及面向评审场景的可读性和可维护性。

## 技术栈选型

- 后端：FastAPI
- 前端：Vue 3 + Tailwind CSS（CDN 零构建，极速开发）
- PDF 解析：pdfplumber
- 大模型接入：OpenAI Python SDK
- 部署形态：阿里云函数计算 FC3（Serverless）

## 核心亮点

### 1. AI 驱动的全栈开发范式

项目深度应用 Vibecoding 理念，将大模型真正纳入工程生产流程，而不是仅停留在“辅助写几段代码”的层面。实现过程中，大模型被用于：

- 架构拆解与模块分层
- FastAPI 接口与异常处理骨架生成
- 前端单文件联调页面的快速搭建
- Prompt 设计与结构化 JSON 输出约束
- README 与交付材料的工程化整理

这体现的不是单点编码能力，而是借助 AI 快速推进系统设计、实现与迭代的完整能力。

### 2. 面向性能优化的缓存机制

后端实现了基于 MD5 摘要的内存缓存策略：

- 对上传 PDF 文件字节流计算 MD5
- 对岗位描述文本计算 MD5
- 将两者拼接为缓存 Key
- 命中缓存时直接返回结果，避免重复解析 PDF 与重复调用大模型

这在本地演示和单实例服务场景下能显著提升响应效率，并降低大模型调用成本。

### 3. 主动讨论 Serverless 场景下的缓存边界

项目没有停留在“缓存已经做完”的表面，而是进一步讨论了其在 Serverless 运行环境中的局限：

- 当前缓存属于进程内内存缓存
- 冷启动后缓存会丢失
- 多实例并发时缓存无法天然共享

未来演进方案非常明确：将缓存抽离到 Redis 或其他外部 KV 存储，以获得跨实例共享、高可用和可观测能力。这一部分体现的是架构视野，而不是仅仅满足题目功能。

### 4. 真实可替换的大模型调用链路

系统已经完成从 Mock 版本到真实 LLM 调用版本的切换：

- 使用 OpenAI Python SDK
- 支持 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL` 环境变量配置
- 通过严格 Prompt 约束模型输出固定 JSON 结构
- 对超时、接口异常和 JSON 解析失败进行统一兜底处理

这意味着该项目既适合作为挑战赛作品，也具备向生产原型继续演进的基础。

## 项目结构

```text
.
├── main.py          # FastAPI 后端服务
├── index.html       # 单文件前端联调页面
├── requirements.txt # Python 依赖
├── s.yaml           # 阿里云 FC3 Serverless Devs 配置
└── README.md
```

## 如何本地运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

由于涉及到真实的 LLM API Token，本项目默认未内置 Key。请评审专家在本地启动前，在环境变量或 `main.py` 中填入您自己的 OpenAI API Key。

Windows PowerShell：

```powershell
$env:OPENAI_API_KEY="your_api_key"
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
$env:OPENAI_MODEL="gpt-4.1-mini"
```

macOS / Linux：

```bash
export OPENAI_API_KEY="your_api_key"
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_MODEL="gpt-4.1-mini"
```

说明：

- `OPENAI_API_KEY` 必填
- `OPENAI_BASE_URL` 选填，适用于兼容 OpenAI 协议的代理或网关
- `OPENAI_MODEL` 选填，默认使用 `gpt-4.1-mini`

### 3. 启动后端服务

```bash
uvicorn main:app --reload
```

服务默认启动在：

```text
http://127.0.0.1:8000
```

### 4. 打开前端页面

直接在浏览器打开根目录下的 `index.html` 即可开始联调。

页面会向以下接口发起请求：

```text
http://127.0.0.1:8000/api/analyze
```

## 接口文档

### `POST /api/analyze`

#### 请求方式

`multipart/form-data`

#### 请求参数

- `file`: PDF 简历文件
- `job_description`: 岗位描述文本

#### 成功响应

```json
{
  "code": 0,
  "message": "分析成功",
  "data": {
    "basic_info": {
      "name": "张三",
      "phone": "13800138000",
      "email": "zhangsan@example.com"
    },
    "job_intention": {
      "target_position": "Python 后端开发工程师",
      "target_city": "上海",
      "employment_type": "全职"
    },
    "background": {
      "education": "本科 / 计算机科学与技术",
      "years_of_experience": "3年",
      "core_skills": ["Python", "FastAPI", "MySQL", "Docker"]
    },
    "match_analysis": {
      "score": 85,
      "reason": "候选人与岗位要求整体匹配度较高，技能栈方向一致，具备进入下一轮评估的基础。"
    }
  }
}
```

#### 失败响应

```json
{
  "code": 400,
  "message": "仅支持上传 .pdf 文件。",
  "data": null
}
```

## Serverless 部署说明

项目根目录已经提供 `s.yaml`，可用于阿里云 FC3 场景下的 Serverless Devs 部署。当前入口配置为：

```yaml
handler: main.app
runtime: python3.10
```

这使得本项目既能本地快速演示，也能进一步扩展到云端托管场景。

## 总结

这个项目的价值不只在于“完成了一道题”，而在于展示了以下能力组合：

- 极短时间内完成可运行的端到端产品原型
- 借助 AI 提升全栈交付效率
- 在实现功能的同时兼顾接口设计、异常处理、缓存优化和部署形态
- 能够主动识别方案边界，并提出合理的下一阶段架构演进路径

对于面试评审而言，这比单纯展示一段后端代码，更能体现候选人的工程成熟度与落地能力。
