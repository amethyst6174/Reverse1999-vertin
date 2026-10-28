## Reverse: 1999语音资源提取与维尔汀主线音频保存

用于从《重返未来：1999》的国际服APK和Android模拟器资源中提取角色语音，解码为不循环的WAV，并关联当前客户端中的英文剧情文本。
目前已提取角色维尔汀的剧情语音，包含1-13章主线，以及部分支线活动。
未登录且未使用游戏内素材解锁历史支线剧情时，apk以及Android目录中并不包含这些资源，因此其对应内容都不包含在`result/vertin-WAV`目录中。

处理链路：

```text
APK
-> datacfg配置解密
-> configs/story剧情JSON提取
-> voice_id关联
-> WEM解码为WAV
-> 英文文本映射
```

## 目录

### `tool/`

存放完整的可复用工具代码：

- `collect_resources.py`：从ADB和APK收集配置、剧情Bundle、BNK；
- `decrypt_datacfg.py`：解密`datacfg_*.dat`；
- `extract_story.py`：导出`json_story_step_*.json`；
- `extract_audio.py`：解析BNK，并使用`vgmstream -i`解码不循环WAV；
- `map_voice_text.py`：关联音频和英文文本，生成映射与 GPT-SoVITS 清单；
- `run_pipeline.py`：执行完整流程。

安装依赖：

```powershell
python -m pip install -r tool/requirements.txt
```

完整命令和环境准备见 [tool/使用说明.md](tool/使用说明.md)。

### `result/`

用于存放运行结果WAV。推荐结构：

```text
result/
├── source/    # 从APK获取的原始配置、Bundle、BNK
├── config/    # 解密后的datacfg配置表
├── story/     # 当前版本json_story_step_*.json
├── WAV/       # WAV
└── mapping/   # mapping.csv、mapping.jsonl、unmatched.csv、gpt-sovits.list
```

已将维尔汀主线1-13章及少量支线音频和文本映射表保存于`result/vertin-WAV`和`vertin.csv`

## 使用

```powershell
python tool/run_pipeline.py `
  --result result `
  --serial 127.0.0.1:7555 `
  --package com.mover.twcfwl1999 `
  --hero 5043 `
  --language en `
  --apk D:\path\to\twcfwl1999.apk `
  --vgmstream D:\path\to\vgmstream\test.exe
```

最终GPT-SoVITS清单位于：

```text
result/mapping/gpt-sovits.list
```

默认使用`result/WAV`的绝对路径：

```text
/result/WAV/xxx.wav|Vertin|en|English text
```
