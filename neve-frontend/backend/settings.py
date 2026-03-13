"""User-editable settings for the Neve backend.

The Neve backend now uses a local LLM (llama-cpp-python) instead of
cloud APIs.  Place your .gguf model files in the `models/` directory
at the project root and load them through the UI or settings below.
"""

# Path to the default GGUF model (relative to project root or absolute).
# Leave empty to require manual loading via the UI.
LLAMA_MODEL_PATH = ""

# Context window size (tokens). Larger = more memory usage.
LLAMA_N_CTX = 8192

# Number of CPU threads to use.  None = auto-detect.
LLAMA_N_THREADS = None

# Number of model layers to offload to the GPU (-1 = all layers).
LLAMA_N_GPU_LAYERS = -1

# Sampling temperature (0.0 – 2.0).
LLAMA_TEMPERATURE = 0.9

# Repetition penalty (1.0 = disabled, >1.0 penalises repeated tokens).
LLAMA_REPEAT_PENALTY = 1.1

# Top-p (nucleus) sampling threshold.
LLAMA_TOP_P = 0.92

# Top-k sampling: only consider the top-k most probable tokens.
LLAMA_TOP_K = 50

# Maximum tokens to generate per reply.
LLAMA_MAX_TOKENS = 512
