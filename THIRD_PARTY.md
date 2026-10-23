# Harmadik féltől származó összetevők

A projekt saját forráskódja MIT licencű. A csomagolt függőségek és a külön letöltött modellek a saját licenceik alatt maradnak; a projekt licence ezeket nem helyettesíti.

| Összetevő | Szerep | Licenc / forrás |
| --- | --- | --- |
| CPython | Önálló helyi futtatókörnyezet | [PSF License](https://docs.python.org/3/license.html) |
| MLX, MLX Whisper, Whisper | Apple GPU-s magyar beszédfelismerés | [MLX MIT](https://github.com/ml-explore/mlx/blob/main/LICENSE), [MLX Examples MIT](https://github.com/ml-explore/mlx-examples/blob/main/LICENSE), [Whisper MIT](https://github.com/openai/whisper/blob/main/LICENSE) |
| NumPy, SciPy, Numba, llvmlite | Numerikus feldolgozás és szóidőbélyegek | A csomag eredeti licencfájljai mellékelve, az LLVM/OpenBLAS kiegészítő jelöléseivel együtt |
| ONNX Runtime, Sherpa-ONNX | Opcionális beszélőelkülönítés és átfedésjelzés | [MIT](https://github.com/microsoft/onnxruntime/blob/main/LICENSE), [Apache-2.0](https://github.com/k2-fsa/sherpa-onnx/blob/master/LICENSE) |
| FFmpeg 8.1.2 | Helyi M4A/MP3/WAV dekódolás | [LGPL-2.1-or-later](https://ffmpeg.org/legal.html); eredeti forrásarchívum, konfiguráció és buildscript az appban |
| TitaNet-Large | Névtelen hangcsoportok elkülönítése | NVIDIA, [CC-BY-4.0](https://huggingface.co/nvidia/speakerverification_en_titanet_large), a Sherpa-ONNX változatlan ONNX-konverziója |
| Pyannote segmentation 3.0, Sherpa-ONNX kiadás | Beszédszakaszok és átfedésjelöltek | Az archívum eredeti MIT licencfájlja a modell letöltésekor megmarad |
| mlx-community/whisper-large-v3-mlx | Az első használatkor letöltött modell | [MIT modellkártya](https://huggingface.co/mlx-community/whisper-large-v3-mlx), rögzített revision és fájlhash |

Az app `Contents/Resources/ThirdParty/` mappája a buildkörnyezetből összegyűjtött eredeti licencszövegeket és verziójegyzéket tartalmazza. A `models/` almappában a Whisper és TitaNet licence is offline olvasható. Az opcionális modellek eredetjelölése a letöltött modell mellett is megmarad. A licencek a **Local Transcripter → Licencek és források…** menüből megnyithatók.

Az alkalmazás külön folyamatként hívja az FFmpeg parancssori eszközeit. A kiadási build nem használ Homebrew FFmpeg-et, GPL/nonfree opciókat, külső codec-könyvtárakat vagy hálózati protokollt. A változatlan FFmpeg-forrás, LGPL licenc, pontos konfiguráció és fordítási script a `ThirdParty/FFmpeg/` mappában található. Ugyanaz a forrás a DMG-n belül is elérhető; újrafordítható és kicserélhető. A saját forráskód MIT licence nem korlátozza ezt.

Kiinduló forrásarchívum: `https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz`, SHA-256: `464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c`. A fordítás lépései: `scripts/build_audio_tools.py`. A script nem módosítja az FFmpeg forrását. A külső összetevők szerzői jogai az eredeti jogosultaknál maradnak.
