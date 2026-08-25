"""
One place that talks to a language model.

Three parts of the project call one: the criteria extraction at
ingestion, the answer generation at query time, and the judge that
grades answers. They all come through here, so retries, JSON handling
and token counting are written once.

**Two providers, one pair of functions.**

The guide picks Gemini, and Gemini still works. I moved to Groq partway
through because the Gemini free tier is 20 requests a day per model, and
running my own evaluation once needs about three hundred. Rather than
rewrite everything, the two providers sit behind generate_text() and
generate_json(), and LLM_PROVIDER in the .env picks one. Nothing else in
the project knows or cares which is running.

That is the same idea as vector_store.py keeping Chroma behind upsert
and search. A thing likely to be swapped gets a small interface early,
and then swapping it is a config change instead of a project.

**JSON is validated here, not trusted.**

Providers differ in how strictly they honour a schema, so the schema is
described in the prompt, and whatever comes back is parsed and checked
against the Pydantic model myself. If it does not fit, the model is
told exactly what was wrong and asked once more. Section 5 of the guide
calls the typed schema the first defence against hallucination, and a
schema nobody enforces is not a defence at all.
"""

import json
import re
import time

from pydantic import ValidationError

from . import config

# Reasoning models wrap their working in these. Asking the provider to
# hide it usually works, but not every model honours the request, so the
# text is cleaned here as well. Belt and braces, because the cost of
# missing one is a student reading the model's notes to itself.
THINKING_PATTERN = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


def strip_thinking(text):
    """Take the reasoning block out of a reply, if one leaked through."""
    if not text:
        return ""

    cleaned = THINKING_PATTERN.sub("", text)

    # An unclosed <think> means the reply was cut off mid thought. There
    # is no answer after it, so keep whatever came before instead of
    # handing over half a thought.
    if "<think>" in cleaned:
        cleaned = cleaned.split("<think>")[0]

    return cleaned.strip()

# Failures worth trying again. 429 is a rate limit and the 5xx family is
# the provider being busy. Neither says my request was wrong, so neither
# should end a job halfway through a corpus.
RETRYABLE = ["429", "500", "502", "503", "504", "RESOURCE_EXHAUSTED", "UNAVAILABLE"]

# Model families that think before answering. Only these accept the
# reasoning options below; the rest reject the request outright.
REASONING_MODELS = ("openai/gpt-oss", "qwen/", "deepseek")

_groq_client = None
_gemini_client = None


def using_groq():
    return config.LLM_PROVIDER == "groq"


def model_name(kind="answer"):
    """
    Which model is doing a job, for the eval config and the README.

    kind is "answer" or "judge". They are deliberately different models
    on Groq, so that nothing marks its own homework.
    """
    if not using_groq():
        return config.GEMINI_MODEL
    return config.GROQ_JUDGE_MODEL if kind == "judge" else config.GROQ_MODEL


# ---------------------------------------------------------------- Groq


def get_groq():
    global _groq_client
    if _groq_client is None:
        if not config.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is empty. Put your key in backend/.env first.")
        from groq import Groq

        _groq_client = Groq(api_key=config.GROQ_API_KEY)
    return _groq_client


def _groq_call(prompt, system_instruction, temperature, json_mode, model=None):
    """One Groq request. Returns (text, tokens)."""
    model = model or config.GROQ_MODEL

    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    extra = {}

    # Ask the provider to enforce JSON only where that actually works.
    #
    # Groq's strict JSON mode rejects the whole request if the model
    # writes anything outside the object, and a reasoning model writes
    # its thinking first, so qwen failed every call with "Failed to
    # validate JSON" and an empty body. Nothing was wrong with the
    # prompt; the two features do not fit together.
    #
    # Leaving it off is safe because generate_json() does not trust the
    # provider anyway. It puts the schema in the prompt, pulls the
    # object out of whatever comes back, and validates it against the
    # Pydantic model itself.
    if json_mode and model.startswith("openai/gpt-oss"):
        extra["response_format"] = {"type": "json_object"}

    # The gpt-oss models think before they answer, and every thinking
    # token counts against the daily allowance. On "high" a single eval
    # run does not fit in a day. These are lookups and comparisons over
    # a paragraph of text, not puzzles, so "low" costs nothing that
    # matters and roughly triples how much I can measure.
    if model.startswith("openai/gpt-oss"):
        extra["reasoning_effort"] = "low"

    # Keep the thinking out of the answer. Without this, qwen returned
    # its whole "Here's a thinking process: 1. Analyze User Input..."
    # as the answer text, which would have gone straight to the student
    # and straight through the grounding check as a wall of numbers.
    #
    # Only reasoning models take this setting. Sending it to one that
    # does not think returns a 400 and kills the request, so a model
    # that was otherwise perfectly usable becomes unusable because of an
    # option it never needed.
    if any(model.startswith(family) for family in REASONING_MODELS):
        extra["reasoning_format"] = "hidden"

    response = get_groq().chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        **extra,
    )

    text = response.choices[0].message.content or ""
    tokens = response.usage.total_tokens if response.usage else 0
    return strip_thinking(text), tokens


