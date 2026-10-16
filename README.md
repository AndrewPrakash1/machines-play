# Mesa Island

A small Python island for the experiment in Cloos, Norelli, Durbin, Andreas, Rus, and Isola, *Is this machine playing?* (arXiv:2610.07130). The body has no task, score, or reward. Terrain, twelve cubes, a rock that mints cubes on a hard impact, and a ring are here. Notes in the workspace survive the hourly reset; the world and the context do not.

This is the island, the text action API, a browser view, and the four held-out goals. It is not the Rust engine from [clawblox](https://github.com/nacloos/clawblox). Physics is a 60 Hz box simulation that follows the mesa-island sizes and the paper’s action rules. Observations are JSON only. The standard library is enough; nothing needs to be installed.

```bash
python3 -m eko serve
```

Open http://127.0.0.1:8080. Drive turns on click-to-walk. Jump and Stop are buttons. Space also jumps.

```bash
python3 -m eko play --backend demo --seconds 90
python3 -m eko play --backend llm --seconds 3600
python3 -m eko eval --task all --seconds 90
python3 -m unittest discover -s tests -v
```

`demo` is a script that reads and writes the same memory files the paper uses (`SOUL.md`, `SEMANTIC_MEMORY.md`, `EPISODIC_MEMORY.jsonl`). It is a stand-in, and it does less when those notes are blank. `llm` is the unguided coding agent: bash against the text API, Anthropic when `ANTHROPIC_API_KEY` is set, otherwise OpenAI with `OPENAI_API_KEY`. `EKO_MODEL` and `EKO_PROVIDER` override the model and which API is used.

The four goals are `many-5-towers`, `tallest-tower`, `objects-on-spire`, and `throw-on-spire`.
