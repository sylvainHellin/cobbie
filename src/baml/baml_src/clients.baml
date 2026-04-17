// LLM clients for the ACC pipeline.
//
// Primary: Z.AI GLM 4.7 (the config used to produce the paper results).
// The `base_url` below is the exact endpoint the paper runs targeted — if
// your Z.AI key doesn't accept it, swap `client GLM_4_7` to
// `client GLM_4_7_OpenRouter` in any baml function to run the same model
// (z-ai/glm-4.7) via OpenRouter.

client<llm> GLM_4_7 {
  provider openai
  retry_policy Exponential
  options {
    base_url "https://api.z.ai/api/coding/paas/v4"
    model "glm-4.7"
    api_key env.Z_AI_API_KEY
    temperature 0.1
    max_tokens 8192
  }
}

client<llm> GLM_4_7_OpenRouter {
  provider openrouter
  retry_policy Exponential
  options {
    model "z-ai/glm-4.7"
    api_key env.OPENROUTER_API_KEY
    temperature 0.1
    max_tokens 8192
  }
}

retry_policy Exponential {
  max_retries 5
  strategy {
    type exponential_backoff
    delay_ms 1000
    multiplier 2
    max_delay_ms 40000
  }
}
