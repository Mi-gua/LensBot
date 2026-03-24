# LensBot

LensBot 是一个面向光学镜头设计的 autoresearch agent。

## 目录结构

```text
LensBot/
  main.py
  configs/
    default.yaml
  src/
    agent/
      loop.py
      context.py
      memory.py
      tools.py
    tools/
      requirements.py
      patents.py
      design.py
      evaluation.py
    providers/
      openai.py
    settings.py
    cli/
      main.py
    engine/
      deeplens.py
      deeplens_rms.py
    memory/
      episodic/
      semantic/
    schema.py
    ui.py
```

## 运行

```bash
cd /home/mi/workspace/Lens/LensBot
python main.py
```
