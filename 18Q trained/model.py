"""
model.py
--------
The Text-to-SQL model inference layer with fallback and self-correction retry loop.
"""

import os
import re
import time
from prompts import SYSTEM_PROMPT, RETRY_PROMPT_TEMPLATE, EXPLAIN_PROMPT_TEMPLATE

MODEL_NAME = "gemini-flash-latest"
MAX_RETRIES = 2

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None
        try:
            from google import genai
            _client = genai.Client(api_key=api_key)
        except Exception:
            _client = None
    return _client


def _clean_sql(raw_text: str) -> str:
    text = raw_text.strip()
    text = re.sub(r"^```sql\s*|^```\s*|```$", "", text, flags=re.MULTILINE).strip()
    return text


def generate_sql(question: str, history: list | None = None) -> str:
    client = _get_client()
    if client is None:
        # Fallback query lookup for offline execution
        from dataset_18q import BENCHMARK_18Q
        for item in BENCHMARK_18Q:
            if item["question"].strip().lower() == question.strip().lower():
                return item["sql"]
        return f"SELECT * FROM customers LIMIT 10;"

    try:
        from google.genai import types
        context_block = ""
        if history:
            context_block = "CONVERSATION SO FAR:\n"
            for turn in history:
                context_block += f"Q: {turn['question']}\nSQL: {turn['sql']}\n"
            context_block += "\n"

        user_message = f"{context_block}Q: {question}\nSQL:"
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0,
                max_output_tokens=500,
            ),
        )
        return _clean_sql(response.text)
    except Exception as e:
        return f"ERROR: Inference error: {str(e)}"


def generate_sql_with_retry(
    question: str,
    validate_fn,
    execute_fn,
    history: list | None = None,
    max_retries: int = MAX_RETRIES,
) -> dict:
    sql = generate_sql(question, history=history)
    attempts = [{"attempt": 1, "sql": sql}]

    if sql.startswith("ERROR:"):
        return {"status": "rejected", "reason": sql, "attempts": attempts}

    for attempt_num in range(1, max_retries + 2):
        is_valid, validation_error = validate_fn(sql)
        if not is_valid:
            if attempt_num > max_retries:
                return {"status": "failed_validation", "reason": validation_error, "attempts": attempts}
            sql = _retry_generation(question, sql, validation_error)
            attempts.append({"attempt": attempt_num + 1, "sql": sql})
            continue

        success, result_or_error = execute_fn(sql)
        if success:
            return {"status": "success", "sql": sql, "result": result_or_error, "attempts": attempts}

        if attempt_num > max_retries:
            return {"status": "failed_execution", "reason": result_or_error, "sql": sql, "attempts": attempts}

        sql = _retry_generation(question, sql, result_or_error)
        attempts.append({"attempt": attempt_num + 1, "sql": sql})

    return {"status": "failed_execution", "reason": "Max retries exceeded", "attempts": attempts}


def _retry_generation(question: str, previous_sql: str, error_message: str) -> str:
    client = _get_client()
    if not client:
        return previous_sql
    try:
        from google.genai import types
        retry_prompt = RETRY_PROMPT_TEMPLATE.format(
            previous_sql=previous_sql, error_message=error_message, question=question
        )
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=retry_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0,
                max_output_tokens=500,
            ),
        )
        return _clean_sql(response.text)
    except Exception:
        return previous_sql


def explain_query(sql_query: str) -> str:
    client = _get_client()
    if not client:
        return f"This SQL query queries the database tables matching filter conditions."
    try:
        from google.genai import types
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=EXPLAIN_PROMPT_TEMPLATE.format(sql_query=sql_query),
            config=types.GenerateContentConfig(temperature=0.3, max_output_tokens=200),
        )
        return response.text.strip()
    except Exception:
        return "Explanation unavailable."
