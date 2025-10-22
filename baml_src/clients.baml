// Learn more about clients at https://docs.boundaryml.com/docs/snippets/clients/overview

// Using the new OpenAI Responses API for enhanced formatting
client<llm> CustomGPT5 {
  provider openai-responses
  options {
    model "gpt-5"
    api_key env.OPENAI_API_KEY
  }
}

client<llm> CustomGPT5Mini {
  provider openai-responses
  retry_policy Exponential
  options {
    model "gpt-5-mini"
    api_key env.OPENAI_API_KEY
  }
}

// Openai with chat completion
client<llm> CustomGPT5Chat {
  provider openai
  options {
    model "gpt-5"
    api_key env.OPENAI_API_KEY
  }
}

// Latest Anthropic Claude 4 models
client<llm> CustomOpus4 {
  provider anthropic
  options {
    model "claude-opus-4-1-20250805"
    api_key env.ANTHROPIC_API_KEY
  }
}

client<llm> CustomSonnet4 {
  provider anthropic
  options {
    model "claude-sonnet-4-20250514"
    api_key env.ANTHROPIC_API_KEY
  }
}

client<llm> CustomHaiku {
  provider anthropic
  retry_policy Constant
  options {
    model "claude-3-5-haiku-20241022"
    api_key env.ANTHROPIC_API_KEY
  }
}

// Example Google AI client (uncomment to use)
// client<llm> CustomGemini {
//   provider google-ai
//   options {
//     model "gemini-2.5-pro"
//     api_key env.GOOGLE_API_KEY
//   }
// }

// Example AWS Bedrock client (uncomment to use)
// client<llm> CustomBedrock {
//   provider aws-bedrock
//   options {
//     model "anthropic.claude-sonnet-4-20250514-v1:0"
//     region "us-east-1"
//     // AWS credentials are auto-detected from env vars
//   }
// }

// Example Azure OpenAI client (uncomment to use)
// client<llm> CustomAzure {
//   provider azure-openai
//   options {
//     model "gpt-5"
//     api_key env.AZURE_OPENAI_API_KEY
//     base_url "https://MY_RESOURCE_NAME.openai.azure.com/openai/deployments/MY_DEPLOYMENT_ID"
//     api_version "2024-10-01-preview"
//   }
// }

// Example Vertex AI client (uncomment to use)
// client<llm> CustomVertex {
//   provider vertex-ai
//   options {
//     model "gemini-2.5-pro"
//     location "us-central1"
//     // Uses Google Cloud Application Default Credentials
//   }
// }

// Example Ollama client for local models (uncomment to use)
// client<llm> CustomOllama {
//   provider openai-generic
//   options {
//     base_url "http://localhost:11434/v1"
//     model "llama4"
//     default_role "user" // Most local models prefer the user role
//     // No API key needed for local Ollama
//   }
// }

// https://docs.boundaryml.com/docs/snippets/clients/round-robin
client<llm> CustomFast {
  provider round-robin
  options {
    // This will alternate between the two clients
    strategy [CustomGPT5Mini, CustomHaiku]
  }
}

// https://docs.boundaryml.com/docs/snippets/clients/fallback
client<llm> OpenaiFallback {
  provider fallback
  options {
    // This will try the clients in order until one succeeds
    strategy [CustomGPT5Mini, CustomGPT5]
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
  max_retries 2
  strategy {
    type exponential_backoff
    delay_ms 300
    multiplier 1.5
    max_delay_ms 10000
  }
}

// Z.AI GLM 4.6 clients for BIM QA system - General API
client<llm> ZAIClient {
  provider openai
  options {
    base_url "https://api.z.ai/api/paas/v4"
    model "glm-4.6"
    api_key env.Z_AI_API_KEY
    temperature 0
  }
}

client<llm> ZAIGLM46Mini {
  provider openai
  retry_policy Exponential
  options {
    base_url "https://api.z.ai/api/paas/v4"
    model "glm-4.6-mini"
    api_key env.Z_AI_API_KEY
    temperature 0
  }
}

// Z.AI GLM Coding Plan - Optimized for coding tasks with enhanced performance
client<llm> ZAICodingPlan {
  provider openai
  options {
    base_url "https://api.z.ai/api/coding/paas/v4"
    model "glm-4.6"
    api_key env.Z_AI_API_KEY
    temperature 0.1
    max_tokens 8192
  }
}

client<llm> ZAICodingPlanMini {
  provider openai
  retry_policy Exponential
  options {
    base_url "https://api.z.ai/api/coding/paas/v4"
    model "glm-4.6-mini"
    api_key env.Z_AI_API_KEY
    temperature 0.1
    max_tokens 4096
  }
}

// DeepInfra QWEN3-CODER client - High-performance coding model
client<llm> DeepInfraQwen3Coder {
  provider openai
  retry_policy Exponential
  options {
    base_url "https://api.deepinfra.com/v1/openai"
    model "Qwen/Qwen3-Coder-480B-A35B-Instruct-Turbo"
    api_key env.DEEPINFRA_API_KEY
    temperature 0.1
    max_tokens 8192
  }
}
