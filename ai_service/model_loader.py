"""Load the base Qwen model and ESG QLoRA adapter once."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Tuple

from configs.settings import BASE_MODEL_PATH, HF_LOCAL_FILES_ONLY, MODEL_ALLOW_DOWNLOAD, resolve_adapter_path

_MODEL = None
_TOKENIZER = None


def get_model_and_tokenizer() -> Tuple[Any, Any]:
    """Return the loaded model/tokenizer pair with process-global caching."""
    global _MODEL, _TOKENIZER

    if _MODEL is not None and _TOKENIZER is not None:
        return _MODEL, _TOKENIZER

    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    except Exception as exc:
        raise RuntimeError(
            "Local QLoRA dependencies are not installed. Use RAG_ANSWER_MODE=openai and "
            "ESG_EXTRACTION_BACKEND=remote in production, or install torch/transformers/peft locally."
        ) from exc

    adapter_dir = resolve_adapter_path()
    if not adapter_dir.exists():
        raise FileNotFoundError(
            f"Adapter directory not found: {adapter_dir.resolve()}. "
            "Expected a LoRA adapter under ./esg_qlora_adapter or ./qlora_model/esg-qwen2.5-7b-qlora, "
            "or set ESG_ADAPTER_PATH explicitly."
        )
    if not (adapter_dir / "adapter_config.json").exists() or not (adapter_dir / "adapter_model.safetensors").exists():
        raise FileNotFoundError(
            f"Adapter directory is incomplete: {adapter_dir.resolve()}. "
            "Missing adapter_config.json or adapter_model.safetensors."
        )

    base_model_ref = BASE_MODEL_PATH
    base_model_path = Path(base_model_ref)
    local_files_only = HF_LOCAL_FILES_ONLY or base_model_path.exists() or not MODEL_ALLOW_DOWNLOAD
    use_4bit = _can_use_4bit_quantization()
    quantization_config = None
    model_kwargs = {"device_map": "auto", "trust_remote_code": True}

    if use_4bit:
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        model_kwargs["quantization_config"] = quantization_config
    else:
        model_kwargs["torch_dtype"] = torch.float16 if torch.cuda.is_available() else torch.float32

    try:
        tokenizer = AutoTokenizer.from_pretrained(
            base_model_ref,
            trust_remote_code=True,
            local_files_only=local_files_only,
        )
    except Exception as exc:
        raise RuntimeError(
            "Failed to load the Qwen tokenizer/base model reference. "
            "If the model is not cached locally, either enable internet access for Hugging Face "
            "or set ESG_BASE_MODEL_PATH to a local Qwen base model directory. "
            f"Current base reference: {base_model_ref}. Original error: {exc}"
        ) from exc
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    try:
        base_model = AutoModelForCausalLM.from_pretrained(
            base_model_ref,
            local_files_only=local_files_only,
            **model_kwargs,
        )
    except Exception as exc:
        raise RuntimeError(
            "Failed to load the Qwen base model. "
            "If the model is not already cached locally, either enable internet access for Hugging Face "
            "or set ESG_BASE_MODEL_PATH to a local base model directory. "
            f"Current base reference: {base_model_ref}. Original error: {exc}"
        ) from exc

    model = PeftModel.from_pretrained(
        base_model,
        str(adapter_dir),
        trust_remote_code=True,
    )
    model.eval()

    _MODEL = model
    _TOKENIZER = tokenizer
    return _MODEL, _TOKENIZER


def _can_use_4bit_quantization() -> bool:
    """Use 4-bit loading only when CUDA is available and bitsandbytes is usable."""
    try:
        import torch
    except Exception:
        return False

    if not torch.cuda.is_available():
        return False

    try:
        import bitsandbytes as bnb  # noqa: F401
    except Exception:
        return False

    return True
