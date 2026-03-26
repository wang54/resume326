import hashlib
import io
import json
import logging
import os
import re
from typing import Any

import openai
import pdfplumber
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import OpenAI


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
result_cache: dict[str, dict[str, Any]] = {}

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


# 1. 基础与跨域配置
app = FastAPI(title="Resume Analyze Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 2. PDF 解析函数
def extract_text_from_pdf(file_bytes: bytes) -> str:
    if not file_bytes:
        raise ValueError("上传的 PDF 文件为空。")

    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text_parts = [page.extract_text() or "" for page in pdf.pages]
    except Exception as exc:
        raise RuntimeError(f"PDF 解析失败: {exc}") from exc

    raw_text = " ".join(text_parts)
    cleaned_text = re.sub(r"\s+", " ", raw_text).strip()

    if not cleaned_text:
        raise ValueError("PDF 中未提取到有效文本。")

    return cleaned_text


def get_openai_client() -> OpenAI:
    # 请评审专家在此配置您的 API Key，推荐通过环境变量 OPENAI_API_KEY 注入。
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")

    client_kwargs: dict[str, Any] = {"timeout": 60.0}
    if api_key:
        client_kwargs["api_key"] = api_key
    if base_url:
        client_kwargs["base_url"] = base_url

    return OpenAI(**client_kwargs)


def validate_llm_result(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("LLM 返回结果必须是 JSON 对象。")

    required_fields = {"basic_info", "job_intention", "background", "match_analysis"}
    missing_fields = required_fields - set(data.keys())
    if missing_fields:
        raise ValueError(f"LLM 返回缺少字段: {', '.join(sorted(missing_fields))}")

    basic_info = data["basic_info"]
    job_intention = data["job_intention"]
    background = data["background"]
    match_analysis = data["match_analysis"]

    if not isinstance(basic_info, dict):
        raise ValueError("basic_info 必须是对象。")
    if not isinstance(job_intention, dict):
        raise ValueError("job_intention 必须是对象。")
    if not isinstance(background, dict):
        raise ValueError("background 必须是对象。")
    if not isinstance(match_analysis, dict):
        raise ValueError("match_analysis 必须是对象。")

    raw_score = match_analysis.get("score")
    try:
        score = int(raw_score)
    except (TypeError, ValueError) as exc:
        raise ValueError("match_analysis.score 必须是 0-100 的整数。") from exc

    score = max(0, min(100, score))
    reason = str(match_analysis.get("reason", "")).strip()
    if not reason:
        raise ValueError("match_analysis.reason 不能为空。")

    core_skills = background.get("core_skills", [])
    if not isinstance(core_skills, list):
        raise ValueError("background.core_skills 必须是数组。")

    return {
        "basic_info": {
            "name": str(basic_info.get("name", "")).strip(),
            "phone": str(basic_info.get("phone", "")).strip(),
            "email": str(basic_info.get("email", "")).strip(),
        },
        "job_intention": {
            "target_position": str(job_intention.get("target_position", "")).strip(),
            "target_city": str(job_intention.get("target_city", "")).strip(),
            "employment_type": str(job_intention.get("employment_type", "")).strip(),
        },
        "background": {
            "education": str(background.get("education", "")).strip(),
            "years_of_experience": str(
                background.get("years_of_experience", "")
            ).strip(),
            "core_skills": [str(skill).strip() for skill in core_skills if str(skill).strip()],
        },
        "match_analysis": {
            "score": score,
            "reason": reason,
        },
    }


# 3. 真实 LLM 调用
def call_llm(resume_text: str, jd_text: str) -> dict[str, Any]:
    system_prompt = """
你是一名资深 HR 和招聘负责人，擅长从候选人简历中提炼结构化信息，并结合岗位描述给出专业、克制、可解释的匹配判断。

你的输出必须满足以下要求：
1. 只能输出严格合法的 JSON 对象，绝对不要输出 Markdown、代码块、说明文字或额外字段。
2. 顶层字段必须且只能包含：basic_info、job_intention、background、match_analysis。
3. basic_info 必须包含：name、phone、email。
4. job_intention 必须包含：target_position、target_city、employment_type。
5. background 必须包含：education、years_of_experience、core_skills。
6. match_analysis 必须包含：score、reason。
7. score 必须是 0 到 100 之间的整数。
8. 若简历中没有明确信息，请返回空字符串，core_skills 返回空数组。
9. 匹配理由需要简洁、专业，突出亮点与短板，不要超过 120 字。
""".strip()

    user_prompt = f"""
请基于以下岗位描述和简历文本，输出严格 JSON。

岗位描述（JD）：
{jd_text}

简历文本：
{resume_text}

请确保输出 JSON 结构如下：
{{
  "basic_info": {{
    "name": "",
    "phone": "",
    "email": ""
  }},
  "job_intention": {{
    "target_position": "",
    "target_city": "",
    "employment_type": ""
  }},
  "background": {{
    "education": "",
    "years_of_experience": "",
    "core_skills": []
  }},
  "match_analysis": {{
    "score": 0,
    "reason": ""
  }}
}}
""".strip()

    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except openai.APITimeoutError as exc:
        raise RuntimeError("LLM 请求超时，请稍后重试。") from exc
    except openai.APIError as exc:
        raise RuntimeError(f"LLM 请求失败: {exc}") from exc
    except openai.OpenAIError as exc:
        if "api_key" in str(exc).lower():
            raise RuntimeError(
                "未配置 OPENAI_API_KEY。由于涉及到真实的 LLM API Token，本项目默认未内置 Key，请在环境变量或 main.py 中填入您自己的 OpenAI API Key。"
            ) from exc
        raise RuntimeError(f"LLM 鉴权或请求失败: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(
            "OpenAI 客户端初始化或请求失败，请检查 OPENAI_API_KEY / OPENAI_BASE_URL 配置。"
        ) from exc

    try:
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM 返回内容为空。")
        parsed = json.loads(content)
        return validate_llm_result(parsed)
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError(f"LLM 返回结果解析失败: {exc}") from exc


# 4. 核心路由
@app.post("/api/analyze")
async def analyze_resume(
    file: UploadFile = File(...),
    job_description: str = Form(...),
) -> JSONResponse:
    try:
        filename = (file.filename or "").lower()
        if not filename.endswith(".pdf"):
            return JSONResponse(
                status_code=400,
                content={"code": 400, "message": "仅支持上传 .pdf 文件。", "data": None},
            )

        if not job_description.strip():
            return JSONResponse(
                status_code=400,
                content={"code": 400, "message": "job_description 不能为空。", "data": None},
            )

        file_bytes = await file.read()
        file_md5 = hashlib.md5(file_bytes).hexdigest()
        jd_md5 = hashlib.md5(job_description.encode("utf-8")).hexdigest()
        cache_key = f"{file_md5}:{jd_md5}"

        if cache_key in result_cache:
            print("命中缓存")
            return JSONResponse(
                status_code=200,
                content={"code": 0, "message": "分析成功", "data": result_cache[cache_key]},
            )

        resume_text = extract_text_from_pdf(file_bytes)
        result = call_llm(resume_text, job_description)
        result_cache[cache_key] = result

        return JSONResponse(
            status_code=200,
            content={"code": 0, "message": "分析成功", "data": result},
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": str(exc), "data": None},
        )
    except RuntimeError as exc:
        logger.exception("简历分析流程失败")
        return JSONResponse(
            status_code=500,
            content={"code": 500, "message": str(exc), "data": None},
        )
    except Exception:
        logger.exception("接口处理时发生未预期错误")
        return JSONResponse(
            status_code=500,
            content={"code": 500, "message": "服务器内部错误。", "data": None},
        )
    finally:
        await file.close()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
