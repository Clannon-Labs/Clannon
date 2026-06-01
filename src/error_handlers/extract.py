def extract_error_info(err, model_inst):
    import re
    import logging
    
    logger = logging.getLogger(__name__)
    logger.error("Caught exception during model execution", exc_info=err)

    status_code = getattr(err, "status_code", "unknown")

    model_name = getattr(model_inst, "model_name", None)
    if not model_name:
        model_name = str(model_inst)

    body = getattr(err, "body", None)

    if body is None:
        response = getattr(err, "response", None)

        try:
            if response and hasattr(response, "json"):
                body = response.json()
            else:
                body = str(err)
        except Exception:
            body = str(err)

    message = "Unknown error"
    raw_body = str(body)

    if isinstance(body, dict):
        # Nested error format (Anthropic / Google)
        if "error" in body and isinstance(body["error"], dict):
            message = body["error"].get("message", message)

        # Flat error format (OpenAI)
        elif "message" in body:
            message = body.get("message", message)
    else:
        message = str(body)

    detail_lines = [
        line.strip()
        for line in str(message).splitlines()
        if line.strip()
    ]
    message = detail_lines[0] if detail_lines else "Unknown error"

    lower_body = raw_body.lower()
    category = "unknown"
    likely_cause = "The provider returned an error Vraksha does not recognize yet."
    suggested_fix = "Check the detailed provider message and the provider dashboard."
    retry_after = None

    retry_match = re.search(r"retry(?:delay| in)?[':\s]+['\"]?([0-9.]+)\s*s", raw_body, re.IGNORECASE)
    if retry_match:
        retry_after = f"{retry_match.group(1)}s"

    if status_code == 429 or "resource_exhausted" in lower_body or "quota" in lower_body:
        category = "quota_exhausted"
        likely_cause = "Your provider account or project has exhausted quota for this model."
        suggested_fix = "Wait for quota reset, enable billing/increase quota, or move this provider lower in models.yaml."
    elif status_code in (401, 403) or "unauthorized" in lower_body or "forbidden" in lower_body or "authentication" in lower_body:
        category = "authentication"
        likely_cause = "The API key is missing, invalid, expired, or not allowed to use this model."
        suggested_fix = "Check the key in .env.local and confirm the provider account has model access."
    elif "base_url" in lower_body or "region_name" in lower_body or "environment variable" in lower_body:
        category = "provider_configuration"
        likely_cause = "The fallback provider is configured incompletely."
        suggested_fix = "Set the missing provider URL/region/client value, or remove that provider from the fallback chain."
    elif "rate limit" in lower_body or "rate_limit" in lower_body:
        category = "rate_limited"
        likely_cause = "The provider is temporarily rate limiting requests."
        suggested_fix = "Wait briefly, reduce request frequency, or use a different fallback provider."
    elif "network" in lower_body or "connection" in lower_body or "timeout" in lower_body:
        category = "network"
        likely_cause = "Vraksha could not reach the provider reliably."
        suggested_fix = "Check network connectivity, proxy settings, and provider status."

    urls = re.findall(r"https?://[^\s,]+", str(body))
    help_url = urls[0] if urls else None

    return {
        "status_code": status_code,
        "model_name": model_name,
        "message": message,
        "details": detail_lines[1:],
        "category": category,
        "likely_cause": likely_cause,
        "suggested_fix": suggested_fix,
        "retry_after": retry_after,
        "help_url": help_url,
    }
