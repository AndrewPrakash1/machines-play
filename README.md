# Mesa Island

```text
                 ~  ~   ~    ~   ~  ~   ~    ~   ~
            ~                                           ~
        ~          M E S A     I S L A N D                ~
            ~                                           ~
                 ~  ~   ~    ~   ~  ~   ~    ~   ~

                         |                  ______
                        / \                | ring |
                       |you|                ------
                        \ /            [ ][ ][ ]
                         |             [ ][ ][ ]  cubes
                    _____|_____
                   /  ground   \

        ||                         ___________
        ||                        |  summit   |
       /  \                       |___________|
      | SP |                      | tower base|
       \  /                       |___________|
        ||                        | tall mesa |
        ||                        |___________|

      ______              ____________           ______
     | rock |            | large mesa |         | peak |
     |______|            |____________|         |______|
```

A body, a memory, and an island with nothing it is supposed to do.

This is a Python island for the experiment in Cloos, Norelli, Durbin, Andreas, Rus, and Isola, [*Is this machine playing?*](https://arxiv.org/abs/2610.07130) (arXiv:2610.07130). Eko is left here with no task, no score, and no reward. Whatever it learns has to be written down. Every hour the world and the conversation are wiped. The notes in the workspace stay.

The geometry and the six text actions follow the paper’s mesa island. The engine underneath is a 60 Hz box simulation in the Python standard library. It is a runnable stand-in for the island, the memory loop, the browser view, and the four held-out goals. The original world is the Rust engine in [clawblox](https://github.com/nacloos/clawblox).

```text
   wake -------------------------------------------------------.
     |                                                          |
     |   read SOUL, semantic notes, episode summaries           |
     |                          |                               |
     |                          v                               |
     |              wander, jump, carry, throw                  |
     |                          |                               |
     |                          v                               |
     |              write what turned out to be true            |
     |                          |                               |
     '--------------------------+-------------------------------'
                                |
                     five minutes before the hour:
                     "update your memory files now"
                                |
                                v
              the island resets. the notes stay.
```

## What you need

Python 3.10 or newer. Nothing to install. Observations are JSON text. The viewer is one HTML file and does not load anything from a CDN.

```bash
git clone https://github.com/AndrewPrakash1/machines-play.git
cd machines-play
python3 -m eko serve
```

Open http://127.0.0.1:8080.

| Control | What it does |
| --- | --- |
| Drive | Click the ground to walk there. Off by default, so a click does not yank the body. |
| Jump | Same as the Space key. About six units, the cap the paper measures. |
| Stop | Drop the current walk. |
| Follow | The camera stays on the body. On by default. |

The side panel shows who is embodied, where they are, what they are holding, the last action result, the tick, and chat.

## Leave someone on the island

```bash
python3 -m eko play --backend demo --seconds 90
python3 -m eko play --backend llm --seconds 3600 --hour-seconds 3600
```

`demo` is a script that uses the same memory files as the paper. It reads them before it acts and writes them when something works. With a blank workspace it can stack cubes and climb the low step. With notes that mention a rock impact, it shatters the rock first and has more cubes. With a `spire-throw` recipe that includes a jump, it can land a cube on the Spire from the ground. Delete that line and the same throw misses. That is the paper’s claim in miniature: the skill is in the text.

`llm` is the unguided coding agent from the experiment. It gets a bash tool, the system prompt, and the instruction `Begin`. If it stops, it is told to continue. Five minutes before the hour it is told to update its notes. It talks to the island with `curl`.

| Variable | Used when |
| --- | --- |
| `ANTHROPIC_API_KEY` | Anthropic, model `claude-sonnet-4-5` unless `EKO_MODEL` is set. |
| `OPENAI_API_KEY` | OpenAI, model `gpt-4.1` unless `EKO_MODEL` is set. |
| `EKO_PROVIDER` | `anthropic` or `openai`, if both keys are present. |
| `EKO_MODEL` | Replaces the default model name. |

Anthropic is used when its key is set and `EKO_PROVIDER` is empty. Otherwise OpenAI is used. With neither key, `llm` exits and tells you to run `--backend demo`.

```bash
python3 -m eko play --help
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--backend` | `demo` | `demo` or `llm`. |
| `--seconds` | `90` | How long this visit lasts, in wall-clock seconds. |
| `--hour-seconds` | `3600` | Length of one hour. The world resets when an hour ends and time remains. |
| `--port` | `8080` | Where the island listens. |
| `--name` | `Eko` | Name sent to `POST /join`. |
| `--workspace` | `runs/eko` | Directory whose files survive the reset. |
| `--no-soul` | off | Start without `SOUL.md`. |

`runs/` is gitignored. A second visit to the same workspace wakes up with the notes the first visit wrote.

## The four goals

During free play there is no score. Afterwards, the paper hands the agent a goal it was never given and asks whether the notes are enough. This repo grades the same four.

```bash
python3 -m eko eval --task all --seconds 90
python3 -m eko eval --task throw-on-spire --workspace runs/eko
```

| Task | The request | What the score counts |
| --- | --- | --- |
| `many-5-towers` | Build as many 5-block towers as possible on the ground. | Ground columns whose height is at least 5. |
| `tallest-tower` | Build the tallest ground tower, by blocks in one column. | Blocks in the tallest ground column. |
| `objects-on-spire` | Get as many objects as possible onto the Spire. | Cubes resting inside the Spire’s footprint, on or just above the top. |
| `throw-on-spire` | Throw a block onto the Spire as fast as possible, without climbing any platform. | Seconds left in the budget if a cube landed and the body never stood on a mesa. Zero if it climbed, or if nothing landed. |

A fair comparison is the same budget twice: once with an empty workspace, once with the workspace left by `play`. The interesting gap is the one the notes explain.

## The island

North is +z, east is +x. The sketch is the layout, not a scale drawing. Tops are in world units. A jump from the ground reaches about 6.25.

```text
  +z   north
   ^
   |     rock on                 high shelf     peak
   |     small plateau           top 7          top 11
   |     top 2
   |
   |              low step            large mesa
   |              top 2               top 4
   |
   |         * spawn (0, 0)     cube pile
   |
   |     stepping stone                         ridge
   |     top 2.5
   |
   |   tall mesa
   |   top 6
   |   tower base, summit
   |   tops 7 and 10
   |   SPIRE top 20
   |
   |                                          ring
   +-------------------------------------------------> +x   east
```

| Place | Why it matters |
| --- | --- |
| Twelve cubes | They spawn in the air near (15, −1) and settle into a pile. Each is 0.75 on a side. |
| Rock | Sits on the small plateau. A hard impact mints up to eight new cubes. A soft one does nothing. |
| Ring | A torus at (40, −42), yawed 32°. The hole is wide enough for a cube to fall through. |
| Low step | The easy climb. Jump and move together, from the south. |
| Southwest chain | Tall mesa, then tower base, then summit. Feet on the summit are at 10. A jump from there reaches about 16, short of the Spire top at 20. |
| Spire | The tallest thing on the island. Getting a cube onto it from the ground is the throw the paper cares about. |
| Ocean and the walls at ±80 | The ocean is painted water. The walls are invisible. Falling below y = −200 respawns at the origin. |

Walking does not shove cubes. The body can stand on cubes and on mesas. Standing on a mesa whose top is above 1.2 marks the hour as climbed, and `throw-on-spire` then scores zero for that hour.

## How a throw reaches the Spire

A throw always adds 6 units of upward speed, then adds 0.35 of the body’s own velocity. From a standstill the cube peaks near 17 and falls short of 20. Thrown a moment after a jump, it inherits the upward speed of the jump and can clear the top.

That 0.35 carry is the boost the paper says agents found and the designers had not planned. The demo writes the working recipe into `SEMANTIC_MEMORY.md` as a `spire-throw:` line with `"jump": true`. The next hour reads it back.

The rock has the same kind of hidden rule. Impact speed has to reach 6, and the impact energy has to reach 3000. Each extra 3000 mints another cube, up to 8, with a 0.35 s cooldown. A downward throw from the plateau looks violent and is too slow, because of that built-in upward bias.

## Actions

`GET /api.md` is the page the agent is told to fetch. The six inputs:

| Action | Body | Rule |
| --- | --- | --- |
| `MoveTo` | `{"position": [x, y, z]}` | Walks toward x, z. Does not jump. Gives up after 8 s, or when it is within 0.5. |
| `Jump` | `{}` | Vertical speed 50. Character gravity is 200, so the top of the jump is about 6.25. |
| `Stop` | `{}` | Clears the walk. |
| `Pickup` | `{"position": [x, y, z]}` | The nearest carryable within 1.5 of that point, and within 6 of the body. |
| `Place` | `{"position": [x, y, z]}` | Within 7 of the body. Optional `rotation` of `yaw`, `pitch`, `roll` in degrees. Refuses an occupied spot. |
| `Throw` | `{"direction": [x, y, z], "speed": n}` | Speed is clamped to 0..10. Always adds the upward bias, then the carry. |

Cubes, the rock, and the ring can be carried. Mesas, ground, and the ocean cannot.

Join once, then send the session on every later call.

```bash
curl -sS -X POST 'http://127.0.0.1:8080/join?name=Eko'
# {"session":"...","agent_id":"...","name":"Eko"}

curl -sS -X POST http://127.0.0.1:8080/input \
  -H 'Content-Type: application/json' \
  -H 'X-Session: SESSION' \
  -d '{"type":"MoveTo","data":{"position":[8,0,12]}}'

curl -sS -H 'X-Session: SESSION' http://127.0.0.1:8080/observe
```

| Method | Path | Who it is for |
| --- | --- | --- |
| `POST` | `/join?name=` | First call. Returns the session. A second join returns the same one. |
| `POST` | `/input` | One action. Header `X-Session`. Returns the new observation. |
| `GET` | `/observe` | The same observation, without acting. |
| `POST` | `/chat` | `{"content":"..."}` |
| `GET` | `/chat/messages` | The log. |
| `GET` | `/spectate` | What the viewer polls. Includes chat. No session required. |
| `GET` | `/api.md` | The action page above. |
| `GET` | `/health` | `{"ok": true}` |
| `GET` | `/observe/image` | `404`. This experiment is text only, matching the paper. |
| `POST` | `/admin/reset` | Puts the island back to the settled start and deletes minted cubes. Bound to localhost. It is not listed in `/api.md`, so the agent is not invited to reset itself. |

An observation carries `tick`, `time`, `game_status`, and the player (`position`, `velocity`, `grounded`, `holding`, `support`, `last_action_result`, `climbed_platform`). Each entity has `name`, `position`, `size`, a 3×3 `rotation`, `aabb`, `color`, `shape` (`block` or `ring`), `anchored`, and attributes: `RenderRole`, `IsCarryable`, `ItemColorName`. `events` is the short list of things the world just noticed.

## What survives the hour

```text
   forgotten every hour                 kept in the workspace
   ----------------------               -------------------------
   conversation                         SOUL.md
   where the body was                   SEMANTIC_MEMORY.md
   what it was holding                  EPISODIC_MEMORY.jsonl
   towers, throws, new cubes            EPISODIC_MEMORY.md
   the session token
```

`SOUL.md` is the persona. The file says to read it and not rewrite it. `--no-soul` leaves it out.

`EPISODIC_MEMORY.md` explains the format. The entries themselves are one JSON object per line in `EPISODIC_MEMORY.jsonl`: `timestamp`, `summary`, `detail`. Append only. Episodes are what happened. Lessons do not go here.

`SEMANTIC_MEMORY.md` is what the next hour should believe. One section per topic, tagged `verified`, `fact`, `mistake`, or `hypothesis`. The line `<!-- DO NOT EDIT ABOVE THIS LINE -->` marks where the preamble ends and the notes begin.

On a new workspace those files are created for you. The system prompt pastes the soul, the semantic file, and the episode summaries in at the start of the hour, then the model is on its own until the reset warning.

## Layout

```text
eko/world.py        island, physics, actions, observations
eko/server.py       HTTP server and the viewer
eko/prompts.py      soul, memories, system prompt, the four goals
eko/memory.py       create, append, remember, ablate
eko/behaviors.py    the demo body
eko/llm_agent.py    the bash-tool coding agent
eko/scoring.py      the four scores
eko/driver.py       step the world in-process, or over HTTP
web/index.html      isometric view
tests/              world, learning, API
```

`WorldDriver` spends a budget of simulated seconds, which is what `eval` uses. `HttpDriver` spends wall-clock seconds against a running server, which is what `play` uses.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

`tests/test_world.py` checks the roster, the six-unit jump, the low-step climb, stacking, the throw’s inherited upward speed, the rock minting cubes, the ring’s hole, the reset, and a Spire observation.

`tests/test_learning.py` checks that a jump-throw can rest on the Spire without climbing, that a column can grow, and that notes from one hour change what the next hour can do. The last test also deletes the `spire-throw` line and checks that the ground throw misses.

`tests/test_api.py` joins, walks, spectates, and round-trips a chat message.

The world settles the pile before a test starts, so the suite takes a couple of minutes.

## Physics, briefly

Sixty steps a second. Semi-implicit Euler, axis-aligned boxes, and the ring as sixteen spheres. World gravity is 10. The body uses 20 times that, which is how jump speed 50 becomes a height of about 6.25 (`v² / 2g`). Walk speed is 16. Air acceleration is 220. Terminal fall is 100. A step up to 1.05 is climbed automatically. Cubes use the gentler world gravity, density 0.7, friction 0.9, restitution 0.03, so a thrown cube hangs in the air for several seconds. The player is kinematic and does not push props.

Numbers live at the top of `eko/world.py`. If a behavior and the paper disagree, trust the paper and then the constants.

## Citation

```text
Cloos, Norelli, Durbin, Andreas, Rus, and Isola.
Is this machine playing?
arXiv:2610.07130, 2026.
https://arxiv.org/abs/2610.07130
```
