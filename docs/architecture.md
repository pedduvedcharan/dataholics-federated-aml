# Architecture

![architecture](architecture.svg)

Rendered diagram: `docs/architecture.svg` (hand-drawn SVG, no build step). Same picture as Mermaid, for anyone who prefers to edit text:

```mermaid
flowchart LR
  subgraph VM["IBM LinuxONE · s390x · Ubuntu 24.04 · docker compose (sandboxed containers)"]
    direction LR
    subgraph banks["banks — each sees only its own shard"]
      B1[bank1<br/>local SGD → clip → +noise]
      B2[bank2]
      B3[bank3]
      B4[bank4]
      R[rogue bank5<br/>poisoned update]
    end
    E{{"egress.send()<br/>the only door out<br/>refuses raw rows · logs every message<br/>rows_shared: 0"}}
    C[coordinator :8000<br/>FedAvg weighted by n_samples<br/>rogue defense: norm + cosine-to-median<br/>ε accounting approx.]
    V[(shared volumes<br/>state/*.json · logs/egress/*.jsonl)]
    D[dashboard :8050<br/>regulator view]
    A[attacker<br/>membership inference<br/>DP off vs on]
    G[genai<br/>SAR writer, CPU LLM<br/>template fallback]
    B1 -->|model update only| E
    B2 --> E
    B3 --> E
    B4 --> E
    R -.->|poisoned| E
    E ==>|"JSON, ~21 numbers"| C
    C -.->|global model back| banks
    C -->|"✖ bank5 excluded"| V
    E -->|audit lines| V
    V --> D
    V --> A
    V --> G
  end
  M[Mac / judge] -->|ssh -L 8050| D
```

What flows where:

| Flow | Content | Never contains |
|---|---|---|
| bank → coordinator | one clipped, noised weight delta per round (JSON, ~750 bytes) | transaction rows, account ids, amounts, labels |
| coordinator → bank | current global `coef`/`intercept` | any bank's data or update |
| everything → dashboard | `state/*.json`, `logs/egress/*.jsonl`, read-only | raw data |
| VM → the world | nothing; ports bind 127.0.0.1, reached through an SSH tunnel | |
