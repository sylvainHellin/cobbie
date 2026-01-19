// Learn more about clients at https://docs.boundaryml.com/docs/snippets/clients/overview

// Anthropic Claude Haiku - for lightweight tasks like chunk review
client<llm> ClaudeHaiku {
  provider anthropic
  retry_policy Exponential
  options {
    model "claude-3-5-haiku-latest"
    api_key env.ANTHROPIC_API_KEY
    max_tokens 1024
  }
}

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

// Z.AI GLM 4.5 (with Coding Plan API key)
client<llm> GLM_4_5_air{
  provider openai
  retry_policy Exponential
  options {
    base_url "https://api.z.ai/api/coding/paas/v4"
    model "glm-4.5-air"
    api_key env.Z_AI_API_KEY
    temperature 0.1
    max_tokens 8192
  }
}

client<llm> Devstral {
  provider "openai-generic"
  retry_policy Constant
  options {
    base_url "http://localhost:11434/v1"
    model "devstral-small-2:latest"
  }
}

client<llm> Gemini_2_5_Flash_Lite {
  provider google-ai
  retry_policy Exponential
  options {
    model "gemini-2.5-flash-lite"
    api_key env.GEMINI_API_KEY
    generationConfig {
      temperature 0.1
    }
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
