import json, shutil
from pathlib import Path
from safetensors import safe_open
from safetensors.torch import save_file

BASE_PATH = Path("/Users/juanjosearevalocamargo/Desktop/models")
SOURCE_DIR = BASE_PATH / "gemma4-e4b"
TARGET_DIR = BASE_PATH / "gemma4-text-only"
SOURCE_SAFE = SOURCE_DIR / "model.safetensors"
TARGET_SAFE = TARGET_DIR / "model.safetensors"

def surgical_clean():
    print("1. Limpiando TARGET_DIR...")
    if TARGET_SAFE.exists(): TARGET_SAFE.unlink()
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    
    # Configuración Gemma 2 Estándar (Sin extensiones Omni)
    with open(SOURCE_DIR / "config.json", "r") as f:
        src_cfg = json.load(f)
    text_cfg = src_cfg.get("text_config", src_cfg)
    
    new_config = {
        "architectures": ["Gemma2ForCausalLM"],
        "model_type": "gemma2",
        "hidden_size": text_cfg["hidden_size"],
        "num_hidden_layers": text_cfg["num_hidden_layers"],
        "intermediate_size": text_cfg["intermediate_size"],
        "num_attention_heads": text_cfg["num_attention_heads"],
        "num_key_value_heads": text_cfg["num_key_value_heads"],
        "head_dim": text_cfg["head_dim"],
        "rms_norm_eps": text_cfg["rms_norm_eps"],
        "vocab_size": text_cfg["vocab_size"],
        "rope_theta": text_cfg.get("rope_theta", 10000.0),
        "sliding_window": 4096,
        "final_logit_softcap": 30.0,
        "attn_logit_softcap": 50.0
    }
    
    with open(TARGET_DIR / "config.json", "w") as f:
        json.dump(new_config, f, indent=2)
    
    for f_name in ["tokenizer.json", "tokenizer_config.json"]:
        if (SOURCE_DIR / f_name).exists():
            shutil.copy(SOURCE_DIR / f_name, TARGET_DIR / f_name)

    print("2. Filtrado con 'Iron Whitelist' (Solo model.*.weight)...")
    
    # Solo permitimos llaves que MLX Gemma 2 espera
    new_tensors = {}
    with safe_open(SOURCE_SAFE, framework="pt", device="cpu") as f:
        for key in f.keys():
            # Eliminar prefijo language_model
            clean_key = key.replace("language_model.", "")
            
            # REGLA 1: Solo el backbone de lenguaje (model. o lm_head.)
            if not (clean_key.startswith("model.") or clean_key.startswith("lm_head.")):
                continue
            
            # REGLA 2: Solo pesos (.weight). Sin biases, scales o AQT metadata.
            if not clean_key.endswith(".weight"):
                continue
            
            # REGLA 3: Excluir componentes específicos de Gemma 4 (Omni/Experimental)
            # MLX Gemma 2 fallará si recibe q_norm, k_norm o layer_scalar
            forbidden = ["q_norm", "k_norm", "layer_scalar", "per_layer", "input_gate"]
            if any(word in clean_key for word in forbidden):
                continue
                
            new_tensors[clean_key] = f.get_tensor(key)
    
    print(f"3. Guardando {len(new_tensors)} tensores puros...")
    save_file(new_tensors, str(TARGET_SAFE))
    print("\n--- CIRUGÍA V6 COMPLETADA: NÚCLEO DE LENGUAJE AISLADO ---")

if __name__ == "__main__":
    surgical_clean()