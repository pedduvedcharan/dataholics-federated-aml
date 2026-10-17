# One image for every service (coordinator, bank1-4, rogue, attacker, dashboard, genai).
# Service command is chosen in docker-compose.yml. Built natively on the LinuxONE VM (s390x).
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    OMP_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2

# Scientific stack from Ubuntu apt (prebuilt for s390x). Never pip-compile numpy/scipy/sklearn here.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-numpy python3-scipy python3-pandas python3-sklearn \
      python3-flask python3-matplotlib python3-requests ca-certificates curl procps \
 && rm -rf /var/lib/apt/lists/*

# Pure-Python extras only.
RUN pip install --no-cache-dir --break-system-packages --only-binary numpy,scipy,pandas,scikit-learn phe requests dilithium-py adversarial-robustness-toolbox

WORKDIR /app
COPY fedaml /app/fedaml

# Shared volumes (mounted by compose): /app/data, /app/state, /app/logs
RUN mkdir -p /app/data /app/state /app/logs/egress

CMD ["python3", "-c", "import numpy, pandas, sklearn, flask, phe, platform; print('fedaml image ok', platform.machine(), sklearn.__version__)"]
