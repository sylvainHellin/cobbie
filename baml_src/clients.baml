// Learn more about clients at https://docs.boundaryml.com/docs/snippets/clients/overview

// Z.AI GLM 4.7 (with Coding Plan API key)
client<llm> GLM_4_7{
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

// Minimax M2 client
client<llm> MinimaxM2 {
  provider openai
  retry_policy Exponential
  options {
    base_url "https://api.minimax.chat/v1"
    model "minimax-m2"
    api_key env.MINIMAX_API_KEY
    temperature 0.1
    max_tokens 8192
  }
}


// https://docs.boundaryml.com/docs/snippets/clients/retry
retry_policy Constant {
  max_retries 3
  strategy {
    type constant_delay
    delay_ms 200
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