# -------------------------------------------------------------- Gemini


def get_gemini():
    global _gemini_client
    if _gemini_client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is empty. Put your key in backend/.env first.")
        from google import genai

        _gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _gemini_client


def _gemini_call(prompt, system_instruction, temperature, json_mode, model=None):
    """One Gemini request. Returns (text, tokens)."""
    from google.genai import types

    response = get_gemini().models.generate_content(
        model=model or config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            response_mime_type="application/json" if json_mode else None,
            # The SDK assumes I might hand it Python functions to call
            # and warns about it on every request. This project never
            # does that, so the feature is turned off.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )

    text = response.text or ""
    try:
        tokens = response.usage_metadata.total_token_count or 0
    except Exception:
        tokens = 0
    return text, tokens


# --------------------------------------------------------- the two doors


def _call(prompt, system_instruction=None, temperature=0.0, json_mode=False, retries=6, model=None):
    """
    Send one request, waiting and trying again on a temporary failure.

    The wait doubles each time and stops growing at 60 seconds. A fixed
    wait walks straight back into the same rate limit, and one that
    keeps doubling eventually sits there for a quarter of an hour, which
    is not retrying any more, it is hanging.
    """
    send = _groq_call if using_groq() else _gemini_call

    for attempt in range(retries):
        try:
            return send(prompt, system_instruction, temperature, json_mode, model)
        except Exception as error:
            message = str(error)
            if not any(code in message for code in RETRYABLE) or attempt == retries - 1:
                raise

            wait = min(2 ** (attempt + 1), 60)
            print(f"  provider said no ({message[:60]}...), waiting {wait}s")
            time.sleep(wait)


def generate_text(prompt, system_instruction=None, temperature=0.0, model=None):
    """
    Ask for a plain text answer.

    temperature 0 because every use here wants the same answer for the
    same input. This is not creative writing, it is a lookup with
    grammar, and a run to run difference would show up as noise in the
    eval and I would not know whether a change had helped.

    Returns (text, tokens_used).
    """
    return _call(prompt, system_instruction, temperature, json_mode=False, model=model)


def _first_json_object(text):
    """
    Pull the JSON object out of a reply.

    JSON mode usually returns clean JSON, but a model occasionally wraps
    it in a ```json fence or writes a sentence first. Taking the text
    from the first brace to the last is a small, boring fix that saves a
    lot of failed extractions.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in the reply: {text[:200]}")
    return text[start : end + 1]


def generate_json(prompt, response_schema, system_instruction=None, model=None):
    """
    Ask for JSON shaped like response_schema, and check that it is.

    response_schema is a Pydantic model class. Its JSON schema is put in
    the prompt, and the reply is validated against the model here. If
    validation fails, the model is told what was wrong and asked once
    more, because a single missing field is usually fixed on the retry
    and re-running a whole corpus because of one is wasteful.

    Returns (parsed_dict, tokens_used).
    """
    schema = json.dumps(response_schema.model_json_schema(), indent=2)

    full_prompt = (
        f"{prompt}\n\n"
        "Reply with a single JSON object and nothing else. It must match "
        f"this JSON schema:\n\n{schema}"
    )

    total_tokens = 0
    last_problem = None

    for attempt in range(2):
        ask = full_prompt
        if last_problem:
            ask = (
                f"{full_prompt}\n\nYour previous reply did not fit the schema: "
                f"{last_problem}\nReturn the corrected JSON object."
            )

        text, tokens = _call(ask, system_instruction, 0.0, json_mode=True, model=model)
        total_tokens += tokens

        try:
            parsed = json.loads(_first_json_object(text))
            # Validate, then hand back the validated version rather than
            # the raw dict, so defaults are filled in and types are real
            # floats and ints instead of whatever the model typed.
            return response_schema(**parsed).model_dump(), total_tokens
        except (ValueError, ValidationError, TypeError) as error:
            last_problem = str(error)[:300]
            if attempt == 1:
                raise ValueError(f"model would not return valid JSON: {last_problem}")


if __name__ == "__main__":
    print(f"provider: {config.LLM_PROVIDER}   model: {model_name()}")
    text, tokens = generate_text("Reply with exactly: the model is working")
    print(f"{text.strip()}   ({tokens} tokens)")
