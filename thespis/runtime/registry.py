"""What the local runtime can fetch: models and the llama.cpp builds that run them, each pinned to a checksum.

Every file is named by where it comes from, how big it is and its SHA-256, so a download is checked before it is
used and a half-finished one resumes. Model tiers are what the hardware probe chooses between (thespis.runtime.
hardware). Which tiers Thespis supports is decided by measurement, not by this list: docs/models.md records what each
tier scored in live Rehearsal.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Artifact:
    url: str
    sha256: str
    size: int  # bytes

    @property
    def name(self) -> str:
        return self.url.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class Model:
    id: str
    artifact: Artifact
    params: str  # "4B"
    quant: str  # "Q4_K_M"
    licence: str
    vram_gb: float  # GPU memory to run it wholly on the GPU, two slots of `ctx` (docs/models.md: measured or not)
    ram_gb: float  # to run it on the CPU instead
    ctx: int = 4096  # context per slot; a state pack and its reply fit in well under half of it
    kind: str = "chat"  # "chat" or "embed"


HF = "https://huggingface.co"


def _hf(repo: str, file: str, sha256: str, size: int) -> Artifact:
    return Artifact(f"{HF}/{repo}/resolve/main/{file}", sha256, size)


MODELS: dict[str, Model] = {m.id: m for m in (
    Model("qwen3.5-4b", _hf("unsloth/Qwen3.5-4B-GGUF", "Qwen3.5-4B-Q4_K_M.gguf",
                             "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4", 2_740_937_888),
          "4B", "Q4_K_M", "Apache-2.0", vram_gb=3.0, ram_gb=5.0),  # measured: 3,048 MiB at 2 x 4096 on Vulkan
    Model("qwen3.5-9b", _hf("unsloth/Qwen3.5-9B-GGUF", "Qwen3.5-9B-Q4_K_M.gguf",
                             "03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8", 5_680_522_464),
          "9B", "Q4_K_M", "Apache-2.0", vram_gb=6.2, ram_gb=8.5),  # estimated; on a 4 GB GPU it ran partly in RAM at 8-13 s a line
    # A candidate for the first tier, from another family: 4B effective, with per-layer embeddings that llama.cpp
    # may keep in RAM. Google's quantisation-aware-trained Q4_0. Not a tier until live Rehearsal says so.
    Model("gemma4-e4b", _hf("google/gemma-4-E4B-it-qat-q4_0-gguf", "gemma-4-E4B_q4_0-it.gguf",
                             "676c35070db6dbe52f93e9c864ee0fba4eddea94b9c875d9cb10daff453fbaee", 5_154_941_280),
          "E4B", "Q4_0 (QAT)", "Apache-2.0", vram_gb=3.0, ram_gb=7.0),  # measured: 3,042 MiB at 2 x 4096
)}

# Tiers, smallest first: the probe picks the largest the machine can run (thespis.runtime.hardware.choose).
TIERS = ("qwen3.5-4b", "qwen3.5-9b")

# llama.cpp, pinned: one build for every platform, so a fix or a regression lands for everyone at once.
LLAMA_CPP = "b11172"  # 2026-09-24
_GH = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_CPP}"


def _gh(asset: str, sha256: str, size: int) -> Artifact:
    return Artifact(f"{_GH}/llama-{LLAMA_CPP}-bin-{asset}", sha256, size)


# (os, arch, accelerator) -> the build. Vulkan runs on NVIDIA, AMD and Intel GPUs alike; macOS builds use Metal.
ENGINES: dict[tuple[str, str, str], Artifact] = {
    ("windows", "x64", "vulkan"): _gh("win-vulkan-x64.zip",
                                      "326c346c4c452bf16b8fdca61b79fd71571eabfc3ebff753fbc351718008e854", 32_456_962),
    ("windows", "x64", "cpu"): _gh("win-cpu-x64.zip",
                                   "27935d6ba9c6b7f371203a1d514673cafdcd7f35bb6c1526983b1fcbfbbeffb2", 18_567_826),
    ("linux", "x64", "vulkan"): _gh("ubuntu-vulkan-x64.tar.gz",
                                    "50fe51b17cb302b1554d513148ca52fcc5529251bbea1ce47b2d4626529c0f54", 30_954_359),
    ("linux", "x64", "cpu"): _gh("ubuntu-x64.tar.gz",
                                 "9e4e01efb644c099a848259f2665e3a6cb757c3be46ea66daa0fa626f71fd083", 17_009_716),
    ("linux", "arm64", "vulkan"): _gh("ubuntu-vulkan-arm64.tar.gz",
                                      "234d82884c6347fda29228b4e13bbb858febcbe7cdf4735ff8a0509a09e89c8b", 24_773_606),
    ("linux", "arm64", "cpu"): _gh("ubuntu-arm64.tar.gz",
                                   "48a9606a167135928750928a0b0750f4819b5835e02df720a2dce09e4e33d564", 13_603_530),
    ("macos", "arm64", "metal"): _gh("macos-arm64.tar.gz",
                                     "dc8100181cd0b401073db397ed958f9836af9a0eadeddc82bfcb99c525ce99c1", 11_201_980),
    ("macos", "x64", "metal"): _gh("macos-x64.tar.gz",
                                   "feccd2d0a1aaddc9bb939ccd3d092003438af7e4cd99680b296ec22e6230ea44", 11_246_746),
}
